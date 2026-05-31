from typing import TypedDict, Optional, List
from datetime import datetime, timedelta
import random

from langchain_core import language_models
from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel

from decision_making import ClaimDecision, decision_making_node
from document_checking import document_checking_node
from document_processing import document_processing_node
from langfuse_utils import langfuse_handler, langfuse_client
from state import ClaimState, ClaimVerdictEnum, ClaimClassification
from llms import chat_llm
from utils import read_multiline
from share_verdict import share_verdict_node


class ClaimExtraction(BaseModel):
    member_id: Optional[str] = None
    claim_category: Optional[str] = None
    claimed_amount: Optional[float] = None
    confidence: float
    reason: str


def classify_claim_node(state: ClaimState) -> ClaimState:
    member_id = state.get("member_id")
    claimed_amount = state.get("claimed_amount")
    classification: Optional[ClaimClassification] = state.get("classification")
    conversation_history: List[str] = list(state.get("conversation_history", []))

    prompt = langfuse_client.get_prompt("CLAIM_EXTRACTION_PROMPT")
    extraction_chain = PromptTemplate(
        template=prompt.get_langchain_prompt(),
        input_variables=["user_query"]
    ) | chat_llm.with_structured_output(ClaimExtraction)

    while True:
        combined_text = "\n".join(conversation_history)
        extraction: ClaimExtraction = extraction_chain.invoke({"user_query": combined_text}, config={"metadata": {"langfuse_prompt": prompt}})

        if extraction.member_id and not member_id:
            member_id = extraction.member_id
            member_id = member_id.upper()
        if extraction.claimed_amount is not None and claimed_amount is None:
            claimed_amount = extraction.claimed_amount
        if extraction.claim_category and not classification:
            classification = ClaimClassification(
                claim_category=extraction.claim_category,
                confidence=extraction.confidence,
                reason=extraction.reason,
            )

        missing = []
        if not member_id:
            missing.append("member ID (e.g. EMP001 or DEP001)")
        if not classification:
            missing.append("claim type / nature of treatment")
        if claimed_amount is None:
            missing.append("claimed amount in ₹")

        if not missing:
            break

        print("\nI still need the following to process your claim:")
        for item in missing:
            print(f"  - {item}")
        user_input = read_multiline("\nPlease provide the missing details (press Enter twice when done):")
        conversation_history.append(user_input)

    print("\nAll required information collected:")
    print(f"  Member ID     : {member_id}")
    print(f"  Claim Type    : {classification.claim_category}")
    print(f"  Claimed Amount: ₹{claimed_amount}")
    print(f"  Confidence    : {classification.confidence}")
    print(f"  Reason        : {classification.reason}")

    if member_id.upper() not in ["EMP001", "EMP002", "EMP003", "EMP004", "EMP005", "EMP006", "EMP007", "EMP008", "EMP009", "EMP010", "DEP001", "DEP002"]:
        return{
            "claim_verdict": ClaimVerdictEnum.REJECTED,
            "claim_decision_reason": "member id does not belong to roster. REJECTING claim."
        }

    if claimed_amount < 500:
        return{
            "claim_verdict": ClaimVerdictEnum.REJECTED,
            "claim_decision_reason": "claimed amount less than lower limit. REJECTING claim."
        }

    if claimed_amount >= 25000:
        return{
            "claim_verdict": ClaimVerdictEnum.MANUAL_REVIEW,
            "claim_decision_reason": "claimed amount crossed threshold of INR 25,000. ESCALATING claim to Operations.."
        }

    return {
        "conversation_history": conversation_history,
        "member_id": member_id,
        "claimed_amount": claimed_amount,
        "classification": classification,
        "claim_verdict": None,
    }

# Edge Definitions

def route_after_classification(state: ClaimState) -> str:
    """Route to share_verdict if claim is rejected, otherwise continue to document_checking."""
    verdict = state.get("claim_verdict")
    if verdict == ClaimVerdictEnum.REJECTED or verdict == ClaimVerdictEnum.MANUAL_REVIEW:
        return "share_verdict"
    return "document_checking"

def route_after_doc_processing(state: ClaimState) -> str:
    """Route to share_verdict if claim is rejected, otherwise continue to decision_making."""
    if state["claim_verdict"] == ClaimVerdictEnum.REJECTED:
        return "share_verdict"
    return "decision_making"

def build_graph():
    # Nodes
    graph = StateGraph(ClaimState)
    graph.add_node("classify_claim", classify_claim_node)
    graph.add_node("document_checking", document_checking_node)
    graph.add_node("document_processing", document_processing_node)
    graph.add_node("decision_making", decision_making_node)
    graph.add_node("share_verdict", share_verdict_node)
    graph.set_entry_point("classify_claim")

    # Edges
    graph.add_conditional_edges("classify_claim", route_after_classification)
    graph.add_edge("document_checking", "document_processing")
    graph.add_conditional_edges("document_processing", route_after_doc_processing)
    graph.add_edge("decision_making", "share_verdict")
    graph.add_edge("share_verdict", END)
    return graph.compile()


def main():
    print("Welcome to the Plum Health Insurance Claim System.")
    initial_input = read_multiline("\nPlease describe your claim (press Enter twice when done):")

    policy_start = datetime.strptime("2024-04-01", "%Y-%m-%d")
    policy_end = datetime.strptime("2025-03-31", "%Y-%m-%d")
    random_date = policy_start + timedelta(days=random.randint(0, (policy_end - policy_start).days))
    today_date = random_date.strftime("%Y-%m-%d")

    print(f"TODAY'S DATE: {today_date}")

    app = build_graph()
    final_state: ClaimState = app.invoke({
        "conversation_history": [initial_input],
        "policy_start_date": "2024-04-01",
        "policy_end_date": "2025-03-31",
        "today_date": today_date
    },
    config={"callbacks": [langfuse_handler]})
    # import pdb; pdb.set_trace()

if __name__ == "__main__":
    main()
