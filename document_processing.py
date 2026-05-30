from typing import List
from datetime import datetime, timedelta

from langchain_core.messages import SystemMessage, HumanMessage

from document_checking import CLAIM_REQUIRED_DOCS, _encode_files
from document_models import DOCUMENT_MODEL_MAP
from langfuse_utils import langfuse_handler
from llms import chat_llm
from state import ClaimState, ClaimVerdictEnum

_CONFIDENCE_RULES = """
Confidence scoring rules (apply strictly):
  1.0  — printed/typed text, value fully and clearly readable
  0.8  — handwritten text, value fully and clearly readable
  0.5–0.2 — partially legible (print or handwriting); use lower end when mostly unreadable
  0.0  — completely unreadable, obscured, or the field is absent from the document

Do NOT round up. If you have any doubt, score lower.
""".strip()

_SYSTEM_TEMPLATE = """You are a medical document extraction agent for an Indian health insurance system.

{confidence_rules}

Your task: extract every field from the {doc_type} document(s) visible in the uploaded images.
Return a single JSON object matching the required schema exactly.
- For each field set `value` to the extracted string (or null if absent/unreadable) and `confidence` according to the rules above.
- For list fields (medicines, line_items, test_results), include one entry per item found.
- Do not fabricate values. If a field is not present or not legible, set value to null and confidence to 0.0.
"""


def _build_system_prompt(doc_type: str) -> str:
    return _SYSTEM_TEMPLATE.format(confidence_rules=_CONFIDENCE_RULES, doc_type=doc_type)


def _parse_date_to_iso_format(date_str: str) -> str:
    """Convert various date formats to yyyy-mm-dd format."""
    if not date_str:
        return None

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
        "%B %d, %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%d %b %Y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str.strip(), fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def document_processing_node(state: ClaimState) -> ClaimState:
    classification = state.get("classification")
    claim_category = classification.claim_category
    required_docs: List[str] = CLAIM_REQUIRED_DOCS[claim_category]
    all_file_paths: List[str] = list(state.get("all_uploaded_file_paths") or [])

    image_blocks = _encode_files(all_file_paths)

    if not image_blocks:
        print("[document_processing] Warning: no uploaded files found in state; skipping extraction.")
        return {**state, "extracted_documents": []}

    extracted_documents = []

    for doc_type in required_docs:
        model_cls = DOCUMENT_MODEL_MAP.get(doc_type)
        if model_cls is None:
            print(f"[document_processing] No model defined for {doc_type}, skipping.")
            continue

        print(f"\nExtracting fields from {doc_type}...")

        structured_llm = chat_llm.with_structured_output(model_cls)

        messages = [
            SystemMessage(content=_build_system_prompt(doc_type)),
            HumanMessage(content=[
                {
                    "type": "text",
                    "text": (
                        f"Please extract all {doc_type} fields from the document images below. "
                        "There may be multiple images; focus on the one(s) that correspond to this document type."
                    ),
                },
                *image_blocks,
            ]),
        ]

        extracted = structured_llm.invoke(messages)

        extracted_documents.append({
            "document_type": doc_type,
            "data": extracted.model_dump(),
        })

        print(f"  Done: {doc_type}")

    print(f"\nDocument processing complete. Extracted {len(extracted_documents)} document(s).")

    # Check if any extracted date fields fall outside policy date range
    policy_start_date = state.get("policy_start_date")
    policy_end_date = state.get("policy_end_date")

    if policy_start_date and policy_end_date:
        for doc in extracted_documents:
            doc_data = doc.get("data", {})
            for date_field_name in ["issue_date", "report_date", "sample_date"]:
                if date_field_name in doc_data:
                    field_info = doc_data[date_field_name]
                    # Extract value from field (dict with value/confidence)
                    field_value = field_info.get("value") if isinstance(field_info, dict) else field_info

                    if field_value:
                        # Convert to yyyy-mm-dd format
                        normalized_date = _parse_date_to_iso_format(str(field_value))

                        if normalized_date:
                            # Check if issue_date is within first 30 days of policy start date
                            policy_start = datetime.strptime(policy_start_date, "%Y-%m-%d")
                            thirty_days_after_start = policy_start + timedelta(days=30)
                            issue_date_obj = datetime.strptime(normalized_date, "%Y-%m-%d")
                            print(f"policy_start : {policy_start}")
                            print(f"thirty_days_after_start : {thirty_days_after_start}")
                            print(f"issue_date_obj : {issue_date_obj}")

                            # check if issue date within first 30 days of policy start
                            if policy_start <= issue_date_obj <= thirty_days_after_start:
                                return{
                                    "claim_verdict": ClaimVerdictEnum.REJECTED,
                                    "claim_decision_reason": f"{date_field_name} of {doc["document_type"]} ({field_value}) Document within 30 days of policy start date. REJECTING claim."
                                }

                            # check if issue date outside policy date range
                            if normalized_date < policy_start_date or normalized_date > policy_end_date:
                                return{
                                    "claim_verdict": ClaimVerdictEnum.REJECTED,
                                    "claim_decision_reason": f"{date_field_name} of {doc["document_type"]} ({field_value}) Document NOT within Policy date range. REJECTING claim."
                                }

    return {
        **state,
        "extracted_documents": extracted_documents,
    }
