from typing import Any, TypedDict, Optional, List
from classify_claim import ClaimClassification
from enum import Enum
class ClaimVerdictEnum(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"

class ClaimState(TypedDict):
    # extracted from policy_terms.json
    policy_start_date: str
    policy_end_date: str

    conversation_history: List[str]
    member_id: Optional[str]
    claimed_amount: Optional[float]
    classification: Optional[ClaimClassification]
    collected_documents: Optional[List[str]]
    # Paths of every file the user uploaded during document_checking
    all_uploaded_file_paths: Optional[List[str]]
    # One dict per required document: {"document_type": str, "data": dict}
    extracted_documents: Optional[List[Any]]

    # Structured verdict produced by decision_making_node
    claim_verdict: Optional[ClaimVerdictEnum]
    claim_decision_reason: str