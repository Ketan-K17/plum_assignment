import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from llms import chat_llm
from state import ClaimState, ClaimVerdictEnum

POLICY_TERMS_PATH = Path(__file__).parent / "policy_terms.json"

_CATEGORY_MAP = {
    "CONSULTATION": "consultation",
    "DIAGNOSTIC": "diagnostic",
    "PHARMACY": "pharmacy",
    "DENTAL": "dental",
    "VISION": "vision",
    "ALTERNATIVE_MEDICINE": "alternative_medicine",
}

_SYSTEM_PROMPT = """You are a claims adjudication engine for Plum Health Insurance (Policy: PLUM_GHI_2024, Insurer: ICICI Lombard General Insurance).

════════════════════════════════════════════════════════════
COMPLETE POLICY REFERENCE — PLUM_GHI_2024
Policy Period: 2024-04-01 to 2025-03-31 (Status: ACTIVE)
════════════════════════════════════════════════════════════

## COVERAGE LIMITS
- Sum insured per employee: ₹5,00,000
- Annual OPD limit: ₹50,000
- Per-claim limit: ₹5,000 — this is a HARD REJECTION threshold for CONSULTATION and VISION
  (Categories with higher sub-limits — dental ₹10,000, diagnostic ₹10,000, pharmacy ₹15,000,
   alternative_medicine ₹8,000 — use their own sub-limit as the effective ceiling instead)
- Family floater combined limit: ₹1,50,000 (shared across SELF, SPOUSE, CHILDREN, PARENTS)

## OPD CATEGORIES — SUB-LIMITS, CO-PAY, AND RULES

### CONSULTATION
- Sub-limit: ₹2,000/year (annual cumulative, not per-claim cap) | Co-pay: 10% | Network discount: 20%
- Requires valid prescription: YES | Pre-auth required: NO
- Per-claim limit applies: YES — reject if claimed_amount > ₹5,000

### DIAGNOSTIC (Lab Tests, Imaging)
- Sub-limit: ₹10,000/year | Co-pay: 0% | Network discount: 10%
- Requires valid prescription: YES
- Pre-auth required: NO for standard tests
- EXCEPTION: MRI, CT Scan, PET Scan require pre-authorization if claim amount > ₹10,000

### PHARMACY
- Sub-limit: ₹15,000/year | Co-pay: 0% for generic drugs
- Branded drug co-pay: 30% (where a generic equivalent exists)
- Generic substitution is mandatory where available
- Requires valid prescription: YES

### DENTAL
- Sub-limit: ₹10,000/year | Co-pay: 0%
- Requires dental treatment report/procedure note: YES
- COVERED procedures: Root Canal Treatment, Tooth Extraction, Dental Filling,
  Scaling and Polishing, Dental X-Ray, Crown Placement, Gum Treatment
- EXCLUDED procedures: Teeth Whitening, Veneers, Orthodontic Treatment (Braces),
  Implants (Cosmetic), Bleaching
- Mixed bills: sum only COVERED line items, then apply dental sub-limit → PARTIAL if excluded items present

### VISION
- Sub-limit: ₹5,000/year | Co-pay: 0%
- Requires valid prescription: YES
- COVERED items: Glasses, Contact Lenses, Eye Examination, Cataract Surgery
- EXCLUDED items: LASIK Surgery, Cosmetic Eye Surgery, Refractive Surgery
- Mixed bills: sum only COVERED line items → PARTIAL if excluded items present
- Per-claim limit applies: YES — reject if claimed_amount > ₹5,000

### ALTERNATIVE MEDICINE (AYUSH)
- Sub-limit: ₹8,000/year | Co-pay: 0%
- Requires valid prescription: YES | Requires registered AYUSH practitioner: YES
- Max 20 sessions/year
- COVERED systems: Ayurveda, Homeopathy, Unani, Siddha, Naturopathy
- Claims from unregistered practitioners or non-listed systems: REJECTED

## WAITING PERIODS (measured from member join date to TREATMENT DATE — not today)
- Initial waiting period (all conditions): 30 days
- Pre-existing conditions: 365 days
- Specific condition waiting periods:
  - Diabetes: 90 days | Hypertension: 90 days | Thyroid disorders: 90 days
  - Joint replacement: 730 days | Maternity: 270 days | Mental health: 180 days
  - Obesity treatment: 365 days | Hernia: 365 days | Cataract: 365 days

IMPORTANT: Always use `days_join_to_treatment` (join_date → treatment_date) for waiting period checks,
NOT days from today. If days_join_to_treatment < required waiting period → REJECTED (WAITING_PERIOD).
When rejecting for waiting period, state the exact date the member becomes eligible
(join_date + waiting_period_days).

## EXCLUSIONS (automatic REJECTED — regardless of amount or documentation)
General:
- Self-inflicted injuries
- War or nuclear hazard
- Substance abuse treatment
- Experimental treatments
- Infertility and assisted reproduction
- Obesity and weight loss programs
- Bariatric surgery
- Cosmetic or aesthetic procedures
- Vaccination (non-medically necessary)
- Health supplements and tonics

Dental-specific: Teeth whitening, Orthodontic treatment, Cosmetic dental procedures
Vision-specific: LASIK, Refractive surgery

## PRE-AUTHORIZATION
- Required BEFORE treatment for: MRI scan (>₹10,000), CT scan (>₹10,000), PET scan,
  Major surgical procedures, Planned hospitalization
- Pre-auth validity: 30 days from issue date
- If required but not obtained → REJECTED
- If pre-auth obtained but treatment occurred >30 days after issue date → REJECTED

## NETWORK HOSPITALS (eligible for network discount)
Apollo Hospitals, Fortis Healthcare, Max Healthcare, Manipal Hospitals, Narayana Health,
Medanta, Kokilaben Dhirubhai Ambani Hospital, Aster CMI Hospital, Columbia Asia, Sakra World Hospital

## SUBMISSION RULES
- Claims must be submitted within 30 days of treatment date (else REJECTED)
- Minimum claimable amount: ₹500 (below this → REJECTED)
- All amounts in INR

## FRAUD & MANUAL REVIEW THRESHOLDS
- Claimed amount > ₹25,000 → always MANUAL_REVIEW
- Fraud score ≥ 0.80 → MANUAL_REVIEW
- More than 2 claims on the same treatment date → fraud flag → MANUAL_REVIEW
- More than 6 claims in a calendar month → fraud flag → MANUAL_REVIEW

════════════════════════════════════════════════════════════
DECISION WORKFLOW
════════════════════════════════════════════════════════════

## STEP 1 — HARD REJECTIONS → decision = REJECTED, approved_amount = 0

Reject (stop evaluating further) if ANY of these are true:
1. Claim submitted more than 30 days after treatment date
2. Initial waiting period not met: days_join_to_treatment < 30
3. Condition-specific waiting period not met (check diagnosis against the specific conditions table above
   using days_join_to_treatment)
4. Pre-existing condition claimed within 365 days of join date (days_join_to_treatment < 365)
5. Diagnosis or procedure is in the general exclusions list
6. Dental claim contains an excluded dental procedure (full bill or specific line item)
7. Vision claim contains an excluded vision item (full bill or specific line item)
8. Alternative medicine system is not in the covered systems list OR practitioner is unregistered
9. MRI or CT Scan where claimed amount > ₹10,000 and no pre-authorization document is present
10. Pre-authorization was obtained but treatment date is more than 30 days after pre-auth issue date
11. CONSULTATION or VISION claim where claimed_amount > ₹5,000 (per-claim limit exceeded → PER_CLAIM_EXCEEDED)

## STEP 2 — MANUAL REVIEW TRIGGERS → decision = MANUAL_REVIEW, approved_amount = null

Route to manual review if ANY apply (do not reject, do not approve):
1. Claimed amount > ₹25,000
2. Average document confidence score < 0.4
3. Diagnosis is too ambiguous to confidently rule on exclusions or waiting periods
4. Extracted bill amount differs significantly from claimed amount (possible alteration)
5. Document shows corrections, overwritten amounts, or conflicting ORIGINAL/DUPLICATE markings
6. Member has submitted >2 claims on the same treatment date (check claims_history)
7. Member has submitted >6 claims in the current calendar month (check claims_history)
8. Condition involves a very long waiting period (e.g., joint replacement at 730 days) requiring human verification
9. Dependent's relationship cannot be verified against roster
10. Practitioner registration number missing or unreadable on alternative medicine claim
11. LLM extraction failed or returned null on critical fields (diagnosis, amount, date)
12. A pipeline component failed (see component_failures in context) — reduce confidence and flag

For MANUAL_REVIEW: your reason must be an exceptionally detailed trace. List every ambiguity,
every missing piece, every conflicting signal — the ops person picking this up must understand
exactly what stopped automated adjudication and what they should verify manually.

## STEP 3 — AMOUNT CALCULATION (all other cases → APPROVED or PARTIAL)

Compute the payable amount in this EXACT order:

1. Start with claimed_amount
2. For DENTAL/VISION with mixed bills: sum only the COVERED line items (exclude cosmetic/excluded procedures).
   If any line items were excluded, decision will be PARTIAL.
3. Cap at the effective ceiling:
   - CONSULTATION/VISION: ₹5,000 per-claim limit (already checked in Step 1; should not exceed this)
   - DENTAL: ₹10,000 sub-limit | DIAGNOSTIC: ₹10,000 | PHARMACY: ₹15,000 | ALTERNATIVE_MEDICINE: ₹8,000
4. If is_network_hospital = true, apply network discount FIRST (before co-pay):
   amount_after_discount = capped_amount × (1 − network_discount_percent / 100)
   - consultation network discount: 20% | diagnostic: 10%
   If NOT a network hospital, amount_after_discount = capped_amount (no change)
5. Apply co-pay on the discounted amount:
   approved_amount = amount_after_discount × (1 − copay_percent / 100)
   - consultation: 10% | all others: 0% (except pharmacy branded drugs — see below)
6. For PHARMACY with branded drugs: apply 30% co-pay on the branded drug portion only

Decision based on final amount vs original claimed:
- approved_amount < claimed_amount → PARTIAL
- approved_amount ≥ claimed_amount → APPROVED

## CONFIDENCE SCORE (start at 1.0, deduct, clamp to [0.0, 1.0])
- −0.2 if average document confidence < 0.6
- −0.1 if diagnosis is ambiguous or partially legible
- −0.2 if member was not found in the roster
- −0.1 if any hard rule required an inference rather than a clear stated fact
- −0.1 if treatment facility is out-of-network (informational, not a rejection reason)
- −0.2 per component failure listed in component_failures context (min 0.3 for degraded pipeline)

════════════════════════════════════════════════════════════
REASON FORMAT — MANDATORY
════════════════════════════════════════════════════════════

The `reason` field MUST be a numbered checklist. Every rule you evaluated (both passed and
failed) must appear as a line item. Each line must end with — PASS or — FAIL.

Format:
  1. [Rule name]: [specific values you compared] — PASS
  2. [Rule name]: [specific values you compared] — FAIL → [what this means for the decision]
  ...
  Decision summary: [one sentence explaining the final outcome]

Rules to always include (when applicable):
  - Policy period check (treatment date vs 2024-04-01–2025-03-31)
  - Minimum claim amount (≥ ₹500)
  - Submission deadline (within 30 days of treatment)
  - Member found in roster
  - Initial waiting period (days_join_to_treatment ≥ 30)
  - Condition-specific waiting period (if diagnosis matches a specific condition, state days_join_to_treatment vs required days, and eligibility date)
  - Exclusion check (diagnosis/procedure vs exclusions list)
  - Pre-authorization check (if MRI/CT/PET or high-value surgical)
  - Per-claim limit check (CONSULTATION/VISION: claimed ≤ ₹5,000)
  - Document confidence check
  - Amount > ₹25,000 manual review threshold
  - Fraud signals (same-day claims count, monthly volume) — note if unknown
  - Component failures (if any — list each failed component and its impact)
  - Category sub-limit cap
  - Network discount (if applicable — show amount_after_discount)
  - Co-pay calculation (show amount_after_copay)
  - Approved amount vs claimed amount comparison

For MANUAL_REVIEW cases, additionally list:
  - Every field that was ambiguous or unreadable
  - Every signal that raised suspicion
  - Every piece of information the human reviewer should verify
  - Recommended verification steps
"""


class ClaimDecision(BaseModel):
    decision: str  # APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW
    approved_amount: Optional[float] = None
    reason: str
    confidence_score: float


def _load_policy() -> dict:
    with open(POLICY_TERMS_PATH) as f:
        return json.load(f)


def _get_member(policy: dict, member_id: str) -> Optional[dict]:
    for m in policy.get("members", []):
        if m["member_id"] == member_id:
            return m
    return None


def _collect_confidence_scores(obj: Any) -> list[float]:
    scores = []
    if isinstance(obj, dict):
        if "value" in obj and "confidence" in obj:
            scores.append(obj["confidence"])
        else:
            for v in obj.values():
                scores.extend(_collect_confidence_scores(v))
    elif isinstance(obj, list):
        for item in obj:
            scores.extend(_collect_confidence_scores(item))
    return scores


def _avg_doc_confidence(extracted_documents: list) -> float:
    scores = []
    for doc in extracted_documents:
        scores.extend(_collect_confidence_scores(doc.get("data", {})))
    return round(sum(scores) / len(scores), 3) if scores else 0.0


def _is_network_hospital(policy: dict, hospital_name_hint: Optional[str], extracted_documents: list) -> bool:
    network = [h.lower() for h in policy.get("network_hospitals", [])]

    # Check explicit hospital_name hint from claim input first
    if hospital_name_hint:
        h = hospital_name_hint.lower()
        if any(net in h or h in net for net in network):
            return True

    for doc in extracted_documents:
        data = doc.get("data", {})
        for field in ("hospital_name", "pharmacy_name", "lab_name"):
            val = (data.get(field) or {}).get("value") or ""
            val_lower = val.lower()
            if any(net in val_lower or val_lower in net for net in network):
                return True
    return False


def _flatten_doc(obj: Any) -> Any:
    """Collapse ConfidenceField dicts to 'value (conf: X)' strings for readability."""
    if isinstance(obj, dict):
        if "value" in obj and "confidence" in obj:
            return f"{obj['value']} (conf: {obj['confidence']})"
        return {k: _flatten_doc(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_flatten_doc(item) for item in obj]
    return obj


def _docs_summary(extracted_documents: list) -> str:
    parts = []
    for doc in extracted_documents:
        flat = _flatten_doc(doc.get("data", {}))
        parts.append(f"=== {doc['document_type']} ===\n{json.dumps(flat, indent=2, ensure_ascii=False)}")
    return "\n\n".join(parts) if parts else "No documents extracted."


def decision_making_node(state: ClaimState) -> ClaimState:
    policy = _load_policy()

    member_id = state.get("member_id")
    claimed_amount = state.get("claimed_amount") or 0.0
    classification = state.get("classification")
    claim_category = (classification.claim_category if classification else "UNKNOWN").upper()
    extracted_documents = list(state.get("extracted_documents") or [])
    treatment_date_str = state.get("treatment_date")
    claims_history = state.get("claims_history") or []
    simulate_failure = state.get("simulate_component_failure", False)
    hospital_name_hint = state.get("hospital_name")  # optional hint from claim input

    # Component failure simulation: note the skipped component
    component_failures: list[str] = []
    if simulate_failure:
        component_failures.append(
            "fraud_risk_scorer: simulated component failure — fraud score unavailable, skipped"
        )

    member = _get_member(policy, member_id)
    join_date_str: Optional[str] = None
    days_join_to_treatment: Optional[int] = None
    eligibility_note: str = "Unknown — treatment date or join date missing"

    if member and member.get("join_date"):
        join_date_str = member["join_date"]
        join_date = datetime.strptime(join_date_str, "%Y-%m-%d").date()

        if treatment_date_str:
            treatment_date = datetime.strptime(treatment_date_str, "%Y-%m-%d").date()
            days_join_to_treatment = (treatment_date - join_date).days
            eligibility_note = (
                f"{days_join_to_treatment} days between join date ({join_date_str}) "
                f"and treatment date ({treatment_date_str})"
            )

    avg_confidence = _avg_doc_confidence(extracted_documents)
    network_hospital = _is_network_hospital(policy, hospital_name_hint, extracted_documents)
    policy_category_key = _CATEGORY_MAP.get(claim_category, claim_category.lower())
    category_rules = policy.get("opd_categories", {}).get(policy_category_key, {})
    coverage = policy.get("coverage", {})

    component_failures_section = (
        f"\n## Component Failures (pipeline degraded)\n"
        + "\n".join(f"- {f}" for f in component_failures)
        if component_failures
        else ""
    )

    claims_history_section = (
        f"\n## Prior Claims History (for fraud detection)\n{json.dumps(claims_history, indent=2, ensure_ascii=False)}"
        if claims_history
        else "\n## Prior Claims History\nNone provided — same-day/monthly fraud check cannot be performed."
    )

    human_content = f"""## Claim Details
- Member ID: {member_id}
- Claim Category: {claim_category}
- Claimed Amount: ₹{claimed_amount}
- Treatment Date: {treatment_date_str or "NOT PROVIDED"}
- Today's Date: {state['today_date']}

## Member Details
{json.dumps(member, indent=2, ensure_ascii=False) if member else "Member not found in roster."}

## Waiting Period Context
- Member join date: {join_date_str or "Unknown"}
- Treatment date: {treatment_date_str or "Unknown"}
- Days from join to treatment (use this for ALL waiting period checks): {days_join_to_treatment if days_join_to_treatment is not None else "Unknown"}
- Note: {eligibility_note}

## Pre-computed Context
- Is network hospital/lab/pharmacy: {network_hospital}
- Average document confidence score: {avg_confidence}
{component_failures_section}

## Coverage Limits
{json.dumps(coverage, indent=2, ensure_ascii=False)}

## Category Policy Rules (for category: {claim_category})
{json.dumps(category_rules, indent=2, ensure_ascii=False) if category_rules else "Category not found — treat as UNKNOWN."}

## All OPD Category Sub-limits (for reference)
{json.dumps(policy.get("opd_categories", {}), indent=2, ensure_ascii=False)}

## Waiting Periods
{json.dumps(policy.get("waiting_periods", {}), indent=2, ensure_ascii=False)}

## Policy Exclusions
{json.dumps(policy.get("exclusions", {}), indent=2, ensure_ascii=False)}

## Pre-authorization Rules
{json.dumps(policy.get("pre_authorization", {}), indent=2, ensure_ascii=False)}

## Network Hospitals
{json.dumps(policy.get("network_hospitals", []), indent=2, ensure_ascii=False)}

## Fraud & Auto-Review Thresholds
{json.dumps(policy.get("fraud_thresholds", {}), indent=2, ensure_ascii=False)}

## Submission Rules
{json.dumps(policy.get("submission_rules", {}), indent=2, ensure_ascii=False)}

## Policy Period
- Start: {policy.get("policy_holder", {}).get("policy_start_date", "2024-04-01")}
- End: {policy.get("policy_holder", {}).get("policy_end_date", "2025-03-31")}
{claims_history_section}

## Extracted Document Data
{_docs_summary(extracted_documents)}

---

Using the policy reference in your system prompt and all claim context above:
1. Work through EVERY applicable rule in sequence (Step 1 → Step 2 → Step 3).
2. Write the `reason` as a numbered checklist — one line per rule evaluated, each ending with — PASS or — FAIL.
3. If any Step 1 rule FAILs, stop there and return REJECTED.
4. If any Step 2 trigger fires, return MANUAL_REVIEW with an exhaustive trace in `reason`.
5. Otherwise, compute the approved amount step-by-step (network discount FIRST, then co-pay) and return APPROVED or PARTIAL.
6. If component_failures is non-empty: deduct 0.2 from confidence per failure, note each in reason, and add "Manual review recommended due to incomplete pipeline processing."
"""

    structured_llm = chat_llm.with_structured_output(ClaimDecision)
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]

    print("\nRunning claims adjudication...")

    try:
        decision: ClaimDecision = structured_llm.invoke(messages)
    except Exception as exc:
        # Graceful degradation: LLM call failed — produce a safe fallback
        component_failures.append(f"claims_adjudicator: {exc}")
        failure_note = "; ".join(component_failures)
        decision = ClaimDecision(
            decision="MANUAL_REVIEW",
            approved_amount=None,
            reason=(
                f"1. Adjudication engine failure: {exc} — FAIL → pipeline could not complete\n"
                f"Component failures: {failure_note}\n"
                "Decision summary: Adjudication engine encountered an error; routing to manual review. "
                "Manual review is required to complete this claim."
            ),
            confidence_score=max(0.3, 1.0 - 0.2 * len(component_failures)),
        )

    # If components failed but LLM succeeded, still flag it in the reason
    if component_failures and "component failure" not in decision.reason.lower():
        failure_note = "; ".join(component_failures)
        decision.reason = (
            decision.reason.rstrip()
            + f"\n\nComponent failures detected: {failure_note}. "
            "Manual review recommended due to incomplete pipeline processing."
        )
        decision.confidence_score = max(0.3, decision.confidence_score - 0.2 * len(component_failures))

    print("\n--- Claim Decision ---")
    print(f"  Decision        : {decision.decision}")
    if decision.approved_amount is not None:
        print(f"  Approved Amount : ₹{decision.approved_amount:.2f}")
    else:
        print("  Approved Amount : N/A")
    print(f"  Confidence      : {decision.confidence_score:.2f}")
    print(f"  Reason:\n{decision.reason}")

    return {
        **state,
        # Raw decision object (used by api.py)
        "claim_decision": decision,
        # Populate ClaimState verdict fields for graph/share_verdict path
        "claim_verdict": ClaimVerdictEnum(decision.decision),
        "claim_decision_reason": decision.reason,
        "approved_amount": decision.approved_amount,
        "confidence_score": decision.confidence_score,
    }
