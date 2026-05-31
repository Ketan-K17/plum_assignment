from typing import Any, TypedDict, Optional, List
from pydantic import BaseModel
from enum import Enum
class ClaimVerdictEnum(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"

class ClaimClassification(BaseModel):
    claim_category: str
    confidence: float
    reason: str

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

    # Date of the medical treatment (yyyy-mm-dd)
    treatment_date: Optional[str]
    # Prior claims history for fraud detection (list of claim dicts)
    claims_history: Optional[List[dict]]
    # When True, the pipeline simulates a mid-flight component failure
    simulate_component_failure: Optional[bool]

    # Structured verdict produced by decision_making_node
    claim_verdict: Optional[ClaimVerdictEnum]
    claim_decision_reason: str
    approved_amount: Optional[float]
    confidence_score: Optional[float]

    # a date chosen randomly between policy start and end date
    today_date: str