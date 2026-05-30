from typing import List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from llms import chat_llm
from state import ClaimState
from utils import encode_file_as_images
from prompts import GENERIC_DOCUMENT_PROMPT

CLAIM_REQUIRED_DOCS = {
    "CONSULTATION": ["PRESCRIPTION", "HOSPITAL_BILL"],
    "DIAGNOSTIC": ["PRESCRIPTION", "LAB_REPORT", "HOSPITAL_BILL"],
    "PHARMACY": ["PRESCRIPTION", "PHARMACY_BILL"],
    "DENTAL": ["HOSPITAL_BILL"],
    "VISION": ["PRESCRIPTION", "HOSPITAL_BILL"],
    "ALTERNATIVE_MEDICINE": ["PRESCRIPTION", "HOSPITAL_BILL"],
}



class DocumentVerification(BaseModel):
    documents_found: List[str]
    documents_missing: List[str]
    all_complete: bool
    message: str


def _read_file_paths() -> List[str]:
    """Prompt the user to enter file paths one per line; blank line to submit."""
    print("\nEnter file paths one per line (press Enter twice when done):")
    paths = []
    while True:
        line = input().strip()
        if line == "":
            if paths:
                break
        else:
            paths.append(line)
    return paths


def _encode_files(file_paths: List[str]) -> list:
    """Encode a list of file paths into LLM image_url content blocks."""
    blocks = []
    for fp in file_paths:
        try:
            pages = encode_file_as_images(fp)
            for b64_data, mime in pages:
                blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64_data}"},
                })
            print(f"  Loaded: {fp} ({len(pages)} page(s))")
        except Exception as e:
            print(f"  Could not read '{fp}': {e}")
    return blocks


def document_checking_node(state: ClaimState) -> ClaimState:
    classification = state.get("classification")
    claim_category = classification.claim_category
    collected_documents: List[str] = list(state.get("collected_documents") or [])

    required_docs = CLAIM_REQUIRED_DOCS[claim_category]

    structured_llm = chat_llm.with_structured_output(DocumentVerification)

    system_content = (
        GENERIC_DOCUMENT_PROMPT
        + f"\n\nFor this {claim_category} claim, the REQUIRED documents are: {', '.join(required_docs)}."
        + "\n\nThe user will upload document images. Examine each image carefully and identify which document types are present."
        + "\n\nIMPORTANT: Only the documents listed above as REQUIRED should be uploaded. If you identify a document type that is NOT in the required list (e.g., a LAB_REPORT when only PRESCRIPTION and HOSPITAL_BILL are needed), mention this in your message and ask the user to upload only the required documents."
        + "\nReturn structured JSON with:"
        + "\n- documents_found: list of REQUIRED document type strings clearly present in the images"
        + "\n- documents_missing: list of REQUIRED document type strings not found"
        + "\n- all_complete: true only when every required document is accounted for"
        + "\n- message: friendly message describing what is still needed, or if they uploaded non-required documents, guide them to upload only what's needed (empty string if all_complete is true)"
    )

    while True:
        still_needed = [doc for doc in required_docs if doc not in collected_documents]

        print(f"\nDocuments still needed for your {claim_category} claim:")
        for doc in still_needed:
            print(f"  - {doc}")

        file_paths = _read_file_paths()
        image_blocks = _encode_files(file_paths)

        if not image_blocks:
            print("No valid files were loaded. Please try again.")
            continue

        # Tell the LLM which docs are already verified so it only needs to check new uploads
        already_verified = (
            f"Already verified from previous uploads: {', '.join(collected_documents)}."
            if collected_documents
            else "No documents verified yet."
        )

        content = [
            {"type": "text", "text": f"{already_verified}\n\nPlease examine the uploaded document image(s) and identify which required document types they contain."},
            *image_blocks,
        ]

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=content),
        ]

        verification: DocumentVerification = structured_llm.invoke(messages)

        for doc in verification.documents_found:
            if doc not in collected_documents:
                collected_documents.append(doc)

        if all(doc in collected_documents for doc in required_docs):
            break

        if verification.message:
            print(f"\n{verification.message}")

    print(f"\nAll required documents collected for {claim_category} claim:")
    for doc in collected_documents:
        print(f"  - {doc}")

    return {
        **state,
        "collected_documents": collected_documents,
    }
