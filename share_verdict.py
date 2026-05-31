from state import ClaimState


def share_verdict_node(state: ClaimState) -> ClaimState:
    """Node that shares the claim verdict with the user."""
    verdict = state.get("claim_verdict")
    reason = state.get("claim_decision_reason", "")
    approved_amount = state.get("approved_amount")
    confidence_score = state.get("confidence_score")

    print("\n═══════════════════════════════════")
    print("         CLAIM VERDICT")
    print("═══════════════════════════════════")
    print(f"  Verdict         : {verdict}")
    if approved_amount is not None:
        print(f"  Approved Amount : ₹{approved_amount:.2f}")
    if confidence_score is not None:
        print(f"  Confidence      : {confidence_score:.2f}")
    if reason:
        print(f"\n  Reason:\n{reason}")
    print("═══════════════════════════════════\n")

    return state
