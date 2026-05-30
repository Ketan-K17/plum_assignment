from typing import Any, TypedDict, Optional, List
from classify_claim import ClaimClassification

class ClaimState(TypedDict):
    conversation_history: List[str]
    member_id: Optional[str]
    claimed_amount: Optional[float]
    classification: Optional[ClaimClassification]
    collected_documents: Optional[List[str]]
    # Paths of every file the user uploaded during document_checking
    all_uploaded_file_paths: Optional[List[str]]
    # One dict per required document: {"document_type": str, "data": dict}
    extracted_documents: Optional[List[Any]]