import pypandoc

content = r"""# AI Support-Ops Pipeline — Design Specification

**Document:** `spec.md`  
**Version:** 1.0  
**Status:** Design baseline  
**Language/runtime:** Python 3.12+ (recommended)  
**Primary inputs:** `tickets.json`, `kb_articles.json`

## 1. Purpose and design goals

Build a replayable, auditable pipeline that ingests support tickets and help-center articles from disk, normalises multilingual ticket text, classifies intent and urgency, retrieves relevant knowledge-base (KB) guidance, computes deterministic priority scores, routes tickets to internal queues, drafts safe replies for human review, and validates the resulting artifacts.

The implementation must run from a clean checkout and regenerate outputs from the current input files. It must not depend on sample ticket IDs, input ordering, hardcoded ticket-to-article mappings, or precomputed outputs.

### 1.1 Core principles

- **Stage separation:** each pipeline stage has a defined input, output, and responsibility.
- **Replayability:** the same inputs and configuration should produce the same deterministic outputs, except for explicitly identified LLM-generated content and timestamps.
- **Traceability:** retain intermediate artifacts and log every required LLM call.
- **Controlled vocabularies:** validate all model-generated category fields against enums.
- **Deterministic priority:** calculate priority in Python using the specified formula.
- **Safe drafting:** drafts are not sent automatically; human review is required.
- **Input-driven retrieval:** retrieve from the supplied `kb_articles.json` using a reproducible algorithm.
- **Fail visibly:** invalid schemas, missing files, malformed model responses, and invalid enum values must result in clear validation errors or bounded retries, not silent corruption.

## 2. High-level architecture

```text
                 +--------------------------+
                 | tickets.json             |
                 | kb_articles.json         |
                 +------------+-------------+
                              |
                              v
                    [1. Load and validate]
                              |
                              v
                    [2. Multilingual prep]
                              |
                 preprocessed_tickets.json
                              |
                              v
                 [3. Stage 1: Classification]
                              |
                  classified_tickets.json
                              |
                              v
                    [4. KB retrieval]
                              |
                   retrieval_results.json
                              |
                              v
                 [5. Deterministic scoring]
                              |
                    priority_scores.json
                              |
                              v
                   [6. Stage 2: Routing]
                              |
                   routing_decisions.json
                              |
                              v
                 [7. Stage 3: Reply drafting]
                              |
                      reply_drafts.json
                              |
                              v
                      [8. Validation]
                              |
                 validation_report.md
                              |
                              v
                      [9. Finalise]
                              |
             summary / quality notes / handoff
```

### 2.1 Suggested module layout

```text
project/
├── tickets.json
├── kb_articles.json
├── spec.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── Makefile
├── src/
│   └── support_ops/
│       ├── __init__.py
│       ├── config.py
│       ├── models.py
│       ├── vocab.py
│       ├── ingestion.py
│       ├── preprocessing.py
│       ├── classification.py
│       ├── retrieval.py
│       ├── prioritization.py
│       ├── routing.py
│       ├── drafting.py
│       ├── validate.py
│       ├── artifacts.py
│       ├── llm_client.py
│       └── pipeline.py
├── artifacts/
│   ├── preprocessed_tickets.json
│   ├── classified_tickets.json
│   ├── retrieval_results.json
│   ├── priority_scores.json
│   ├── routing_decisions.json
│   ├── reply_drafts.json
│   ├── retrieval_quality.json
│   ├── handoff_memory.json
│   ├── ops_summary.md
│   ├── validation_report.md
│   └── llm_calls.jsonl
└── tests/
    ├── test_models.py
    ├── test_retrieval.py
    ├── test_prioritization.py
    ├── test_pipeline.py
    └── fixtures/
```

The evaluator requires the named artifacts to be produced. If compatibility with an evaluator expecting files in the repository root is uncertain, write artifacts to the root by default or make `ARTIFACT_DIR` configurable and document the chosen default. The input files remain at the configured input paths.

### 2.2 Responsibility boundaries

| Component | Responsibility | Must not do |
|---|---|---|
| Ingestion | Read JSON files, validate top-level shape and required fields | Classify, route, or modify original text |
| Preprocessing | Preserve original text and create English processing text | Discard source text |
| Classification | One Stage 1 LLM call over the preprocessed batch; validate output | Assign final numeric priority |
| Retrieval | Rank articles from the loaded KB with a reproducible method | Use hardcoded ticket-to-article mappings |
| Prioritisation | Apply the specified score formula and sort deterministically | Ask an LLM to set final scores |
| Routing | One separate Stage 2 LLM call with classifications, retrieval, top-five priority context, and queue enum | Emit queues outside the allowed vocabulary |
| Drafting | One separate Stage 3 LLM call for top-five tickets only | Send customer messages or make unsupported promises |
| Validation | Check artifacts and cross-stage invariants | Silently repair invalid outputs without recording it |
| Artifact/logging | Persist JSON/Markdown and append LLM call records | Store API keys or secrets |

## 3. Stage state machine

The pipeline must advance through the following states in order:

```text
INIT
  -> TICKETS_LOADED
  -> PREPROCESSING_COMPLETE
  -> TICKETS_CLASSIFIED
  -> KB_RETRIEVAL_COMPLETE
  -> PRIORITY_SCORES_COMPUTED
  -> ROUTING_COMPLETE
  -> REPLY_DRAFTS_GENERATED
  -> VALIDATION_COMPLETE
  -> RESULTS_FINALISED
```

### 3.1 State definitions and transition contracts

| State reached | Preconditions | Work performed | Required output / postcondition |
|---|---|---|---|
| `INIT` | None | Initialise configuration, directories, logger, and run metadata | State starts at `INIT` |
| `TICKETS_LOADED` | Input paths exist | Read and parse both JSON files; validate record schemas and uniqueness of IDs | In-memory ticket and KB collections are valid |
| `PREPROCESSING_COMPLETE` | Tickets loaded | Use language hints and/or language detection; translate non-English or mixed-language text into English processing text while preserving originals | `preprocessed_tickets.json` covers every ticket |
| `TICKETS_CLASSIFIED` | Preprocessing complete | Make one Stage 1 LLM call for all preprocessed tickets; parse and validate structured response | `classified_tickets.json` has one valid record per ticket |
| `KB_RETRIEVAL_COMPLETE` | Classification complete | Retrieve top two KB articles per ticket using normalised text and classification metadata | `retrieval_results.json` contains exactly two valid article references per ticket |
| `PRIORITY_SCORES_COMPUTED` | Retrieval complete | Compute deterministic score, explain score components, sort descending, mark top five expedited tickets | `priority_scores.json` includes all tickets and top-five flags |
| `ROUTING_COMPLETE` | Priority computed | Make a separate Stage 2 LLM call using classification, top retrieval results, top-five priority context, and queue vocabulary | `routing_decisions.json` covers every ticket and uses valid queues/safety labels |
| `REPLY_DRAFTS_GENERATED` | Routing complete | Make a separate Stage 3 LLM call for top-five tickets only; attach retrieved KB citations and human review notes | `reply_drafts.json` has exactly the selected top-five ticket IDs, subject to fewer than five input tickets |
| `VALIDATION_COMPLETE` | All required prior outputs exist | Run schema, vocabulary, coverage, reference, priority, citation, and LLM-log checks | Validation results are recorded; failures are explicit |
| `RESULTS_FINALISED` | Validation executed | Write optional quality report, operations summary, handoff memory, and final report; close run | All expected outputs for the run are persisted |

### 3.2 State transition enforcement

Implement an enum such as `PipelineState` and a single transition method. Each stage should assert its required predecessor before running. A stage must not silently skip a required predecessor.

Recommended pattern:

```python
class PipelineState(str, Enum):
    INIT = "INIT"
    TICKETS_LOADED = "TICKETS_LOADED"
    PREPROCESSING_COMPLETE = "PREPROCESSING_COMPLETE"
    TICKETS_CLASSIFIED = "TICKETS_CLASSIFIED"
    KB_RETRIEVAL_COMPLETE = "KB_RETRIEVAL_COMPLETE"
    PRIORITY_SCORES_COMPUTED = "PRIORITY_SCORES_COMPUTED"
    ROUTING_COMPLETE = "ROUTING_COMPLETE"
    REPLY_DRAFTS_GENERATED = "REPLY_DRAFTS_GENERATED"
    VALIDATION_COMPLETE = "VALIDATION_COMPLETE"
    RESULTS_FINALISED = "RESULTS_FINALISED"
```

Maintain an explicit allowed-transition map. When a stage succeeds, persist its artifact first and then advance state. If a stage fails, keep the last completed artifact/state and exit non-zero; do not mark the run finalised.

### 3.3 Failure and retry policy

- Input/schema failures: fail fast with file and record context.
- LLM transport errors: retry a small configurable number of times with backoff.
- Invalid structured LLM output: attempt a bounded repair/retry, then fail the stage with the raw response captured safely in diagnostic logs if permitted.
- Never treat a malformed or missing model result as a valid empty classification/routing result.
- Record the run ID, failed stage, error category, and timestamp in operational logs.
- Do not write secrets, access tokens, or unnecessary customer-sensitive content to logs.

## 4. Data models (Pydantic)

Use Pydantic v2 models for input validation, stage contracts, and artifact serialization. The examples below are a design contract; field constraints may be tightened as implementation details become clear. Use `extra="forbid"` for model-produced outputs to reject unexpected fields where appropriate, and `model_dump(mode="json")` for JSON-safe serialization.

### 4.1 Base model configuration

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
```

For external input files, consider whether `extra="forbid"` is too strict for evaluator fixtures that may add harmless fields. A robust compromise is to allow extra input fields while explicitly modelling required fields; keep stage outputs strict.

### 4.2 Input ticket and knowledge-base models

```python
from typing import Literal

class Ticket(StrictModel):
    ticket_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    customer_tier: str = Field(min_length=1)
    language_hint: str = Field(min_length=1)
    subject: str
    message: str
    created_at: datetime

class KBArticle(StrictModel):
    article_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    body: str
    tags: list[str] = Field(default_factory=list)
```

Input invariants:
- `ticket_id` values must be unique within a batch.
- `article_id` values must be unique within the KB.
- `created_at` must parse as an ISO-8601 timestamp. Normalise timezone handling consistently; the supplied sample uses UTC `Z`.
- Do not require known ticket IDs or a fixed number/order of tickets.
- The pipeline must handle an empty or small fixture deliberately: either reject an empty batch with a clear error or support it consistently. For a batch with fewer than five tickets, the expedited set and draft set contain all available tickets.

### 4.3 Preprocessing model

```python
class PreprocessedTicket(StrictModel):
    ticket_id: str
    original_subject: str
    original_message: str
    subject_for_processing: str
    message_for_processing: str
    original_language: str
    translated: bool
```

Rules:
- Preserve `original_subject` and `original_message` byte-for-byte at the string level.
- `subject_for_processing` and `message_for_processing` should be English for classification and retrieval.
- `translated=True` when translation was applied; otherwise `False`.
- Use `language_hint` as a signal, not as proof that the body is entirely in that language. Mixed-language inputs may need translation/normalisation.
- If translation fails, do not silently claim the original non-English text is English. Use a configured fallback or fail with a clear diagnostic.

### 4.4 Controlled vocabulary enums

Define enums centrally in `vocab.py` and import them in all relevant modules.

```python
from enum import Enum

class Intent(str, Enum):
    WITHDRAWAL_ISSUE = "withdrawal_issue"
    DEPOSIT_ISSUE = "deposit_issue"
    LOGIN_ACCESS = "login_access"
    VERIFICATION_KYC = "verification_kyc"
    ACCOUNT_RESTRICTION = "account_restriction"
    PRODUCT_BEHAVIOR = "product_behavior"
    PRIVACY_REQUEST = "privacy_request"
    STATEMENT_EXPORT = "statement_export"
    API_SUPPORT = "api_support"
    OTHER = "other"

class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Sentiment(str, Enum):
    CALM = "calm"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"
    NEUTRAL = "neutral"

class InternalQueue(str, Enum):
    GENERAL_SUPPORT = "General Support"
    PAYMENTS = "Payments"
    COMPLIANCE = "Compliance"
    RISK = "Risk"
    ENGINEERING = "Engineering"
    PRODUCT = "Product"
    PRIVACY = "Privacy"
    DEVELOPER_SUPPORT = "Developer Support"

class ReplySafetyLabel(str, Enum):
    SAFE_TO_SEND_AFTER_REVIEW = "safe_to_send_after_review"
    NEEDS_SPECIALIST_REVIEW = "needs_specialist_review"
    NEEDS_LEGAL_OR_COMPLIANCE_REVIEW = "needs_legal_or_compliance_review"
```

### 4.5 Classification model

```python
class Classification(StrictModel):
    ticket_id: str
    intent: Intent
    urgency: Urgency
    sentiment: Sentiment
    mentions_funds_blocked: bool
    mentions_regulator_or_legal_threat: bool
    requires_specialist_handling: bool
    original_language: str
    translated: bool
```

The Stage 1 prompt must explicitly describe every field, allowed enum value, and expected output structure. Parse model output into this model; reject values outside the enum. Classification should return exactly one record for every preprocessed ticket, with no duplicate or unknown ticket IDs.

### 4.6 Retrieval model

```python
class RetrievedArticle(StrictModel):
    article_id: str
    title: str
    score: float = Field(ge=0.0, le=1.0)

class TicketRetrieval(StrictModel):
    ticket_id: str
    retrieved_articles: list[RetrievedArticle] = Field(min_length=2, max_length=2)
```

The score is the retrieval algorithm's relevance score, not a confidence claim from the LLM. Define and document how it is calculated and normalised. Article IDs must be checked against the actual input KB. Titles should be copied from the KB records rather than generated.

### 4.7 Priority model

```python
class PriorityResult(StrictModel):
    ticket_id: str
    base_priority: int
    customer_tier_bonus: int
    funds_blocked_bonus: int
    regulatory_legal_threat_bonus: int
    specialist_handling_bonus: int
    retrieval_weakness_bonus: int
    priority_score: int
    expedited: bool
    rank: int
```

Persist the score components so the score is auditable. Define a stable tie-breaker (recommended: descending score, then ascending `ticket_id`) to make ordering deterministic when scores match.

### 4.8 Routing model

```python
class RoutingDecision(StrictModel):
    ticket_id: str
    queues: list[InternalQueue] = Field(min_length=1)
    routing_rationale: str = Field(min_length=1)
    reply_safety_label: ReplySafetyLabel
```

Validate that queues contain no duplicates. The rationale should be short, concrete, and supported by ticket/classification/retrieval evidence. Multiple queues are allowed when justified. The model must not introduce a queue outside `InternalQueue`.

### 4.9 Draft model

```python
class ReplyDraft(StrictModel):
    ticket_id: str
    channel: str
    draft_reply: str = Field(min_length=1)
    citations: list[str] = Field(min_length=1)
    review_gate_note: str = Field(min_length=1)
```

Draft invariants:
- Generate drafts only for tickets selected in the expedited top-five set.
- Every citation must refer to an article retrieved for that ticket and exist in the current KB.
- The draft must acknowledge the issue, avoid speculation and unsupported promises, and not disclose internal review triggers.
- The review note must make clear that a human agent must review before sending.
- No automatic sending or external side effect is part of this pipeline.

### 4.10 Optional output models

```python
class RetrievalQualityNote(StrictModel):
    ticket_id: str
    issue: str
    recommended_improvement: str

class HandoffMemory(StrictModel):
    ticket_id: str
    customer_problem_summary: str
    open_questions: list[str]
    do_not_say: list[str]
    recommended_next_action: str
```

The operations summary is Markdown and should include counts by intent and urgency, recurring themes, legal/regulatory-risk tickets, and tickets requiring specialist handling.

## 5. Controlled vocabularies and policy

All controlled vocabulary values must be defined once in code and reused by prompts, parsers, validators, and tests.

| Field | Allowed values |
|---|---|
| Intent | `withdrawal_issue`, `deposit_issue`, `login_access`, `verification_kyc`, `account_restriction`, `product_behavior`, `privacy_request`, `statement_export`, `api_support`, `other` |
| Urgency | `critical`, `high`, `medium`, `low` |
| Sentiment | `calm`, `frustrated`, `angry`, `neutral` |
| Queue | `General Support`, `Payments`, `Compliance`, `Risk`, `Engineering`, `Product`, `Privacy`, `Developer Support` |
| Reply safety | `safe_to_send_after_review`, `needs_specialist_review`, `needs_legal_or_compliance_review` |

The prompt should request structured JSON and list the allowed values explicitly. Pydantic validation is the enforcement boundary; prompt instructions alone are not sufficient.

## 6. Pipeline execution flow

### 6.1 Load inputs

1. Resolve input paths from configuration.
2. Read `tickets.json` and `kb_articles.json`.
3. Parse JSON and validate records.
4. Check unique IDs and required fields.
5. Keep immutable in-memory representations of the original records for traceability.

### 6.2 Multilingual preprocessing

1. Inspect `language_hint` and detect mixed/non-English content where needed.
2. Produce English processing text for subject and message.
3. Preserve original subject/message and language metadata.
4. Write `preprocessed_tickets.json`.
5. Validate that every input ticket is represented exactly once.

The public fixture specifically requires the Malay ticket and Hindi-English mixed ticket to be normalised into English before classification.

### 6.3 Stage 1 — Classification

1. Build one batch prompt containing all preprocessed tickets.
2. Include the full output schema and enum vocabularies.
3. Request one JSON record per ticket.
4. Parse the response and validate each record with `Classification`.
5. Check exact ticket coverage, no duplicates, and no unknown IDs.
6. Write `classified_tickets.json`.
7. Append the classification call record to `llm_calls.jsonl`.

Use a provider abstraction so the pipeline is not coupled to one SDK. Keep API keys in environment variables and never commit them.

### 6.4 Retrieval

Use a reproducible lexical retrieval method unless embeddings are specifically required. A practical baseline is TF-IDF over article title, body, category, and tags, with the query built from:
- `subject_for_processing`
- `message_for_processing`
- classification intent and other useful normalised metadata

Implementation recommendations:
- Fit the vectoriser on the loaded KB for each run, or use a deterministic token-overlap/BM25 implementation.
- Do not hardcode expected article IDs for individual tickets.
- Use a stable tie-breaker, such as ascending `article_id`.
- Return exactly two articles per ticket. If the KB contains fewer than two articles, fail clearly because the required contract cannot be satisfied.
- Ensure scores are bounded and consistently interpreted. If TF-IDF cosine similarity is used, it naturally lies in `[0, 1]` for non-negative vectors.
- Write `retrieval_results.json` before priority scoring begins.

### 6.5 Deterministic priority scoring

Use the required formula exactly:

```text
base priority:
  critical = 40
  high     = 25
  medium   = 10
  low      = 3

customer tier bonus:
  vip      = 10
  standard = 0

funds blocked bonus              = 20 if mentions_funds_blocked
regulatory/legal threat bonus    = 25 if mentions_regulator_or_legal_threat
specialist handling bonus        = 10 if requires_specialist_handling
retrieval weakness bonus         = 8 if top retrieval score < 0.55

priority_score = sum of all components
```

Rules:
- The final score must be computed only in Python.
- Treat the tier according to the supplied schema. The specification explicitly defines `vip` and `standard`; if other tiers appear in replacement fixtures, configure an explicit policy (recommended: unknown tiers receive zero bonus and generate a validation warning rather than crashing).
- Compare the top retrieval score using the strict condition `< 0.55`.
- Sort by descending `priority_score`; break ties by ascending `ticket_id`.
- Mark the first `min(5, number_of_tickets)` tickets as expedited.
- Write `priority_scores.json`, including component breakdown, rank, and expedited flag.

### 6.6 Stage 2 — Queue routing

Make a separate LLM call after priority scores exist. Include:
- all classified tickets,
- the top retrieval results,
- the top five priority tickets and score context,
- the complete controlled queue vocabulary,
- the allowed reply-safety labels.

Validate each `RoutingDecision`, ensure every ticket has a routing decision, and reject invalid queues or safety labels. Persist `routing_decisions.json` and log the call.

Routing must be evidence-based. For example, a deposit reconciliation issue may fit Payments, a privacy deletion request may fit Privacy, and a regulatory threat may justify Compliance or Risk review. These are examples of policy reasoning, not fixed mappings; routing should use current ticket content and evidence.

### 6.7 Stage 3 — Safe reply drafting

Make a separate LLM call for only the expedited tickets. Provide the original customer context, English processing text, classification, routing decision, and retrieved KB article content. Ask for drafts with citations restricted to those retrieved articles.

Validate:
- output ticket IDs match the expedited set exactly,
- channel is copied from the input ticket,
- citations are a subset of that ticket's retrieved article IDs,
- cited articles exist in the KB,
- each draft includes a human-review note,
- no unsupported time or outcome promises are introduced.

Write `reply_drafts.json` and log the call. Replies are drafts only and must never be automatically sent.

### 6.8 Validation and optional analysis

Run validation after all required artifacts are produced. Recommended optional outputs:
- `retrieval_quality.json`: identify weak top scores (for example `< 0.55`) and ambiguous retrieval results; explain a concrete improvement.
- `ops_summary.md`: batch counts by intent/urgency, recurring themes, legal/regulatory risk tickets, specialist-handling tickets.
- `handoff_memory.json`: concise handoff objects for top-five tickets.
- `validation_report.md`: human-readable pass/fail checks with counts and failure details.

Optional analyses must not silently alter required pipeline outputs.

## 7. Artifact storage strategy

### 7.1 Required artifacts

| Artifact | Format | Producer | Contents |
|---|---|---|---|
| `tickets.json` | JSON input | External/input | Ticket records |
| `kb_articles.json` | JSON input | External/input | KB article records |
| `preprocessed_tickets.json` | JSON | Preprocessing | Original and English processing text |
| `classified_tickets.json` | JSON | Stage 1 classification | Validated classifications |
| `retrieval_results.json` | JSON | Retrieval | Top two articles and scores per ticket |
| `priority_scores.json` | JSON | Priority stage | Score components, total, rank, expedited flag |
| `routing_decisions.json` | JSON | Stage 2 routing | Queues, rationale, safety label |
| `reply_drafts.json` | JSON | Stage 3 drafting | Top-five drafts, citations, review notes |
| `llm_calls.jsonl` | JSONL | LLM wrapper | One record per LLM call |
| `retrieval_quality.json` | JSON | Optional analysis | Weak/ambiguous retrieval cases |
| `ops_summary.md` | Markdown | Optional analysis | Operational batch summary |
| `handoff_memory.json` | JSON | Optional analysis | Top-five handoff state |
| `validation_report.md` | Markdown | Validation | Check results and failure details |

### 7.2 Directory and naming policy

- Keep filenames stable and match the required names exactly.
- Default to a configurable artifact directory; ensure the evaluator can find outputs at the documented location. If uncertain, write required artifacts to the repository root.
- Write JSON as UTF-8 with readable indentation and a trailing newline.
- Write JSONL as UTF-8, one valid JSON object per line.
- Write Markdown reports as UTF-8.
- Do not overwrite input files with transformed data.
- Avoid ambiguous names such as `output.json`; each stage has its own named artifact.

### 7.3 Atomic writes and run consistency

For each artifact:
1. Serialise to a temporary file in the same directory.
2. Flush and close it.
3. Replace the target path atomically where supported.

This prevents a partially written artifact from appearing complete. Use a run ID in logs; optionally maintain a run manifest with input hashes, configuration, code version, and completion state. Do not change required artifact names to include run IDs if the evaluator expects fixed names; a run-specific archive can be stored separately.

### 7.4 Replayability and provenance

Recommended run metadata:
- run ID,
- UTC start/end timestamps,
- SHA-256 hashes of both input files,
- configured model/provider identifiers,
- retrieval method and parameters,
- pipeline version or Git commit,
- final pipeline state.

Keep the required artifact names stable. Provenance may be stored in an additional `run_manifest.json`. Timestamps and LLM-generated text can vary across runs; deterministic retrieval, priority scores, tie-breaking, schema validation, and artifact ordering should not.

### 7.5 LLM call logging

`llm_calls.jsonl` must contain separate records for classification, routing, and reply drafting. Each record must include:

```json
{
  "stage": "classification",
  "timestamp": "2026-10-10T12:00:00Z",
  "provider": "provider-name",
  "model": "model-name",
  "prompt_hash": "sha256-of-exact-prompt",
  "input_artifacts": ["preprocessed_tickets.json"],
  "output_artifact": "classified_tickets.json"
}
```

Requirements:
- `timestamp` is an ISO-8601 timestamp, preferably UTC.
- `prompt_hash` is SHA-256 of the exact prompt payload sent to the provider, excluding secrets.
- `input_artifacts` names the artifact paths that informed the call.
- `output_artifact` names the artifact written from that call.
- Append one record only after a call attempt has enough metadata to describe it; record failures separately if the chosen schema supports a status field, or add a separate operational error log.
- Do not log API keys or secrets.
- If retrieval uses only deterministic code, it does not need an LLM call log.

## 8. Validation contract

Provide a runnable command such as:

```bash
python validate.py
# or
make validate
```

The validation command should check at least:

1. All required artifacts exist.
2. All required JSON artifacts parse correctly.
3. Every input ticket appears exactly once in preprocessing and classification.
4. Every classified ticket uses the controlled intent, urgency, and sentiment vocabularies.
5. Non-English/mixed-language tickets preserve original text and provide English processing text; the known Malay and Hindi-English fixture examples must be normalised.
6. Every ticket has exactly two retrieved articles.
7. Every retrieved article ID exists in the loaded `kb_articles.json`.
8. Retrieval scores are finite and within the documented range.
9. Priority scores recompute exactly from classifications, ticket tier, and retrieval results.
10. Sorting and top-five flags match the deterministic ranking rule.
11. Every ticket has a routing decision and every queue/safety label is allowed.
12. Draft IDs match the expedited top-five set (or all tickets when fewer than five exist).
13. Every reply citation belongs to that ticket's retrieval results and exists in the KB.
14. Required LLM call records exist as separate records for classification, routing, and drafting.
15. No stage is marked complete before its required input artifacts exist.

The report should include total checks, passed checks, failed checks, and actionable messages. The validation command should exit with a non-zero code when required checks fail.

## 9. Configuration and runtime

Use environment variables or a configuration file for:
- input directory,
- artifact directory,
- LLM provider and model,
- API key environment variable name,
- retry count and timeout,
- translation provider/model,
- retrieval parameters.

Include `.env.example` with placeholder variable names only. Add `.env` and any secrets to `.gitignore`. Never commit real credentials.

Suggested dependencies (choose versions compatible with the runtime):
- `pydantic>=2`
- one LLM provider SDK
- `scikit-learn` if TF-IDF is used
- a translation SDK or explicitly configured translation model if external translation is used
- `pytest` for tests

If the runtime must work without a network or API key, provide a clearly labelled deterministic mock mode for local tests. The evaluator-facing production mode should still perform the required LLM stages when configured; mock mode must not be mistaken for real model inference.

## 10. Testing strategy

### Unit tests
- Pydantic models reject invalid enum values.
- Duplicate IDs are detected.
- Priority components and total match the specified formula.
- A retrieval score below `0.55` adds exactly eight points.
- Tie-breaking is deterministic.
- Retrieval only references articles loaded from the current KB.
- Citation validation rejects articles not retrieved for that ticket.

### Integration tests
- Run the full pipeline against the supplied fixture.
- Run again with reordered tickets and verify output coverage and ranking logic remain correct.
- Replace fixture wording and article content while retaining schema; verify no hardcoded ID mappings are required.
- Test fewer than five tickets and confirm all available tickets are expedited and drafted.
- Test invalid JSON, missing fields, invalid model output, and provider failure.
- Verify `llm_calls.jsonl` contains three distinct required stage records.

### Acceptance criteria
The implementation is ready when it can run from a clean checkout, regenerate all required artifacts from disk inputs, enforce the state sequence, validate controlled vocabularies, compute deterministic scores after retrieval, route every ticket, draft only for expedited tickets, log the three required LLM stages, and exit successfully only when required validation checks pass.

## 11. Open implementation decisions

The system specification does not mandate a specific LLM provider, model, translation provider, or retrieval library. These should be configurable and documented. The retrieval algorithm and score semantics must be fixed in code so priority scoring is reproducible. The policy for unknown customer tiers should be explicit. The exact location of generated artifacts should be documented and compatible with the evaluator's expected paths.

---

**End of specification.**
"""

path = "/mnt/data/spec.md"
pypandoc.convert_text(content, "md", format="md", outputfile=path, extra_args=["--standalone"])
print(f"Created {path}")
