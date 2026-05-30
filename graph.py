from typing import TypedDict, Optional, List

from langchain_core import language_models
from langgraph.graph import StateGraph, END
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel

from classify_claim import ClaimClassification
from document_checking import document_checking_node
from langfuse_utils import langfuse_handler, langfuse_client
from state import ClaimState
from llms import chat_llm
from utils import read_multiline


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

    return {
        "conversation_history": conversation_history,
        "member_id": member_id,
        "claimed_amount": claimed_amount,
        "classification": classification,
    }


def build_graph():
    graph = StateGraph(ClaimState)
    graph.add_node("classify_claim", classify_claim_node)
    graph.add_node("document_checking", document_checking_node)
    graph.set_entry_point("classify_claim")
    graph.add_edge("classify_claim", "document_checking")
    graph.add_edge("document_checking", END)
    return graph.compile()


def main():
    print("Welcome to the Plum Health Insurance Claim System.")
    initial_input = read_multiline("\nPlease describe your claim (press Enter twice when done):")

    app = build_graph()
    final_state: ClaimState = app.invoke({
        "conversation_history": [initial_input],
        "member_id": None,
        "claimed_amount": None,
        "classification": None,
        "collected_documents": None,
    },
    config={"callbacks": [langfuse_handler]})

    print("\n--- Final Claim State ---")
    print(f"Member ID     : {final_state['member_id']}")
    print(f"Claim Type    : {final_state['classification'].claim_category}")
    print(f"Claimed Amount: ₹{final_state['claimed_amount']}")
    print(f"Confidence    : {final_state['classification'].confidence}")
    print(f"Reason        : {final_state['classification'].reason}")
    import pdb; pdb.set_trace()


if __name__ == "__main__":
    main()
