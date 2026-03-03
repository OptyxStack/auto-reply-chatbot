# UPGRADE_RAG_DESIGN

## Purpose

This document defines the target design for upgrading the current RAG pipeline.
It focuses on:

- End-to-end flow
- New contracts between pipeline stages
- Phase-by-phase rollout criteria

This is a design specification only. It does not prescribe exact implementation details, migrations, or code diffs.

## Design Goals

- Increase answer recall without materially increasing hallucination risk
- Reduce unnecessary `ASK_USER` outcomes caused by rigid gating
- Make retrieval strategy intent-aware instead of keyword-wide
- Turn evidence handling from "top-k list" into "best usable evidence set"
- Separate strong answers, weak-but-usable answers, and true escalation cases
- Make each stage observable and independently tunable

## Core Design Shift

The current flow is effectively:

`query -> normalize -> retrieve -> quality gate -> decision router -> generate -> reviewer`

The target flow becomes:

`query -> understand -> choose retrieval profile -> retrieve candidates -> build evidence set -> assess sufficiency -> choose answer lane -> generate bounded answer -> verify claims -> optional polish`

The key architectural change is that the system should no longer use hard gates as the primary control mechanism.
Instead, it should convert uncertainty into an answer lane:

- `PASS_STRONG`
- `PASS_WEAK`
- `ASK_USER`
- `ESCALATE`

## Hybrid Normalizer Design

The normalizer should be explicitly hybrid:

- Rule-based handles only stable, generic behavior
- LLM handles domain-shaped interpretation when enabled
- Config provides optional domain overrides without hard-coding domain logic into the core normalizer

This keeps the normalizer generic by default while preserving a migration path for existing domain-specific deployments.

### Rule-Based Scope to Keep

The rule-based path should continue to handle:

- `skip_retrieval` for greetings, thanks, and other social messages
- language detection and translation eligibility
- referential ambiguity detection
- generic high-risk keyword detection for refund, legal, and billing-dispute style cases
- broad support intent grouping: transactional, policy, troubleshooting, account, informational, ambiguous

These behaviors are stable across deployments and should stay deterministic.

### Rule-Based Scope to Reduce

The rule-based path should no longer hard-code domain assumptions by default.

Reduce or remove these behaviors unless explicitly enabled by config:

- fixed `domain_terms` lists in code
- domain-specific slot extraction such as `product_type`, `os`, `region`, `billing_cycle`
- hard-coded `required_evidence` tied to one product domain
- keyword expansion that injects deployment-specific vocabulary

The default generic rule path should remain intentionally thin.

### LLM-Primary Semantic Path

When `NORMALIZER_USE_LLM=true`, the LLM path should be the primary semantic analyzer.
It should infer:

- intent
- entities
- required evidence
- risk level

The rule-based path should only serve as deterministic fallback when the LLM is disabled or fails.

The normalizer prompt should stay generic.
Deployment-specific domain context should come from the broader chatbot system prompt or tenant configuration, not from hard-coded normalizer logic.

### Configurable Domain Override

Domain-specific rule enrichment should be optional and configuration-driven.

Recommended controls:

- `NORMALIZER_DOMAIN_TERMS`
  Optional comma-separated terms for rule-based entity extraction. Default: empty.
- `NORMALIZER_QUERY_EXPANSION`
  Enables optional BM25 query expansion. Default: `false`.
- `NORMALIZER_SLOTS_ENABLED`
  Enables optional rule-based slot extraction. Default: `false`.

These settings may start as environment variables and later move into DB-backed tenant configuration.

### Backward Compatibility Mode

The same normalizer should support two modes:

- `Generic default`
  Minimal rule-based behavior, LLM-primary semantics, and no domain assumptions in code.
- `Deployment-specific compatibility`
  Existing domain behavior restored through config by enabling domain terms, slots, and query expansion.

## End-to-End Flow

### High-Level Flow

```text
User Query
  |
  v
[Language Detect]
  |
  v
[Normalizer / Query Understanding]
  |
  |--> QuerySpec
  |      - intent
  |      - slots
  |      - ambiguity type
  |      - retrieval profile
  |      - answer mode hint
  |
  v
[Orchestrator]
  |
  v
[Retrieval Planner]
  |
  |--> RetrievalPlan
  |      - source priorities
  |      - bm25/vector weights
  |      - doc_type policy
  |      - expansion policy
  |
  v
[Candidate Retrieval]
  |
  v
[Rerank + Evidence Set Builder]
  |
  |--> EvidenceSet
  |      - selected chunks
  |      - slot coverage
  |      - trust mix
  |
  v
[Evidence Assessment]
  |
  |--> EvidenceAssessment
  |      - can_answer_fully
  |      - can_answer_partially
  |      - missing slots
  |      - weak claim areas
  |
  v
[Decision Router]
  |
  |--> AnswerLane
  |      - PASS_STRONG
  |      - PASS_WEAK
  |      - ASK_USER
  |      - ESCALATE
  |
  +------------------------------+
  |                              |
  | PASS_*                       | ASK_USER / ESCALATE
  v                              v
[Answer Planner]             [Return System Response]
  |
  v
[LLM Generation]
  |
  v
[Claim-Level Reviewer]
  |
  +--> accept
  +--> trim unsupported claims
  +--> targeted retry
  +--> downgrade lane
  +--> escalate
  |
  v
[Optional Final Polish]
  |
  v
Final Response
```

### Runtime Stage Semantics

1. `Language Detect`
   Determines source language and whether semantic translation is needed.
   It should preserve domain-specific tokens.

2. `Normalizer / Query Understanding`
   Converts the raw question into a structured `QuerySpec`.
   This is where intent, slots, ambiguity, and answerability are determined.

3. `Retrieval Planner`
   Chooses the retrieval strategy from `QuerySpec`.
   It must decide source preference, retrieval weighting, and expansion policy.

4. `Candidate Retrieval`
   Produces a broad pool from BM25, vector, and source-specific fetch rules.

5. `Rerank + Evidence Set Builder`
   Selects the most useful evidence set for answering, not just the highest-scoring top-k.

6. `Evidence Assessment`
   Decides whether the current evidence can support a full answer, a partial answer, or no answer.

7. `Decision Router`
   Converts evidence sufficiency into an answer lane.
   This stage should minimize unnecessary blocking.

8. `Answer Planner`
   Builds the answer structure for the selected lane.

9. `LLM Generation`
   Generates only within the allowed evidence and lane constraints.

10. `Claim-Level Reviewer`
   Audits factual support per claim.
   It should prefer trimming or downgrading before rejecting everything.

11. `Final Polish`
   Optional formatting/clarity pass with no factual changes.

## New Object Contracts

The upgraded design introduces explicit contracts so all stages operate on shared, stable objects.

### QuerySpec

Purpose:
Structured understanding of user intent and what the pipeline should try to answer.

```text
QuerySpec
- original_query: str
- canonical_query: str
- sanitized_query: str
- source_lang: str
- translation_needed: bool
- language_confidence: float | None

- intent: str
  transactional | comparison | policy | troubleshooting | account | informational | ambiguous

- user_goal: str
  price_lookup | order_link | refund_policy | setup_steps | feature_compare | general_info | unknown

- entities: list[str]
- resolved_slots: dict[str, Any]
- missing_slots: list[str]
- constraints: dict[str, Any]

- ambiguity_type: str | None
  referential | missing_constraints | semantic | none

- is_ambiguous: bool
- answerable_without_clarification: bool

- required_evidence: list[str]
- hard_requirements: list[str]
- soft_requirements: list[str]
- extraction_mode: str
  llm_primary | rule_primary | rule_fallback
- config_overrides_applied: list[str]

- retrieval_profile: str
  pricing_profile | policy_profile | troubleshooting_profile | comparison_profile | generic_profile

- keyword_queries: list[str]
- semantic_queries: list[str]
- rewrite_candidates: list[str]

- answer_mode_hint: str
  strong | weak | ask_user

- clarifying_questions: list[str]
- skip_retrieval: bool
- canned_response: str | None
```

Behavior rules:

- `QuerySpec` is the only source of truth for downstream routing.
- Retrieval logic should no longer re-infer intent from raw keywords if `QuerySpec` is present.
- `missing_slots` and `answerable_without_clarification` should drive `ASK_USER` decisions.
- In generic mode, `entities`, `resolved_slots`, and `required_evidence` may be intentionally sparse.
- Domain-enriched rule output should only exist when config explicitly enables it.

### RetrievalPlan

Purpose:
Concrete retrieval strategy derived from `QuerySpec` and prior attempts.

```text
RetrievalPlan
- profile: str
- attempt_index: int
- reason: str

- preferred_doc_types: list[str]
- excluded_doc_types: list[str]
- preferred_sources: list[str]

- query_keyword: str
- query_semantic: str
- fallback_queries: list[str]

- bm25_weight: float
- vector_weight: float
- rerank_weight: float

- fetch_n: int
- rerank_k: int

- enable_parent_expansion: bool
- enable_neighbor_expansion: bool
- enable_exact_slot_fetch: bool

- boost_patterns: list[str]
- exclude_patterns: list[str]

- budget_hint: dict[str, Any]
```

Behavior rules:

- Each retry must produce a materially different `RetrievalPlan`.
- `RetrievalPlan` must encode why the current attempt exists, so it can be evaluated later.
- Retry should not be represented as "same query plus a few tokens" only.

### CandidatePool

Purpose:
Intermediate pool before evidence selection.

```text
CandidatePool
- items: list[CandidateChunk]
- source_counts: dict[str, int]
- doc_type_counts: dict[str, int]
- retrieval_stats: dict[str, Any]
- plan_used: RetrievalPlan
```

```text
CandidateChunk
- chunk_id: str
- document_id: str
- source_url: str
- doc_type: str
- chunk_text: str
- retrieval_score: float
- retrieval_source: str
  bm25 | vector | boosted_fetch | expanded_parent | expanded_neighbor
- metadata: dict[str, Any]
```

Behavior rules:

- This object exists only to separate retrieval breadth from final evidence usefulness.
- The pool can be broad and noisy.
- Later stages should not treat this as answer-ready evidence.

### EvidenceSet

Purpose:
The final selected evidence bundle used for answering.

```text
EvidenceSet
- chunks: list[EvidenceChunk]
- primary_chunks: list[str]
- supporting_chunks: list[str]

- covered_requirements: list[str]
- uncovered_requirements: list[str]
- covered_slots: list[str]
- uncovered_slots: list[str]

- trust_mix: dict[str, float]
- diversity_score: float
- concentration_score: float

- evidence_summary: str
- build_reason: str
```

Behavior rules:

- `EvidenceSet` should be optimized for answerability, not raw rank.
- One strong chunk should be allowed to satisfy a requirement where the requirement is atomic, such as `transaction_link`.
- Weak chunks can remain only as supporting context, not as the basis for high-confidence claims.

### EvidenceAssessment

Purpose:
Formal judgment of whether the current `EvidenceSet` is sufficient.

```text
EvidenceAssessment
- coverage_score: float
- specificity_score: float
- actionability_score: float
- trust_score: float
- consistency_score: float

- can_answer_fully: bool
- can_answer_partially: bool

- missing_slots: list[str]
- weak_claim_areas: list[str]
- blocked_claim_areas: list[str]

- recommended_lane: str
  PASS_STRONG | PASS_WEAK | ASK_USER | ESCALATE

- retry_value_estimate: float
- reasoning: str
```

Behavior rules:

- This replaces simple aggregate-threshold gating.
- It must explicitly distinguish partial answerability from total insufficiency.
- `recommended_lane` is advisory but should usually drive routing.

### DecisionResult

Purpose:
Final routing decision before generation or direct system response.

```text
DecisionResult
- lane: str
  PASS_STRONG | PASS_WEAK | ASK_USER | ESCALATE

- reason: str
  sufficient | partial_but_safe | referential_ambiguity | missing_required_slot | high_risk_insufficient | no_viable_evidence

- answer_policy: str
  direct | bounded | clarify | human_handoff

- clarifying_questions: list[str]
- partial_links: list[str]
- user_safe_summary: str
```

Behavior rules:

- `DecisionResult` should never collapse all non-perfect states into `ASK_USER`.
- `PASS_WEAK` exists to keep the system useful under partial evidence.

### AnswerPlan

Purpose:
Generation blueprint produced from `DecisionResult` and `EvidenceSet`.

```text
AnswerPlan
- lane: str
- allowed_claim_scope: str
  full | partial | none

- must_include: list[str]
- must_avoid: list[str]
- required_citations: list[str]

- output_blocks: list[str]
  direct_answer | confirmed_points | uncertain_points | recommended_next_step | citations

- tone_policy: str
  concise | explanatory | cautious

- generation_constraints: dict[str, Any]
```

Behavior rules:

- This object prevents generation from drifting beyond what the evidence supports.
- Weak-answer mode should force explicit uncertainty blocks.

### AnswerDraft

Purpose:
Model output before review.

```text
AnswerDraft
- lane: str
- direct_answer: str
- confirmed_points: list[str]
- uncertain_points: list[str]
- recommended_next_step: str
- citations: list[dict[str, Any]]
- confidence_band: str
  high | medium | low
- raw_text: str
```

Behavior rules:

- Structured output should be preferred over free-text JSON blobs that only include one `answer`.
- Review can then operate on claim groups instead of a flat paragraph.

### ReviewResult

Purpose:
Claim-level post-generation verification outcome.

```text
ReviewResult
- status: str
  accept | accept_with_lower_confidence | trim_unsupported_claims | retry_targeted | downgrade_lane | escalate

- unsupported_claims: list[str]
- weakly_supported_claims: list[str]
- claim_to_citation_map: dict[str, list[str]]

- reviewer_notes: list[str]
- suggested_retry_plan: RetrievalPlan | None
- final_lane: str
```

Behavior rules:

- Reviewer should preserve good answer content when possible.
- Trimming and downgrading are preferred over throwing away the whole answer.

## File-by-File Direction

### `app/services/language_detect.py`

- Return confidence-aware language signals, not only a language code
- Preserve domain entities during translation
- Feed translation policy into `QuerySpec`

### `app/services/normalizer.py`

- Be the canonical query understanding layer
- Separate referential ambiguity from missing constraints
- Extract slots and determine whether partial answering is still possible
- Emit `QuerySpec` rich enough to drive retrieval directly
- Default to a minimal generic rule-based path
- Use the LLM as the primary source for domain-specific intent, entities, and evidence when enabled
- Load domain terms and optional rule enrichments from config instead of hard-coding them in code
- Keep deployment-specific legacy behavior behind config switches, not separate logic branches

### `app/services/retrieval.py`

- Consume `RetrievalPlan`, not only a raw query
- Build `CandidatePool`, then select `EvidenceSet`
- Use profile-based retrieval instead of broad keyword shortcuts
- Support multiple retry strategies with explicit state

### `app/search/reranker.py`

- Become task-aware and requirement-aware
- Score chunks by usefulness for the active answer task, not only relevance
- Provide richer ranking signals for evidence set building

### `app/services/evidence_quality.py`

- Evolve into `EvidenceAssessment`
- Replace pure average scoring with coverage-oriented sufficiency logic
- Make partial-answer viability explicit

### `app/services/retry_planner.py`

- Generate a new `RetrievalPlan` per retry
- Use prior attempt history and failure reason
- Support source switching, doc filtering, and expansion changes

### `app/services/decision_router.py`

- Route into answer lanes, not only pass/fail
- Prefer `PASS_WEAK` over unnecessary `ASK_USER`
- Reserve `ESCALATE` for high-risk or non-automatable conditions

### `app/services/reviewer.py`

- Move to claim-level verification
- Trim or downgrade before hard rejection
- Support targeted retry only when new evidence could realistically improve the answer

### `app/services/orchestrator.py`

- Become the source of truth for stage transitions and attempt state
- Hold shared runtime context
- Own the retry lifecycle and termination reasons

### `app/services/answer_service.py`

- Become the assembly layer for contracts
- Replace a single monolithic loop with explicit stage transitions
- Support structured weak-answer generation and bounded answer plans

### `app/services/llm_gateway.py`

- Become task-aware rather than generic
- Define per-task model policy, timeout, budget, and cache namespace
- Support structured-output validation and repair

### `app/services/evidence_evaluator.py`

- Act only as semantic gap analysis for retry planning
- Identify missing slots and likely wrong retrieval focus
- Avoid acting as a second decision router

### `app/services/self_critic.py`

- Run selectively for weak answers, risky answers, or high-claim outputs
- Prefer trim instructions or caveat insertion over full regeneration

### `app/services/final_polish.py`

- Remain presentation-only
- Never increase confidence or alter factual scope
- Prefer deterministic formatting over LLM when possible

## Phase-by-Phase Rollout

Rollout should be staged to reduce behavioral drift and make regressions attributable.

### Phase 1: Contract Foundation

Scope:

- Introduce new data contracts
- Expand orchestrator state model
- Add lane vocabulary: `PASS_STRONG`, `PASS_WEAK`, `ASK_USER`, `ESCALATE`

Primary files:

- `app/services/schemas.py`
- `app/services/orchestrator.py`

Success criteria:

- New contracts are defined and consumable without breaking current endpoints
- Existing flow can be adapter-wrapped into the new contracts
- Logs can record lane and stage reason consistently

Exit criteria:

- Every downstream stage can accept structured state instead of raw ad hoc primitives

### Phase 2: Query Understanding and Retrieval Planning

Scope:

- Upgrade normalizer into structured query understanding
- Add retrieval profiles
- Introduce `RetrievalPlan`
- Convert the normalizer into a hybrid model: minimal rule path plus LLM-primary semantic path

Primary files:

- `app/services/normalizer.py`
- `app/services/language_detect.py`
- `app/services/retry_planner.py`

Success criteria:

- Intent classification is no longer re-derived inside retrieval
- Ambiguity and missing-slot cases are separated
- Retry attempts produce distinct plans instead of minor keyword edits
- In generic mode, the normalizer stays domain-agnostic by default
- In deployment-specific mode, domain behavior is restored via config, not code forks

Exit criteria:

- A query can be traced from raw text to an explicit retrieval strategy
- The same normalizer implementation supports both generic and domain-specific deployments through config only

### Phase 3: Evidence Construction and Assessment

Scope:

- Separate candidate retrieval from answer-ready evidence
- Add `CandidatePool`, `EvidenceSet`, and `EvidenceAssessment`

Primary files:

- `app/services/retrieval.py`
- `app/search/reranker.py`
- `app/services/evidence_quality.py`
- `app/services/evidence_evaluator.py`

Success criteria:

- The system can explain why a chunk was included in the final answer set
- One strong chunk can satisfy atomic requirements where appropriate
- Partial answerability is formally detectable

Exit criteria:

- Decision routing is driven by evidence sufficiency, not just aggregate thresholds

### Phase 4: Lane-Based Routing and Generation

Scope:

- Replace binary pass/fail routing with lane-based routing
- Add `AnswerPlan`
- Support bounded weak-answer mode

Primary files:

- `app/services/decision_router.py`
- `app/services/answer_service.py`
- `app/services/llm_gateway.py`

Success criteria:

- `PASS_WEAK` is available and used for partially answerable cases
- `ASK_USER` rate decreases for questions that still allow safe partial answers
- Generation respects structured answer blocks

Exit criteria:

- The generator can produce both strong and weak answers under explicit policies

### Phase 5: Claim-Level Verification

Scope:

- Replace citation-count heuristics with claim-level review
- Allow trim/downgrade before rejection

Primary files:

- `app/services/reviewer.py`
- `app/services/self_critic.py`

Success criteria:

- Unsupported claims can be removed without discarding supported content
- Reviewer can downgrade lane or lower confidence instead of forcing full retry

Exit criteria:

- Final answers are validated at the claim level, not by coarse citation counts

### Phase 6: Final Output Quality and Stability

Scope:

- Limit final polish to presentation
- Tighten observability and stability around all lanes

Primary files:

- `app/services/final_polish.py`
- `app/services/answer_service.py`
- `app/services/llm_gateway.py`

Success criteria:

- Final polish does not alter factual scope
- Output quality improves without increased overstatement
- Logs and metrics can distinguish where answer quality was gained or lost

Exit criteria:

- The full lane-based RAG stack is stable enough for controlled production rollout

## Rollout Guardrails

To keep rollout safe, the following guardrails should apply across all phases:

- New objects should be introduced behind adapters before old structures are removed
- Every stage should emit a machine-readable reason for its decision
- Retry changes should be measurable by attempt and plan type
- Weak-answer mode should always enforce explicit uncertainty
- Escalation should remain conservative for high-risk cases

## Evaluation Requirements

The design should be validated with stage-specific evaluation, not only end-to-end anecdotes.

At minimum, evaluation should track:

- Retrieval hit quality
- Evidence sufficiency quality
- Strong-answer correctness
- Weak-answer usefulness
- Unnecessary `ASK_USER` rate
- Unsupported confident answer rate
- Escalation precision for high-risk queries

Evaluation sets should include:

- Transactional pricing queries
- Policy queries
- Troubleshooting queries
- Comparison queries
- Ambiguous queries
- Under-specified but still partially answerable queries

## Definition of Done

The upgrade should be considered complete only when:

- The pipeline can distinguish full answers from safe partial answers
- Retrieval is profile-driven rather than broad keyword-driven
- Evidence sufficiency is explicit and structured
- Reviewer behavior is claim-aware
- Each retry is purposeful and measurably different
- The system is more useful under incomplete evidence without becoming more speculative

