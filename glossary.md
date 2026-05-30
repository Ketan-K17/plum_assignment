# Health Insurance Policy — Complete Glossary
> Every term from `policy_terms.json` explained for a first-time reader, with notes on how each affects your claims processing workflow.

---

## Top-Level Policy Fields

### `policy_id`
A unique identifier for this specific policy contract. Think of it like an invoice number — it uniquely identifies this exact policy document among potentially thousands.

**Workflow impact:** Use this as a reference key when logging claim decisions. Every trace output should reference which policy was used to evaluate the claim, so ops teams can audit it later.

---

### `policy_name`
A human-readable label for the policy type. "Group Health Insurance — Standard Plan" means this policy covers a group of people (a company's employees) under one contract, as opposed to an individual retail policy.

**Workflow impact:** Purely informational. Display it in the UI and trace output for clarity.

---

### `insurer`
The insurance company that actually underwrites and pays out the claims — in this case ICICI Lombard. The policyholder (TechCorp) pays premiums to them; ICICI Lombard is liable for payouts.

**Workflow impact:** Informational. Relevant if you ever need to route pre-authorization requests or escalations to the insurer.

---

## `policy_holder` Block

### `company_name`
The employer who purchased this group policy for their employees. Employees are covered because their company enrolled them — they are not individual policyholders.

**Workflow impact:** Informational. Helps ops identify which company's policy is being evaluated.

---

### `employee_count`
Total number of employees enrolled under this policy. 500 in this case.

**Workflow impact:** Not directly used in claim evaluation, but useful for fraud detection at scale (e.g. if claims volume suddenly spikes way beyond what 500 employees would generate).

---

### `policy_start_date` and `policy_end_date`
The period during which the policy is active — 01 Apr 2024 to 31 Mar 2025. Claims for treatments outside this window are invalid.

**Workflow impact:** Every claim must pass this check — treatment date must fall within these two dates. If a member submits a claim for a treatment that happened before the policy started or after it ended, reject immediately.

---

### `renewal_status`
Whether the policy is currently active or has lapsed. "ACTIVE" means claims can be processed. "LAPSED" or "EXPIRED" would mean no claims are payable.

**Workflow impact:** Check this before processing any claim. If status is not ACTIVE, reject with a clear message.

---

## `coverage` Block

### `sum_insured_per_employee`
The maximum total amount the insurer will pay out for one employee across the entire policy year — ₹5,00,000 here. This is the ceiling for all claims combined for that member.

**Workflow impact:** You'd need to track cumulative approved amounts per member across all their claims in the policy year. If a new claim would push them over this limit, it gets partially approved or rejected. (For this assignment, the test cases likely won't hit this ceiling, but the logic should exist.)

---

### `annual_opd_limit`
OPD stands for **Outpatient Department** — treatments where the patient is not admitted to a hospital (consultations, pharmacy, diagnostics, dental, vision, alternative medicine all fall under OPD). This sets a ₹50,000 annual cap across all OPD claims for one member.

**Workflow impact:** Similar to sum insured — track cumulative OPD spend per member. A new OPD claim that would breach ₹50,000 gets capped or rejected.

---

### `per_claim_limit`
The maximum the insurer will pay for any single claim — ₹5,000 here. Even if the bill is ₹8,000, the payout is capped at ₹5,000.

**Workflow impact:** After calculating the approved amount using all other rules, cap it at ₹5,000. Anything above becomes a PARTIAL decision, with the member bearing the difference.

---

### `family_floater`
A family floater means the sum insured is shared across the entire family, not per person. So if EMP001 has a ₹1,50,000 family floater, that pool is shared between Rajesh, his spouse Sunita, and child Arjun.

**Workflow impact:** When a dependent files a claim, deduct from the family's shared pool, not just the individual's. Check `combined_limit` and `covered_relationships` to validate that the claimant's relationship type is eligible.

---

### `covered_relationships`
Lists which family members are covered under the floater: SELF, SPOUSE, CHILDREN, PARENTS.

**Workflow impact:** When a dependent submits a claim, check their `relationship` field in the member roster against this list. If relationship is not in this list, reject.

---

## `opd_categories` Block

### `sub_limit`
A cap specific to one category of OPD claim. For example, pharmacy has a ₹15,000 sub-limit — even if the annual OPD limit hasn't been hit, pharmacy claims stop being paid after ₹15,000 for the year.

**Workflow impact:** Track spend per category per member per year. Apply the sub-limit as a ceiling before the overall OPD limit check.

---

### `copay_percent`
Co-pay is the portion of the bill the member must pay out of pocket, with the insurer covering the rest. A 10% co-pay on a ₹1,000 consultation means the member pays ₹100 and the insurer pays ₹900.

**Workflow impact:** After determining the eligible claim amount, deduct the co-pay percentage. The approved payout = eligible amount × (1 - copay_percent/100).

---

### `network_discount_percent`
If the treatment was at a hospital in the insurer's network (listed under `network_hospitals`), an additional discount is applied to the bill before processing. This is a benefit for using preferred providers.

**Workflow impact:** Check if the hospital name extracted from the document matches any entry in `network_hospitals`. If yes, apply the discount to the bill amount before evaluating the claim. If no match, no discount.

---

### `requires_prescription`
Whether a valid doctor's prescription is mandatory for this claim type to be processed.

**Workflow impact:** Part of your document verification gate. If this is true and no prescription is uploaded, stop the claim immediately and tell the member exactly what's missing.

---

### `requires_pre_auth`
Whether the member needs to get approval from the insurer *before* undergoing the treatment. Pre-auth is like getting permission in advance.

**Workflow impact:** If true, your system should check whether a pre-authorization document was submitted. Without it, the claim gets rejected or flagged for manual review.

---

### `pre_auth_threshold`
For diagnostics, pre-auth is only required if the amount exceeds this threshold (₹10,000). Below this, no pre-auth needed.

**Workflow impact:** For DIAGNOSTIC claims, compare extracted bill amount against this threshold. Only enforce pre-auth requirement if amount is above it.

---

### `high_value_tests_requiring_pre_auth`
Specific tests (MRI, CT Scan, PET Scan) that always need pre-auth if above the threshold, regardless of other rules.

**Workflow impact:** Extract the test name from the lab report or bill. If it matches any of these three, check that pre-auth was obtained and that the amount is above the threshold.

---

### `branded_drug_copay_percent`
For pharmacy claims, branded (non-generic) drugs attract a higher 30% co-pay. Generic drugs have 0% co-pay.

**Workflow impact:** Extract each medicine from the pharmacy bill. Determine if it's branded or generic. Apply 30% co-pay to branded drug amounts, 0% to generic. Sum up the final payout accordingly.

---

### `generic_mandatory`
The policy requires generic drugs to be dispensed where available. If a branded drug was prescribed when a generic equivalent exists, it may not be fully covered.

**Workflow impact:** This is hard to enforce without a drug database, so in practice you'd flag it as a low-confidence extraction and possibly route to MANUAL_REVIEW if the bill shows clearly branded expensive drugs.

---

### `requires_dental_report`
A dental-specific document requirement — a report from the dentist detailing the procedure performed.

**Workflow impact:** Add this to the document gate for DENTAL claims. If missing, stop and ask the member for it specifically.

---

### `covered_procedures` (Dental)
An explicit whitelist of dental procedures the policy covers.

**Workflow impact:** Extract the procedure name from the dental bill or report. Check it against this list. If not found, reject with a specific message naming the procedure and stating it isn't covered.

---

### `excluded_procedures` (Dental)
An explicit blacklist of dental procedures that are never covered — cosmetic work essentially.

**Workflow impact:** Check extracted procedure against this list first. If matched, reject immediately before any other rules.

---

### `covered_items` (Vision)
Whitelist of vision-related items the policy pays for — glasses, contact lenses, eye exam, cataract surgery.

**Workflow impact:** Extract the item/procedure from the bill. Must match this list for the claim to proceed.

---

### `excluded_items` (Vision)
LASIK, cosmetic eye surgery, and refractive surgery are never covered.

**Workflow impact:** If extracted item matches any of these, reject immediately.

---

### `requires_registered_practitioner` (Alternative Medicine)
The practitioner must be officially registered — a random person calling themselves an Ayurveda practitioner doesn't qualify.

**Workflow impact:** Extract the practitioner's registration number from the prescription. If absent or unverifiable, flag as low confidence or route to MANUAL_REVIEW.

---

### `max_sessions_per_year` (Alternative Medicine)
Only 20 alternative medicine sessions are covered per year per member.

**Workflow impact:** Track session count per member across all alternative medicine claims in the policy year. If this claim would push them past 20, reject or partially approve.

---

### `covered_systems` (Alternative Medicine)
Only these systems of medicine qualify: Ayurveda, Homeopathy, Unani, Siddha, Naturopathy.

**Workflow impact:** Extract the type of treatment from the prescription or bill. If it doesn't match one of these five, reject.

---

## `waiting_periods` Block

### `initial_waiting_period_days`
Every new member must wait 30 days from their join date before any claim can be processed. This prevents people from joining a policy only when they're already sick.

**Workflow impact:** For every claim, calculate: `treatment_date - member.join_date`. If less than 30 days, reject with "initial waiting period not completed."

---

### `pre_existing_conditions_days`
If a member had a medical condition before joining the policy, claims related to that condition are blocked for 365 days. The policy assumes any condition diagnosed within the first year may have pre-existed.

**Workflow impact:** This is harder to enforce automatically since you'd need to know the member's medical history. In practice, flag diagnoses of chronic conditions in the first year for MANUAL_REVIEW.

---

### `specific_conditions` waiting periods
Certain conditions have their own waiting periods regardless of whether they're pre-existing:

| Condition | Wait |
|-----------|------|
| Diabetes | 90 days |
| Hypertension | 90 days |
| Thyroid Disorders | 90 days |
| Joint Replacement | 730 days |
| Maternity | 270 days |
| Mental Health | 180 days |
| Obesity Treatment | 365 days |
| Hernia | 365 days |
| Cataract | 365 days |

**Workflow impact:** Extract diagnosis from documents. Map diagnosis to condition (e.g. "HTN" → Hypertension, "T2DM" → Diabetes). Look up waiting period. Check if `treatment_date - join_date >= waiting_period_days`. If not, reject.

---

## `exclusions` Block

### `conditions`
A flat list of things the policy never covers under any circumstances — no waiting period applies, no exceptions. Self-inflicted injuries, cosmetic procedures, experimental treatments etc.

**Workflow impact:** Extract diagnosis and procedure from documents. Check against this list. If matched, reject immediately with the specific exclusion reason.

---

### `dental_exclusions` and `vision_exclusions`
Category-specific exclusion lists that mirror what's in the OPD category rules.

**Workflow impact:** Same as above — check extracted procedure/item against these lists as a hard stop before any other evaluation.

---

## `pre_authorization` Block

### `required_for`
The list of treatments that need insurer approval before the treatment happens. If someone got an MRI and didn't get pre-auth first, the claim may be denied.

**Workflow impact:** Check extracted test/procedure name against this list. If matched and no pre-auth document is present in the submission, reject or flag for MANUAL_REVIEW depending on your design.

---

### `validity_days`
A pre-auth approval is only valid for 30 days from the date it was issued. If the treatment happened after this window, the pre-auth is expired and effectively counts as no pre-auth.

**Workflow impact:** Extract pre-auth issue date (if document is present). Check: `treatment_date - preauth_date <= 30 days`. If not, treat as missing pre-auth.

---

## `network_hospitals`

A list of 10 hospitals that have a preferred provider arrangement with the insurer. Treatments at these hospitals attract additional discounts.

**Workflow impact:** Extract hospital name from the bill. Fuzzy-match it against this list (names may not match exactly — "Apollo" vs "Apollo Hospitals"). If matched, apply the relevant `network_discount_percent` for that category.

---

## `submission_rules` Block

### `deadline_days_from_treatment`
Members must submit their claim within 30 days of the treatment date. Late submissions are rejected.

**Workflow impact:** Compare `submission_date` (when the member filed the claim) against `treatment_date` extracted from documents. If difference > 30 days, reject with "submission deadline exceeded."

---

### `minimum_claim_amount`
Claims below ₹500 are not worth processing and are rejected outright.

**Workflow impact:** After extracting the bill total, check if it meets this minimum. Reject early if not.

---

### `currency`
All amounts are in INR. Any document showing amounts in another currency would be anomalous.

**Workflow impact:** Flag claims where extracted amounts appear to be in a foreign currency as suspicious or for MANUAL_REVIEW.

---

## `fraud_thresholds` Block

### `same_day_claims_limit`
A member should not be submitting more than 2 claims for treatments on the same date. More than that is suspicious.

**Workflow impact:** Check claim history for the member — how many other claims have the same treatment date? If > 2, flag for MANUAL_REVIEW and increase fraud score.

---

### `monthly_claims_limit`
No more than 6 claims in a calendar month per member.

**Workflow impact:** Count claims submitted by this member in the current month. If this claim would be the 7th or more, flag for MANUAL_REVIEW.

---

### `high_value_claim_threshold`
Any single claim above ₹25,000 automatically gets extra scrutiny.

**Workflow impact:** If extracted bill total > ₹25,000, route directly to MANUAL_REVIEW regardless of other checks passing.

---

### `auto_manual_review_above`
Confirms the above — ₹25,000 is the hard threshold for automatic manual review routing.

**Workflow impact:** Same as above. This is a hard rule, not a soft flag.

---

### `fraud_score_manual_review_threshold`
Your system should compute a fraud score (0.0 to 1.0) based on various signals — document alterations, amount mismatches, unusual claim patterns etc. If this score hits 0.80 or above, route to MANUAL_REVIEW.

**Workflow impact:** Design a fraud scoring function that accumulates signals. Each red flag adds to the score. Once it crosses 0.80, override the decision to MANUAL_REVIEW.

---

## `members` Block

### `member_id`
Unique identifier for each person covered — employees are EMP001–EMP010, dependents are DEP001 onwards.

**Workflow impact:** The member ID is the first thing the user provides in a claim submission. Look them up here. If not found, reject immediately — unknown member.

---

### `date_of_birth`
Member's date of birth. Used to compute age, which can be relevant for age-specific conditions or pediatric claims.

**Workflow impact:** Compute age at time of treatment. Some conditions or treatments may have age-based rules (not explicitly in this policy, but good to have for extensibility).

---

### `relationship`
Whether the person is an employee (SELF) or a dependent (SPOUSE, CHILD, PARENTS).

**Workflow impact:** Dependents must be validated against `covered_relationships` in the family floater block. Their claims draw from the family pool, not just the employee's individual limit.

---

### `join_date`
The date this member was enrolled in the policy. Critical for all waiting period calculations.

**Workflow impact:** Every waiting period check uses this date as the starting point. `days_elapsed = treatment_date - join_date`.

---

### `dependents`
List of dependent member IDs linked to an employee.

**Workflow impact:** When a dependent files a claim, trace back to their primary member to access the family floater pool and policy terms.

---

### `primary_member_id`
On a dependent's record, this points back to the employee they're linked to.

**Workflow impact:** Use this to fetch the primary member's policy entitlements when processing a dependent's claim.

---

## Decision Types (Not in JSON, but defined by the assignment)

### `APPROVED`
All rules passed. Full bill amount (after co-pay and sub-limit checks) is payable.

### `PARTIAL`
Some rules passed but the payout is less than the claimed amount — due to sub-limit cap, co-pay deduction, per-claim limit, or part of the claim being excluded.

### `REJECTED`
A hard rule failed — exclusion matched, waiting period not met, wrong documents, member not found, etc.

### `MANUAL_REVIEW`
The system cannot make a confident decision — either the fraud score is high, the claim exceeds ₹25,000, document quality was too poor to extract reliably, or confidence score dropped below an acceptable threshold.