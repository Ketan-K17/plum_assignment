from typing import List

from langchain_core.messages import SystemMessage, HumanMessage

from document_checking import CLAIM_REQUIRED_DOCS, _encode_files
from document_models import DOCUMENT_MODEL_MAP
from langfuse_utils import langfuse_handler
from llms import chat_llm
from state import ClaimState

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

    return {
        **state,
        "extracted_documents": extracted_documents,
    }
