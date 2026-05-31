# Plum Health Insurance Claims API

An AI-powered OPD claims processing system built with LangGraph, FastAPI, and Claude. It walks a claimant through information collection, document verification, extraction, and adjudication — entirely via a conversational interface.

---

## Documentation Index

- **[graph.md](graph.md)** — LangGraph workflow diagram, node-by-node reference, state management, and observability setup
- **[glossary.md](glossary.md)** — Health insurance policy terms explained for first-time readers; reference for understanding `policy_terms.json`
- **[my_learnings.md](my_learnings.md)** — Post-project reflection covering architectural shortcuts, domain challenges, and what could have been done better

---

## Architecture Overview

The system has two modes of operation:

| Mode | Entry point | Use case |
|---|---|---|
| **API + Chat UI** | `uvicorn api:app` | HTTP clients, browser chat interface |
| **CLI graph** | `python graph.py` | Terminal-based interactive run |

Both modes execute the same underlying LangGraph nodes. The API externalises the interactive loops into HTTP state machines; the CLI runs them interactively in the terminal.

Observability and prompt management are handled by **Langfuse**:
- Every LLM call is traced end-to-end via the Langfuse callback handler.
- All prompts (`CLAIM_EXTRACTION_PROMPT`, `DOCUMENT_CHECKING_PROMPT`, `GENERIC_DOCUMENT_PROMPT`) are stored and versioned in Langfuse, allowing rapid iteration without code deployments.

For a detailed breakdown of the graph and each node's role, see [`graph.md`](graph.md).

---

## Prerequisites

- Python 3.11+
- A `.env` file (or environment variables) with:

```
OPENAI_API_KEY=...          # or whichever provider llms.py is configured for
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=...           # e.g. https://cloud.langfuse.com
```

---

## Installation

```bash
python -m venv plum_assignment_venv
source plum_assignment_venv/bin/activate

pip install -r requirements.txt
```

---

## Running the API server

```bash
uvicorn api:app --reload
```

The server starts at `http://localhost:8000`.

- **Chat UI** → open `http://localhost:8000` in a browser
- **Swagger docs** → `http://localhost:8000/docs`

---

## Running the CLI graph

```bash
python graph.py
```

Walks through the full claim flow interactively in the terminal — useful for development and testing individual nodes.

---

## API Usage

The claim flow follows four sequential stages. All endpoints are prefixed with `/claims`.

### 1. Create a session

```
POST /claims/session
```

Returns a `session_id` that must be passed to all subsequent calls.

**Response**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Session created. Please describe your claim."
}
```

---

### 2. Describe the claim (one or more turns)

```
POST /claims/{session_id}/message
Content-Type: application/json

{ "text": "I want to claim ₹2500 for a consultation. My employee ID is EMP003." }
```

The endpoint extracts `member_id`, `claim_category`, and `claimed_amount` from the conversation. If any field is missing, it returns a reply asking for what's still needed. Keep sending messages until the status is `ready`.

**Response — still collecting**
```json
{
  "status": "collecting_info",
  "reply": "I still need the following to process your claim:\n  - claimed amount in ₹",
  "session_id": "..."
}
```

**Response — validation failed**
```json
{
  "status": "rejected",
  "reply": "Claimed amount ₹200 is below the minimum limit of ₹500. Claim rejected.",
  "session_id": "..."
}
```

**Response — all info collected**
```json
{
  "status": "ready",
  "reply": "Got it! Here's what I've collected:\n  Member ID: EMP003\n  Claim Type: CONSULTATION\n  Claimed Amount: ₹2500\n\nPlease upload your supporting documents to proceed.",
  "session_id": "..."
}
```

**Early rejection rules (checked before document upload):**
- Member ID not on the roster → `REJECTED`
- Claimed amount < ₹500 → `REJECTED`

---

### 3. Upload documents

```
POST /claims/{session_id}/documents
Content-Type: multipart/form-data

files: <file1>, <file2>, ...
```

The LLM inspects the uploaded images/PDFs and identifies which required document types they satisfy. Required documents vary by claim category:

| Category | Required documents |
|---|---|
| CONSULTATION | PRESCRIPTION, HOSPITAL_BILL |
| DIAGNOSTIC | PRESCRIPTION, LAB_REPORT, HOSPITAL_BILL |
| PHARMACY | PRESCRIPTION, PHARMACY_BILL |
| DENTAL | HOSPITAL_BILL |
| VISION | PRESCRIPTION, HOSPITAL_BILL |
| ALTERNATIVE_MEDICINE | PRESCRIPTION, HOSPITAL_BILL |

**Response — documents still missing**
```json
{
  "status": "awaiting_documents",
  "verified_so_far": ["PRESCRIPTION"],
  "still_missing": ["HOSPITAL_BILL"],
  "message": "Received and verified: PRESCRIPTION.\nStill needed: HOSPITAL_BILL. Please upload the remaining documents."
}
```

**Response — all documents received**
```json
{
  "status": "processing",
  "verified_documents": ["PRESCRIPTION", "HOSPITAL_BILL"],
  "message": "All required documents verified. Processing has started — poll GET /claims/{session_id}/status for updates."
}
```

You can upload documents in multiple batches. Previously verified documents are remembered across calls.

---

### 4. Poll for status

```
GET /claims/{session_id}/status
```

Returns the current session state. Poll this endpoint while `status` is `processing`.

**Possible status values:**

| Status | Meaning |
|---|---|
| `collecting_info` | Waiting for claim details via `/message` |
| `ready` | Info collected, waiting for document upload |
| `awaiting_documents` | Some documents still missing |
| `processing` | Background adjudication running |
| `complete` | Decision ready |
| `rejected` | Claim rejected at an earlier stage |
| `error` | Unhandled processing error |

---

### 5. Get the verdict

```
GET /claims/{session_id}/verdict
```

Only available when status is `complete` or `rejected`.

**Response**
```json
{
  "session_id": "...",
  "verdict": "PARTIAL",
  "approved_amount": 1800.0,
  "confidence_score": 0.85,
  "reason": "1. Policy period check: treatment date 2024-11-10 within 2024-04-01–2025-03-31 — PASS\n2. ..."
}
```

**Possible verdict values:**

| Verdict | Meaning |
|---|---|
| `APPROVED` | Full claimed amount approved |
| `PARTIAL` | Approved amount is less than claimed (sub-limit, co-pay, or network discount applied) |
| `REJECTED` | Claim does not meet policy terms |
| `MANUAL_REVIEW` | Flagged for human review (high value, low document confidence, fraud signals, etc.) |

---

## Policy Rules (summary)

The adjudication engine enforces the full `PLUM_GHI_2024` policy (ICICI Lombard General Insurance, policy period 2024-04-01 to 2025-03-31):

- **Sum insured**: ₹5,00,000 per employee; ₹1,50,000 family floater
- **Annual OPD limit**: ₹50,000; **per-claim cap**: ₹5,000
- **Waiting periods**: 30-day initial, 365-day pre-existing, condition-specific waits for diabetes, hypertension, maternity, and others
- **Exclusions**: cosmetic procedures, LASIK, orthodontic treatment, weight loss, substance abuse, infertility, and others
- **Fraud thresholds**: claims > ₹25,000 or >2 claims on the same day route to `MANUAL_REVIEW`
- **Pre-auth**: required for MRI/CT/PET scans above ₹10,000

Full policy terms are in [`policy_terms.json`](policy_terms.json).

---

## Valid member IDs (for testing)

```
EMP001 – EMP010   (employees)
DEP001, DEP002    (dependents)
```

---

## Project structure

```
.
├── api.py                  # FastAPI app and HTTP endpoints
├── graph.py                # LangGraph graph definition and CLI entry point
├── state.py                # ClaimState TypedDict and ClaimVerdictEnum
├── classify_claim.py       # ClaimClassification Pydantic model
├── document_checking.py    # document_checking_node + DocumentVerification model
├── document_processing.py  # document_processing_node — field extraction per doc type
├── document_models.py      # Per-document Pydantic schemas (PRESCRIPTION, HOSPITAL_BILL, etc.)
├── decision_making.py      # decision_making_node — full adjudication logic + policy prompt
├── share_verdict.py        # share_verdict_node — terminal output (CLI mode only)
├── langfuse_utils.py       # Langfuse client and callback handler setup
├── llms.py                 # LLM client initialisation
├── utils.py                # File encoding helpers
├── policy_terms.json       # Structured policy reference consumed by decision_making_node
├── static/
│   └── index.html          # Single-file chat UI served by FastAPI
└── uploads/                # Uploaded documents saved here per session
```
