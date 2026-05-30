from typing import TypedDict, Optional, List
from classify_claim import ClaimClassification

class ClaimState(TypedDict):
    conversation_history: List[str]
    member_id: Optional[str]
    claimed_amount: Optional[float]
    classification: Optional[ClaimClassification]