from state import ClaimState


def share_verdict_node(state: ClaimState) -> ClaimState:
    """Node that shares the claim verdict with the user."""
    verdict = state.get("claim_verdict")
    reason = state.get("claim_decision_reason", "")

    print("\n--- Claim Verdict ---")
    print(f"Verdict: {verdict}")
    if reason:
        print(f"Reason: {reason}")

    return state
