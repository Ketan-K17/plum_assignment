import os
import uuid
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from classify_claim import ClaimClassification
from document_checking import CLAIM_REQUIRED_DOCS, DocumentVerification, _encode_files
from document_processing import document_processing_node
from graph import ClaimExtraction
from langfuse_utils import langfuse_client
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from llms import chat_llm
from state import ClaimVerdictEnum

UPLOAD_DIR = Path("uploads")

app = FastAPI(title="Plum Claims API")

VALID_MEMBER_IDS = {
    "EMP001", "EMP002", "EMP003", "EMP004", "EMP005",
    "EMP006", "EMP007", "EMP008", "EMP009", "EMP010",
    "DEP001", "DEP002",
}

POLICY_START = "2024-04-01"
POLICY_END = "2025-03-31"

# In-memory session store.
# Each session holds the partial ClaimState built up over multiple turns.
sessions: dict[str, dict] = {}


class MessageRequest(BaseModel):
    text: str


class SessionResponse(BaseModel):
    session_id: str
    message: str


class TurnResponse(BaseModel):
    status: str  # "collecting_info" | "rejected" | "ready"
    reply: str
    session_id: str


def _make_today_date() -> str:
    policy_start = datetime.strptime(POLICY_START, "%Y-%m-%d")
    policy_end = datetime.strptime(POLICY_END, "%Y-%m-%d")
    random_date = policy_start + timedelta(days=random.randint(0, (policy_end - policy_start).days))
    return random_date.strftime("%Y-%m-%d")


def _run_extraction(conversation_history: list[str]) -> ClaimExtraction:
    prompt = langfuse_client.get_prompt("CLAIM_EXTRACTION_PROMPT")
    chain = PromptTemplate(
        template=prompt.get_langchain_prompt(),
        input_variables=["user_query"]
    ) | chat_llm.with_structured_output(ClaimExtraction)
    combined = "\n".join(conversation_history)
    return chain.invoke({"user_query": combined}, config={"metadata": {"langfuse_prompt": prompt}})


def _missing_fields_message(missing: list[str]) -> str:
    lines = ["I still need the following to process your claim:"]
    for item in missing:
        lines.append(f"  - {item}")
    return "\n".join(lines)


@app.post("/claims/session", response_model=SessionResponse)
def create_session():
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "conversation_history": [],
        "member_id": None,
        "claimed_amount": None,
        "classification": None,
        "policy_start_date": POLICY_START,
        "policy_end_date": POLICY_END,
        "today_date": _make_today_date(),
        "status": "collecting_info",
        "collected_documents": [],
        "all_uploaded_file_paths": [],
        "extracted_documents": None,
        "claim_verdict": None,
        "claim_decision_reason": None,
    }
    return SessionResponse(
        session_id=session_id,
        message="Session created. Please describe your claim.",
    )


@app.post("/claims/{session_id}/message", response_model=TurnResponse)
def post_message(session_id: str, body: MessageRequest):
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "collecting_info":
        raise HTTPException(
            status_code=400,
            detail=f"Session is already in status '{session['status']}'. No more messages accepted at this stage.",
        )

    session["conversation_history"].append(body.text)

    extraction: ClaimExtraction = _run_extraction(session["conversation_history"])

    if extraction.member_id and not session["member_id"]:
        session["member_id"] = extraction.member_id.upper()
    if extraction.claimed_amount is not None and session["claimed_amount"] is None:
        session["claimed_amount"] = extraction.claimed_amount
    if extraction.claim_category and not session["classification"]:
        session["classification"] = ClaimClassification(
            claim_category=extraction.claim_category,
            confidence=extraction.confidence,
            reason=extraction.reason,
        )

    missing = []
    if not session["member_id"]:
        missing.append("member ID (e.g. EMP001 or DEP001)")
    if not session["classification"]:
        missing.append("claim type / nature of treatment")
    if session["claimed_amount"] is None:
        missing.append("claimed amount in ₹")

    if missing:
        return TurnResponse(
            status="collecting_info",
            reply=_missing_fields_message(missing),
            session_id=session_id,
        )

    # All fields collected — run the same validation checks as classify_claim_node
    member_id = session["member_id"]
    claimed_amount = session["claimed_amount"]

    if member_id not in VALID_MEMBER_IDS:
        session["status"] = "rejected"
        session["claim_verdict"] = ClaimVerdictEnum.REJECTED
        session["claim_decision_reason"] = "Member ID does not belong to roster."
        return TurnResponse(
            status="rejected",
            reply=f"Sorry, member ID '{member_id}' is not on our roster. Claim rejected.",
            session_id=session_id,
        )

    if claimed_amount < 500:
        session["status"] = "rejected"
        session["claim_verdict"] = ClaimVerdictEnum.REJECTED
        session["claim_decision_reason"] = "Claimed amount less than minimum limit of ₹500."
        return TurnResponse(
            status="rejected",
            reply=f"Claimed amount ₹{claimed_amount} is below the minimum limit of ₹500. Claim rejected.",
            session_id=session_id,
        )

    session["status"] = "ready"
    classification: ClaimClassification = session["classification"]
    return TurnResponse(
        status="ready",
        reply=(
            f"Got it! Here's what I've collected:\n"
            f"  Member ID     : {member_id}\n"
            f"  Claim Type    : {classification.claim_category}\n"
            f"  Claimed Amount: ₹{claimed_amount}\n\n"
            "Please upload your supporting documents to proceed."
        ),
        session_id=session_id,
    )


def _run_document_verification(
    session: dict,
    new_file_paths: list[str],
) -> DocumentVerification:
    """Run the document-checking LLM against newly uploaded files."""
    classification: ClaimClassification = session["classification"]
    claim_category = classification.claim_category
    collected_documents: list[str] = session["collected_documents"]

    required_docs = CLAIM_REQUIRED_DOCS[claim_category]
    req_docs_string = ", ".join(required_docs)

    generic_document_prompt = langfuse_client.get_prompt("GENERIC_DOCUMENT_PROMPT")
    system_content_langfuse_prompt = langfuse_client.get_prompt("DOCUMENT_CHECKING_PROMPT")
    system_content_langchain_prompt = PromptTemplate.from_template(
        system_content_langfuse_prompt.get_langchain_prompt()
    )
    system_content = system_content_langchain_prompt.format(
        generic_document_prompt=generic_document_prompt.get_langchain_prompt(),
        claim_category=claim_category,
        req_docs_string=req_docs_string,
    )

    image_blocks = _encode_files(new_file_paths)

    already_verified = (
        f"Already verified from previous uploads: {', '.join(collected_documents)}."
        if collected_documents
        else "No documents verified yet."
    )

    content = [
        {
            "type": "text",
            "text": (
                f"{already_verified}\n\n"
                "Please examine the uploaded document image(s) and identify which required document types they contain."
            ),
        },
        *image_blocks,
    ]

    structured_llm = chat_llm.with_structured_output(DocumentVerification)
    return structured_llm.invoke(
        [SystemMessage(content=system_content), HumanMessage(content=content)],
        config={"metadata": {"langfuse_prompt": system_content_langfuse_prompt}},
    )


@app.post(
    "/claims/{session_id}/documents",
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                            }
                        },
                        "required": ["files"],
                    }
                }
            },
            "required": True,
        }
    },
)
async def upload_documents(session_id: str, files: list[UploadFile] = File(...)):
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] not in ("ready", "awaiting_documents"):
        raise HTTPException(
            status_code=400,
            detail=f"Session is in status '{session['status']}'. Document uploads are only accepted after claim info is collected.",
        )
    if not files:
        raise HTTPException(status_code=422, detail="No files provided.")

    # Save uploaded files to disk
    session_upload_dir = UPLOAD_DIR / session_id
    session_upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []
    for upload in files:
        dest = session_upload_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved_paths.append(str(dest))

    session["all_uploaded_file_paths"].extend(saved_paths)

    # Run document verification (LLM call — offload from event loop)
    verification: DocumentVerification = await run_in_threadpool(
        _run_document_verification, session, saved_paths
    )

    for doc in verification.documents_found:
        if doc not in session["collected_documents"]:
            session["collected_documents"].append(doc)

    classification: ClaimClassification = session["classification"]
    claim_category = classification.claim_category
    required_docs = CLAIM_REQUIRED_DOCS[claim_category]
    still_missing = [d for d in required_docs if d not in session["collected_documents"]]

    if still_missing:
        session["status"] = "awaiting_documents"
        return {
            "session_id": session_id,
            "status": "awaiting_documents",
            "verified_so_far": session["collected_documents"],
            "still_missing": still_missing,
            "message": (
                f"Received and verified: {', '.join(verification.documents_found) or 'none recognised'}.\n"
                f"Still needed: {', '.join(still_missing)}. Please upload the remaining documents."
            ),
        }

    # All required documents collected — run document processing
    # Build a ClaimState-compatible dict from session
    claim_state = {
        "classification": session["classification"],
        "all_uploaded_file_paths": session["all_uploaded_file_paths"],
        "collected_documents": session["collected_documents"],
        "policy_start_date": session["policy_start_date"],
        "policy_end_date": session["policy_end_date"],
        "today_date": session["today_date"],
        "member_id": session["member_id"],
        "claimed_amount": session["claimed_amount"],
        "conversation_history": session["conversation_history"],
        "extracted_documents": None,
        "claim_verdict": None,
        "claim_decision_reason": None,
    }

    processing_result = await run_in_threadpool(document_processing_node, claim_state)

    # Merge processing result back into session
    session["extracted_documents"] = processing_result.get("extracted_documents")

    if processing_result.get("claim_verdict") == ClaimVerdictEnum.REJECTED:
        session["status"] = "rejected"
        session["claim_verdict"] = ClaimVerdictEnum.REJECTED
        session["claim_decision_reason"] = processing_result.get("claim_decision_reason")
        return {
            "session_id": session_id,
            "status": "rejected",
            "message": f"Claim rejected during document processing: {session['claim_decision_reason']}",
        }

    session["status"] = "documents_processed"
    return {
        "session_id": session_id,
        "status": "documents_processed",
        "verified_documents": session["collected_documents"],
        "message": "All required documents verified and processed. Ready for final decision.",
    }


@app.get("/claims/{session_id}/status")
def get_status(session_id: str):
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "status": session["status"],
        "member_id": session["member_id"],
        "claimed_amount": session["claimed_amount"],
        "classification": session["classification"],
        "collected_documents": session.get("collected_documents"),
        "extracted_documents": session.get("extracted_documents"),
        "claim_verdict": session.get("claim_verdict"),
        "claim_decision_reason": session.get("claim_decision_reason"),
    }
