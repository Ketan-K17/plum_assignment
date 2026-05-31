import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from llms import chat_llm
from state import ClaimState

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
- Per-claim limit: ₹5,000 (hard cap across all categories)
- Family floater combined limit: ₹1,50,000 (shared across SELF, SPOUSE, CHILDREN, PARENTS)

## OPD CATEGORIES — SUB-LIMITS, CO-PAY, AND RULES

### CONSULTATION
- Sub-limit: ₹2,000/year | Co-pay: 10% | Network discount: 20%
- Requires valid prescription: YES | Pre-auth required: NO

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
- Mixed bills: approve only covered line items → PARTIAL

### VISION
- Sub-limit: ₹5,000/year | Co-pay: 0%
- Requires valid prescription: YES
- COVERED items: Glasses, Contact Lenses, Eye Examination, Cataract Surgery
- EXCLUDED items: LASIK Surgery, Cosmetic Eye Surgery, Refractive Surgery
- Mixed bills: approve only covered line items → PARTIAL

### ALTERNATIVE MEDICINE (AYUSH)
- Sub-limit: ₹8,000/year | Co-pay: 0%
- Requires valid prescription: YES | Requires registered AYUSH practitioner: YES
- Max 20 sessions/year
- COVERED systems: Ayurveda, Homeopathy, Unani, Siddha, Naturopathy
- Claims from unregistered practitioners or non-listed systems: REJECTED

## WAITING PERIODS (from member join date)
- Initial waiting period (all conditions): 30 days
- Pre-existing conditions: 365 days
- Specific condition waiting periods:
  - Diabetes: 90 days | Hypertension: 90 days | Thyroid disorders: 90 days
  - Joint replacement: 730 days | Maternity: 270 days | Mental health: 180 days
  - Obesity treatment: 365 days | Hernia: 365 days | Cataract: 365 days

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
1. Treatment date is outside policy period (2024-04-01 to 2025-03-31)
2. Claimed amount < ₹500
3. Claim submitted more than 30 days after treatment date
4. Initial waiting period not met (member joined < 30 days before treatment date)
5. Condition-specific waiting period not met (check diagnosis against the specific conditions table above)
6. Pre-existing condition claimed within 365 days of join date
7. Diagnosis or procedure is in the general exclusions list
8. Dental claim contains an excluded dental procedure (full bill or specific line item)
9. Vision claim contains an excluded vision item (full bill or specific line item)
10. Alternative medicine system is not in the covered systems list OR practitioner is unregistered
11. MRI or CT Scan where claimed amount > ₹10,000 and no pre-authorization document is present
12. Pre-authorization was obtained but treatment date is more than 30 days after pre-auth issue date

## STEP 2 — MANUAL REVIEW TRIGGERS → decision = MANUAL_REVIEW, approved_amount = null

Route to manual review if ANY apply (do not reject, do not approve):
1. Claimed amount > ₹25,000
2. Average document confidence score < 0.4
3. Diagnosis is too ambiguous to confidently rule on exclusions or waiting periods
4. Extracted bill amount differs significantly from claimed amount (possible alteration)
5. Document shows corrections, overwritten amounts, or conflicting ORIGINAL/DUPLICATE markings
6. Member has submitted >2 claims on the same treatment date
7. Member has submitted >6 claims in the current calendar month
8. Condition involves a very long waiting period (e.g., joint replacement at 730 days) requiring human verification
9. Dependent's relationship cannot be verified against roster
10. Practitioner registration number missing or unreadable on alternative medicine claim
11. LLM extraction failed or returned null on critical fields (diagnosis, amount, date)

For MANUAL_REVIEW: your reason must be an exceptionally detailed trace. List every ambiguity,
every missing piece, every conflicting signal — the ops person picking this up must understand
exactly what stopped automated adjudication and what they should verify manually.

## STEP 3 — AMOUNT CALCULATION (all other cases → APPROVED or PARTIAL)

Compute the payable amount in this exact order:

1. Start with claimed_amount
2. Cap at category sub-limit:
   - consultation: ₹2,000 | diagnostic: ₹10,000 | pharmacy: ₹15,000
   - dental: ₹10,000 | vision: ₹5,000 | alternative_medicine: ₹8,000
3. Cap at per-claim limit: ₹5,000
4. Apply co-pay: amount_after_copay = capped_amount × (1 − copay_percent / 100)
   - consultation: 10% | all others: 0% (except pharmacy branded drugs — see below)
5. For PHARMACY with branded drugs: apply 30% co-pay on the branded drug portion only
6. If is_network_hospital = true, apply network discount:
   approved = amount_after_copay × (1 − network_discount_percent / 100)
   - consultation network discount: 20% | diagnostic: 10%
7. For mixed dental/vision bills: sum only the covered line items before applying caps

Decision based on final amount:
- approved_amount < claimed_amount → PARTIAL
- approved_amount ≥ claimed_amount → APPROVED

## CONFIDENCE SCORE (start at 1.0, deduct, clamp to [0.0, 1.0])
- −0.2 if average document confidence < 0.6
- −0.1 if diagnosis is ambiguous or partially legible
- −0.2 if member was not found in the roster
- −0.1 if any hard rule required an inference rather than a clear stated fact
- −0.1 if treatment facility is out-of-network (informational, not a rejection reason)

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
  - Initial waiting period (30 days)
  - Condition-specific waiting period (if diagnosis matches a specific condition)
  - Exclusion check (diagnosis/procedure vs exclusions list)
  - Pre-authorization check (if MRI/CT/PET or high-value surgical)
  - Document confidence check
  - Amount > ₹25,000 manual review threshold
  - Fraud signals (same-day claims, monthly volume) — note if unknown
  - Category sub-limit cap
  - Per-claim limit cap (₹5,000)
  - Co-pay calculation
  - Network discount (if applicable)
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


def _is_network_hospital(policy: dict, extracted_documents: list) -> bool:
    network = [h.lower() for h in policy.get("network_hospitals", [])]
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

    member = _get_member(policy, member_id)
    days_since_joining: Optional[int] = None
    join_date_str: Optional[str] = None
    if member and member.get("join_date"):
        join_date_str = member["join_date"]
        join_date = datetime.strptime(join_date_str, "%Y-%m-%d").date()
        days_since_joining = (date.today() - join_date).days

    avg_confidence = _avg_doc_confidence(extracted_documents)
    network_hospital = _is_network_hospital(policy, extracted_documents)
    policy_category_key = _CATEGORY_MAP.get(claim_category, claim_category.lower())
    category_rules = policy.get("opd_categories", {}).get(policy_category_key, {})
    coverage = policy.get("coverage", {})
    family_floater = coverage.get("family_floater", {})

    human_content = f"""## Claim Details
- Member ID: {member_id}
- Claim Category: {claim_category}
- Claimed Amount: ₹{claimed_amount}
- Today's Date: {state['today_date']}

## Member Details
{json.dumps(member, indent=2, ensure_ascii=False) if member else "Member not found in roster."}

## Pre-computed Context
- Days since member joined (from today): {days_since_joining if days_since_joining is not None else "Unknown (member not in roster)"}
- Member join date: {join_date_str or "Unknown"}
- Is network hospital/lab/pharmacy: {network_hospital}
- Average document confidence score: {avg_confidence}

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

## Extracted Document Data
{_docs_summary(extracted_documents)}

---

Using the policy reference in your system prompt and all claim context above:
1. Work through EVERY applicable rule in sequence (Step 1 → Step 2 → Step 3).
2. Write the `reason` as a numbered checklist — one line per rule evaluated, each ending with — PASS or — FAIL.
3. If any Step 1 rule FAILs, stop there and return REJECTED.
4. If any Step 2 trigger fires, return MANUAL_REVIEW with an exhaustive trace in `reason`.
5. Otherwise, compute the approved amount step-by-step and return APPROVED or PARTIAL.
"""

    structured_llm = chat_llm.with_structured_output(ClaimDecision)
    messages = [ 
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]

    print("\nRunning claims adjudication...")
    decision: ClaimDecision = structured_llm.invoke(messages)

    print("\n--- Claim Decision ---")
    print(f"  Decision        : {decision.decision}")
    if decision.approved_amount is not None:
        print(f"  Approved Amount : ₹{decision.approved_amount:.2f}")
    else:
        print("  Approved Amount : N/A (manual review required)")
    print(f"  Confidence      : {decision.confidence_score:.2f}")
    print(f"  Reason:\n{decision.reason}")

    return {
        **state,
        "claim_decision": decision,
    }
