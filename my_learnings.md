# My Learnings — Plum Health Insurance Claims API

## Overview

This document reflects on the development of an AI-powered OPD claims processing system built with LangGraph, FastAPI, and Claude. The project involved building a complete workflow to handle insurance claim adjudication against a complex policy ruleset. This is an honest assessment of what I cut, what I could have done better, and the challenges I faced.

---

## 1. Corners Cut Due to Time Constraints

### Incomplete Langfuse Integration

I needed to externalize **all prompts** to Langfuse and wire tracing for every node in the workflow, but I didn't prioritize this. 

**What I did:** I set up Langfuse tracing for the `classify_claim_node`, but left the later nodes (`document_checking`, `document_processing`, `decision_making`) with prompts hardcoded in Python rather than fetched from Langfuse at runtime.

**Why this matters:** The whole point of Langfuse is to decouple prompt management from code deployment. By shipping prompts embedded in the source, I made it harder to iterate quickly and eliminated the ability to version-control prompt changes separately from code changes.

**Reality check:** This functionality already existed in earlier nodes. Extending it to the remaining nodes was purely mechanical work — duplicating the fetch pattern and wrapping each node's system prompt in a Langfuse abstraction. I chose not to do it because it felt like a chore, not core functionality. For a POC that's understandable, but it left technical debt that would have to be paid down before production.

---

## 2. Architectural Shortcuts — The Policy Terms Decision

### Ingest Entire Policy as LLM Context Instead of an LLM Tool

I had to decide how to feed the `policy_terms.json` file (7.8 KB, ~130 fields covering sub-limits, exclusions, waiting periods, fraud thresholds) into the decision-making node.

**What I chose:** I serialized the entire JSON into the system prompt of `decision_making_node`, passing it directly to the agent as part of the LLM context.

**What I could have done:** Model `policy_terms.json` as an **LLM tool** that the model could query. Instead of "here's the entire policy," I'd let the agent call a function like `get_policy_rule(rule_name, member_id)` to fetch only the rules it needs to evaluate the claim.

**Why this matters:** The LLM approach wastes context window. A claim only needs a handful of rules evaluated (policy period, waiting period, category sub-limit, exclusions relevant to the diagnosis), but I'm forcing the model to see the entire ruleset for every claim. A tool-based approach would let the model decide what to ask for, keeping its context budget for more important things — like the extracted document data and reasoning.

**The honest assessment:** Given the size of the policy and the scope of a POC, embedding it in the prompt was the fastest path to a working system. But it's a classic engineer's trap: the easy thing now becomes the regrettable thing later. Scaling to multi-policy systems or larger rulesets would expose this choice as a mistake.

---

## 3. Shortcomings of My Approach

### Reasoning Matters, But I Used It Too Broadly

The core problem: **I'm using the LLM to evaluate conditions that could be evaluated in code.**

**Example:** The policy says "Initial waiting period is 30 days from policy start. If the treatment date is within the first 30 days, reject." I could have written this as three lines of Python:

```python
policy_start = datetime(2024, 4, 1)
treatment_date = parse_date(extracted_documents[0].treatment_date)
if (treatment_date - policy_start).days < 30:
    reject("Within initial waiting period")
```

Instead, I'm asking the agent to evaluate it as part of the decision-making workflow, even though it's a deterministic rule with no ambiguity.

**Where this breaks down:**

1. **Latency** — agent invocation adds 1–2 seconds. A local check takes milliseconds.
2. **Cost** — Each LLM call costs tokens. Deterministic rules are free in code.
3. **Reliability** — The LLM could hallucinate or misread the dates. Code is verifiable.
4. **Debuggability** — If an LLM decision is wrong, I'm reverse-engineering its reasoning. If code is wrong, I'm reading the condition.

**The model should handle:**
- Ambiguous cases (e.g., "is this diagnosis on the exclusion list?" when the diagnosis is fuzzy or spelled wrong)
- Trade-offs (e.g., applying network discounts, deciding between multiple sub-limits)
- Open-ended reasoning (e.g., flagging a claim for manual review based on consistency between documents)

**The model should NOT handle:**
- Deterministic date comparisons
- Enum matching (diagnosis vs. exclusion list)
- Arithmetic that's already been done

I mixed these carelessly. The decision_making node does both, but I didn't clearly separate them.

---

## 4. What I Could Have Done Better

### Better Ingestion of Policy Terms

**Current approach:** Serialize the entire `policy_terms.json` into the system prompt.

**Better approach (and why I didn't do it):**

1. **Load policy_terms as an LLM tool:** Define a function `query_policy(member_id, rule_category, member_status)` that the LLM can invoke to fetch contextual rules. This reduces context bloat and forces the model to explicitly state which rules it's checking.
   
   *Didn't do it because:* It requires wrapping the JSON in function schemas and teaching the LLM to call it. Faster to just paste the JSON.

2. **Pre-filter rules in code:** Before invoking the LLM, extract the rules relevant to this specific claim (claim category → OPD sub-limits; diagnosis → exclusion check; member status → waiting period applicability). Pass only those rules to the prompt.
   
   *Didn't do it because:* It requires analyzing `policy_terms.json` upfront and building a lookup structure. The JSON wasn't designed for programmatic querying — it's flat and context-dependent.

3. **Separate rules into code vs. reasoning:** Move deterministic rule evaluation (date checks, amount caps, waiting period arithmetic) into the document_processing and decision_making nodes as code. Ask the LLM only for judgment calls (is this bill suspicious? does this diagnosis match the treatment date?).
   
   *Didn't do it because:* It requires re-architecting the decision-making node to have a hybrid code+reasoning flow. The current approach (all reasoning via LLM) is simpler to build, even if it's less efficient.

**The trade-off I made:** Simplicity of implementation vs. efficiency and clarity. For a POC, simple wins. For production, the other choices would be better.

---

### Insufficient Separation of Concerns in Decision Making

The `decision_making_node` does three things:

1. Check hard rejections (date out of policy period → immediate reject)
2. Check manual review triggers (document confidence too low → flag for human)
3. Calculate approved amount (apply sub-limits, co-pays, discounts)

These are logically separate but implemented as a monolithic LLM call. A cleaner design would:

- Run hard rejections in code (no LLM needed — they're deterministic)
- Send only ambiguous cases to the LLM for manual review flagging and amount calculation

**Why I didn't refactor:** By the time I realized this, the node was working. Refactoring mid-project to extract code-only logic felt risky (could break existing decisions). A greenfield build would benefit from this structure from day one.

---

## 5. Difficulties Faced During Development

### Domain Knowledge Gap — Health Insurance is Unfamiliar Territory

This was the biggest slow-down, and I'll be frank: I shamefully underestimated how much time I'd need to understand the domain.

**The problem:** Health insurance has its own jargon, and almost every term matters for correct implementation:

- **OPD vs. IPD:** I didn't immediately know that "OPD" meant outpatient (no hospital admission) and it was a distinct category with its own annual limit.
- **Waiting period, pre-existing condition, waiting period override:** These are interconnected concepts that don't exist outside insurance. I had to read through `policy_terms.json`, the glossary I wrote, and the assignment document multiple times before the model made sense.
- **Sub-limits, co-pays, network discounts:** Each is a separate calculation that compounds with others. I built the logic, but the first draft didn't handle their interaction correctly.
- **Sum insured vs. annual OPD limit:** Easily confused. One is a yearly cap; one is a per-employee ceiling for the entire policy year.

**The evidence:** I decided to read up a glossary (glossary.md) trying to explain every term from first principles. That document exists because I had to build my understanding from scratch, and I wanted to ensure I'd never re-learn it.

### Complexity of Multi-Condition Logic

The decision_making_node evaluates ~20 different conditions:

- Policy period validation (treatment date in-window?)
- Waiting periods (30-day initial, 365-day pre-existing, condition-specific)
- Exclusions (is this diagnosis/procedure on the exclusion list?)
- Sub-limits (did the OPD category-specific cap get hit?)
- Fraud thresholds (>2 claims same day? >6 claims in a month?)
- Pre-authorization (was this scan pre-approved? Did approval expire?)

Each has nuances:

- Some rejections are immediate (hard rejection).
- Some require human review (manual review triggers).
- Some affect the payout amount (caps, discounts).

**The challenge:** Encoding all of this in an LLM prompt without contradictions, without missing edge cases, and without overshadowing the main logic. The current approach works, but the prompt is long and somewhat repetitive. I could have simplified it by moving more logic to code, but that wasn't obvious during development.

### Scaffolding and Testing Without a Database

I don't have a real database of member rosters, claim history, or policy assignment. Testing required me to:

- Hard-code a list of valid member IDs (EMP001–EMP010, DEP001–DEP002)
- Generate a random "today_date" within the policy window at session creation, since I have no per-member history to check cumulative claims against
- Build test documents myself or use placeholder data

This made it hard to test realistic scenarios like:

- A member hitting their annual OPD limit after multiple claims
- Duplicate claims on the same date (fraud signal)
- Family floaters where multiple dependents are pulling from a shared pool

**In production:** These would require database queries and complex state management. For a POC, I sidestepped them, which is fine, but it means the system hasn't been battle-tested against multi-claim member profiles.

### Integrating LLM Extraction with Pydantic Validation

Early in development, I built structured output schemas for each document type (PRESCRIPTION, HOSPITAL_BILL, etc.) and used Pydantic to validate LLM responses. This worked, but it was fragile:

- If the LLM returned a field in slightly the wrong format (e.g., "2024-11-15" instead of "2024-11-15T00:00:00"), Pydantic would reject the whole response.
- I had to iterate on the prompt to encourage the LLM to match the schema exactly.
- Fallback logic (what to do if the LLM can't extract a required field) was minimal — I mostly just set confidence to 0.0.

**Better approach:** Build a parsing layer that's more forgiving. Extract what you can, flag what you can't, and let the decision-making node decide how to weight missing fields. This would reduce back-and-forth with the LLM.

---

## Key Takeaways

1. **Use the LLM for judgment, not arithmetic.** Hard rules belong in code. Let the model reason about ambiguity.

2. **Externalize mutable logic early.** Langfuse, config files, rule engines — they're not optional extras. Bake them in from the start, even if the POC doesn't need them yet.

3. **Invest in domain understanding upfront.** I spent 3–4 hours learning insurance jargon. That's normal for unfamiliar domains. Budget for it, don't resent it.

4. **Separate hard rejections from soft checks.** Code for deterministic rules; LLM for judgment calls. The architecture is clearer, the performance is better.

5. **Test the full loop early.** I didn't discover architectural issues until late because I was focused on getting one node working at a time. Running end-to-end claims sooner would have surfaced the "context bloat from embedded policy terms" problem earlier.

---

## In Production, I Would

- [ ] Move policy term evaluation to a tool-based approach or a separate rule engine
- [ ] Extract deterministic rule checks (date comparisons, amount caps) into code
- [ ] Wire Langfuse tracing for all nodes, not just classify_claim
- [ ] Build a parsing layer for document extraction that degrades gracefully
- [ ] Add a member database with claim history to test cumulative limits and fraud signals
- [ ] Separate hard rejections from manual review triggers in the decision_making node
- [ ] Document the decision logic more explicitly (it's currently implicit in the LLM prompt)
