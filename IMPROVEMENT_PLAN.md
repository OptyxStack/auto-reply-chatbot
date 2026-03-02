# Improvement Plan – Toward Enterprise RAG (archi.md)

Document describing the implementation roadmap for improvements to align the system with the architecture in `archi.md`.

---

## 1. Roadmap Overview

```
Phase 0.5 (Evidence Hygiene) → Phase 1 (Quick wins)  → Phase 2 (Evidence-first)  → Phase 3 (Full flow)
────────────────────────────────────────────────────────────────────────────────────────────────────
Boilerplate + density log    → Evidence Quality Gate → Request Normalizer        → Decision Router
(measure before tune)        → Retry Planner         → User context              → Budget controls
                             → Observability         →                          → Tone compliance
```

**Implementation principles:**
- Each phase can be deployed independently, no breaking changes
- Evidence-first priority: do not generate when evidence is weak
- Maintain backward compatibility with current API
- **Domain-agnostic:** Evidence scoring by features, not hardcoded domain logic; `doc_type` only as weak prior

---

## 2. Phase 0.5 – Evidence Hygiene (1 week)

**Goal:** Measure evidence characteristics *before* tuning gates. Log boilerplate and content density to inform threshold decisions.

**File:** `app/services/evidence_hygiene.py`

**Functionality (logging only, no gating):**
- **Boilerplate detection:** Ratio of nav/footer signatures (contact, copyright, menu, terms, privacy) vs substantive content; log per-chunk and aggregate
- **Content density:** Non-whitespace chars, sentence count, list/structure presence; log distribution
- **Top evidence signatures** (aggregate, dashboard-friendly):
  - `pct_chunks_with_url`: % chunks with URL
  - `pct_chunks_with_number_unit`: % chunks with number+unit
  - `pct_chunks_boilerplate_gt_06`: % chunks boilerplate > 0.6
  - `median_content_density`: median content_density
  - → Dashboard shows whether retrieval is pulling "junk" or "meat"
- Output: structured logs (or debug metadata) for analysis

**Integration:** Call after `retrieve()`, log to debug. Do not block flow. Use data to tune Phase 1 thresholds.

**Deliverables:**
- [ ] Boilerplate ratio per chunk + aggregate
- [ ] Content density metrics per chunk
- [ ] Top evidence signatures: pct_with_url, pct_with_number_unit, pct_boilerplate_gt_06, median_content_density
- [ ] Log pipeline for dashboard/analysis

---

## 3. Phase 1 – Quick wins (2–3 weeks)

**Goal:** Add Evidence Quality Gate and basic Retry Planner, improve observability. No changes to main flow.

### 3.1 Evidence Quality Gate (domain-agnostic)

**File:** `app/services/evidence_quality.py`

**Principle:** Score by **evidence features**, not domain logic. `doc_type` used only as weak prior (hint), no hardcoded policy/pricing.

**Input:** `EvidencePack`, `required_evidence` (list[str]) — optional; if absent, score all features

**Evidence features (per-chunk → aggregate):**

| Feature | Description | How to measure |
|---------|-------------|----------------|
| `numbers_units` | Numbers + units/currency | Pattern: `$`, `USD`, `/mo`, `\d+`, `%`, currency symbols |
| `has_any_url` | Any URL (docs link) | Valid URL regex |
| `has_transaction_link` | Transaction URL (order/checkout/store) | Paths containing order/store/checkout/cart → avoid "junk links" |
| `policy_language` | Policy language (normative patterns) | See table below |
| `steps_structure` | Procedural content structure | Numbered list (1., 2.), "Step N", bullet sequences |
| `content_density` | Real content density | Non-whitespace ratio, sentence count; avoid empty chunks |
| `boilerplate_ratio` | Nav/footer ratio | Keywords: contact, copyright, menu, terms → low ratio = good |
| `freshness` | Recency (if metadata exists) | `effective_date` decay; absent → neutral |
| `trust_tier` | Source trust level | `doc_type` weak prior: official > user-generated; small weight |

**policy_language — normative pattern groups (reduce false positives):**
- **obligation:** must, shall, required, prohibited
- **entitlement:** eligible, refund, within, fee applies
- **scope:** terms, policy, SLA, abuse, cancellation
→ Score based on combination of groups; not just simple keyword list. Match 2+ groups → higher confidence.

**QualityReport (explainable):**

```python
@dataclass
class QualityReport:
    quality_score: float              # 0–1, aggregate (optional check)
    feature_scores: dict[str, float]   # numbers_units, has_any_url, has_transaction_link, policy_language, ...
    missing_signals: list[str]         # derived: ["missing_numbers", "missing_transaction_link", ...]
    staleness_risk: float | None
    boilerplate_risk: float | None
```

- `missing_signals` **derived from feature_scores**: e.g. `numbers_units < 0.3` → `missing_numbers`; `has_transaction_link < 0.2` → `missing_transaction_link`
- When `required_evidence` exists: map `numbers`→`numbers_units`, `links`→`has_any_url`, `transaction_link`→`has_transaction_link`, `policy_clause`→`policy_language`, `steps`→`steps_structure`
- **Transactional query** (order, buy, checkout) → require `has_transaction_link`, not just `has_any_url`

**PASS decision (avoid aggregate masking missing features):**

| Condition | Result |
|-----------|--------|
| **Required** | `all(required_feature >= per_feature_threshold)` |
| Optional | `aggregate quality_score >= threshold` |

Avoid: good density + good trust → aggregate OK, but missing numbers → still PASS → LLM has to ASK_USER. **PASS only when all required features meet threshold.**

**Config:**
```python
evidence_quality_threshold: float = 0.6       # aggregate (optional check)
evidence_quality_enabled: bool = True
evidence_feature_thresholds: dict[str, float] = {  # per-feature min, required when required
    "numbers_units": 0.3,
    "has_transaction_link": 0.2,
    "policy_language": 0.3,
    ...
}
```

**Integration:** Call in `AnswerService.generate()` after `retrieve()`, before building messages for LLM. If **any required feature** fails → go to Retry Planner.

---

### 3.2 Retry Planner (fixed ladder, max 2 attempts)

**File:** `app/services/retry_planner.py`

**Fixed retry ladder:**
- **Max 2 attempts** (Attempt 1 + Attempt 2)
- **Attempt 1:** Broad hybrid — BM25 + Vector + Fusion + Rerank (unchanged)
- **Attempt 2:** Precision targeted by `missing_signals` (+ optional context expansion)

**Functionality:**
- Input: `QualityReport.missing_signals[]`, `attempt` (1 or 2)
- Output: `RetryStrategy` (boost_patterns, filter_doc_types, exclude_patterns, context_expansion)

**Mapping (Attempt 2 only):**

| missing_signal | Retry strategy |
|----------------|----------------|
| `missing_numbers` | Add patterns `$ USD /mo monthly \d+` to keyword query; phrase boost |
| `missing_links` / `missing_transaction_link` | Boost fields containing URL; context expansion (parent + neighbors) |
| `missing_policy` | Restrict `doc_type` to `{policy, tos}` (weak prior); boost policy language patterns |
| `boilerplate_risk` | Filter by content density; exclude nav/footer; **enable context_expansion = parent+neighbors** for top chunks with "menu page" signals |
| `staleness_risk` | Boost recent `effective_date` (if index has field) |

**Context expansion — default tool when boilerplate is high:**
- In pricing/nav case: Attempt 2 does not just boost regex
- **Always enable** `context_expansion = parent + neighbors` for top chunks with "menu page" signals (high boilerplate, little real content)
- Fetch parent doc / neighbor chunks to find "meat" inside the page

**LLM suggested_queries:** Use only as **fallback** when no QualityReport or when Retry Planner cannot map missing_signals. Do not use as primary retry trigger.

**Integration:**
- `RetrievalService.retrieve()` accepts `retry_strategy: RetryStrategy | None`, `attempt: int`
- Attempt 1: `retry_strategy=None` → broad hybrid
- Attempt 2: `retry_strategy` from Retry Planner → precision targeted

---

### 3.3 Observability

**Updates:**
- Log `QualityReport` (including `feature_scores`, `missing_signals`) to debug metadata
- Log `RetryStrategy` on retry
- Log cost (from `estimate_cost`) to debug per request
- Add metric `evidence_quality_score` (histogram), `evidence_feature_scores` (optional)

---

### 3.4 Phase 1 Flow (after completion)

```
Input → Intent Cache → Retrieval
  → Evidence Quality Gate
    → all required features >= threshold: continue
    → any required feature < threshold: Retry Planner → Retrieval (retry)
  → [Generate Answer] → Reviewer Gate → [Retry if RETRIEVE_MORE] → Output
```

**Note:** `required_evidence` can initially be inferred from query (rule-based), e.g.:
- Query has "price", "cost" → `required_evidence = ["numbers", "transaction_link"]` (transactional)
- Query has "link", "order" → `required_evidence = ["transaction_link"]`
- Query has "refund", "policy" → `required_evidence = ["policy_clause"]`

---

## 4. Phase 2 – Request Normalization (3–4 weeks)

**Goal:** Add Normalizer to create QuerySpec, normalize input before retrieval.

### 4.1 QuerySpec schema

**File:** `app/services/schemas.py` (or extend `app/api/schemas.py`)

```python
@dataclass
class QuerySpec:
    intent: str  # informational | transactional | policy | troubleshooting | account | ...
    entities: list[str]  # domain objects extracted
    constraints: dict[str, Any]  # budget < 10, region=SG, etc.
    required_evidence: list[str]  # ["numbers", "links", "transaction_link", "policy_clause", "steps", "citations"]
    risk_level: str  # low | medium | high
    keyword_queries: list[str]
    semantic_queries: list[str]
    clarifying_questions: list[str]  # optional, do not ask yet
```

### 4.2 Normalizer

**File:** `app/services/normalizer.py`

**Choose one of two:**

**Option A – Rule-based (fast, low cost):**
- Pattern match for intent (like extended intent_cache)
- Keyword extraction for entities
- Heuristic for required_evidence from intent
- Risk level from keywords (refund, legal, billing → high)

**Option B – LLM-small (more accurate):**
- Call small LLM (gpt-4o-mini, Claude Haiku) with structured prompt
- Output JSON → QuerySpec
- Requires prompt engineering + fallback on parse fail

**Recommendation:** Start with Option A, then add Option B as enhancement (config switch).

### 4.3 Normalizer Integration

- `AnswerService.generate()`: call Normalizer before Retrieval
- If QuerySpec exists: pass `keyword_queries`, `semantic_queries`, `required_evidence` to Retrieval and Evidence Quality Gate
- If not (fallback): use current flow (QueryRewrite)

### 4.4 User context (optional in Phase 2)

**API schema:**
```python
class MessageCreate(BaseModel):
    content: str
    # Optional, for future multi-tenant
    tenant_id: str | None = None
    locale: str | None = None  # vi, en
```

- Read from `conversation.metadata` or header if present
- Pass to Normalizer for adjustment (e.g. locale → clarifying_questions in appropriate language)

---

## 5. Phase 3 – Decision Router & Budget (2–3 weeks)

**Goal:** Decision Router runs before Answer Generation; add budget controls.

### 5.1 Decision Router (pre-answer)

**File:** `app/services/decision_router.py`

**Logic:**
- Input: `QualityReport`, `QuerySpec.risk_level`, `constraints` completeness
- Output: `PASS` | `ASK_USER` | `ESCALATE` + **reason** (to distinguish ASK_USER types)

**Distinguish ASK_USER (pre-generation):**

| Cause | Decision | Response type |
|-------|----------|---------------|
| **Missing constraints** | ASK_USER | "I need a bit more info: budget? region? plan type?" — clarifying questions |
| **Missing evidence quality** | ASK_USER | "I couldn't find enough specific info on X. Could you rephrase or specify?" — evidence gap |
| all required features >= threshold AND (optional) aggregate >= threshold | PASS | → Generate |
| high-risk AND insufficient/ambiguous evidence | ESCALATE | → Human |

**Output schema:**
```python
@dataclass
class DecisionResult:
    decision: str  # PASS | ASK_USER | ESCALATE
    reason: str    # "missing_constraints" | "missing_evidence_quality" | "sufficient" | "high_risk_insufficient"
    clarifying_questions: list[str]  # for ASK_USER
    partial_links: list[str]         # for ASK_USER (evidence gap)
```

**ASK_USER response (missing_constraints):**
- State what constraints are missing
- Ask 1–3 clarifying questions
- Human tone

**ASK_USER response (missing_evidence_quality):**
- State what evidence is missing (from `missing_signals`)
- Provide partial useful links (if any)
- Suggest rephrase or narrow scope
- Human tone, not system error

**Integration:** Run after Evidence Quality Gate, before calling LLM. If ASK_USER or ESCALATE → return immediately, do not generate.

### 5.2 Budget controls

**Config:**
```python
retrieval_latency_budget_ms: int = 5000  # total retrieval time across attempts
retrieval_token_budget: int = 0  # 0 = no limit
```

**Logic:**
- In retry loop: measure total latency from retrieval
- If exceeds budget → stop retry, escalate or ASK_USER
- Token budget: if using LLM for normalizer, accumulate tokens; if exceeds → skip normalizer or use rule-based

---

## 6. Phase 4 – Polish (1–2 weeks)

### 6.1 Answer QA Gate – Tone compliance

- Add check in Reviewer: tone should be human, not robotic
- Heuristic: overly long sentences, too many bullets, no follow-up question → flag

### 6.2 Full observability

- Log QuerySpec per request
- Dashboard/metrics: quality_score distribution, retry rate by missing_signal, decision latency

---

## 7. Recommended Implementation Order

| # | Task | Phase | Effort | Dependencies |
|---|------|-------|--------|--------------|
| 0 | Evidence Hygiene (boilerplate + density logging) | 0.5 | 3–4 days | 0 |
| 1 | Evidence Quality Gate (domain-agnostic, feature scores) | 1 | 3–4 days | 0 |
| 2 | Retry Planner (fixed ladder, max 2, Attempt2 precision) | 1 | 2–3 days | 1 |
| 3 | Integrate Gate + Planner into AnswerService | 1 | 1–2 days | 1, 2 |
| 4 | Observability (QualityReport feature_scores, metrics) | 1 | 1 day | 3 |
| 5 | QuerySpec schema + Rule-based Normalizer | 2 | 3–4 days | 0 |
| 6 | Integrate Normalizer into flow | 2 | 2 days | 5, 3 |
| 7 | User context (optional) | 2 | 1 day | 6 |
| 8 | Decision Router (ASK_USER: constraints vs evidence) | 3 | 2–3 days | 1, 5 |
| 9 | Budget controls | 3 | 1–2 days | 8 |
| 10 | Tone compliance + Polish | 4 | 1–2 days | 0 |

---

## 8. Final Flow (after completion)

```
Input → Intent Cache → Normalizer → QuerySpec
  → Retrieval (Attempt 1: broad hybrid)
  → Evidence Quality Gate (feature scores → QualityReport)
    → any required feature < threshold: Retry Planner (missing_signals) → Retrieval (Attempt 2: precision + context expansion)
    → all required features OK: Decision Router
      → PASS: Answer Generator → Answer QA Gate → Output
      → ASK_USER (missing_constraints): clarifying questions (no LLM)
      → ASK_USER (missing_evidence_quality): evidence gap response (no LLM)
      → ESCALATE: Return escalation (no LLM)
```

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|-------------|
| Evidence Quality Gate too strict → many ASK_USER | Start per-feature thresholds low (0.2–0.3); tune per Phase 0.5 dashboard |
| Normalizer LLM increases latency | Use Option A (rule-based) first; LLM async if needed |
| Breaking API change | Keep MessageCreate unchanged; user_context optional |
| Too many retries → slow | Max 2 attempts; latency budget |

---

## 10. Implementation Checklist

### Phase 0.5 – Evidence Hygiene
- [ ] Create `app/services/evidence_hygiene.py`: boilerplate detection + content density
- [ ] Top evidence signatures: pct_with_url, pct_with_number_unit, pct_boilerplate_gt_06, median_content_density
- [ ] Log per-chunk and aggregate to debug (no gating)
- [ ] Log pipeline for analysis/dashboard

### Phase 1 – Evidence Quality Gate + Retry Planner
- [ ] Create `app/services/evidence_quality.py`: domain-agnostic scoring by features
- [ ] Split links: `has_any_url`, `has_transaction_link`; transactional query → require transaction_link
- [ ] `policy_language` based on normative patterns (obligation, entitlement, scope)
- [ ] PASS = all required features >= per-feature thresholds (not just aggregate)
- [ ] `QualityReport` with `feature_scores`, `missing_signals` (derived from features)
- [ ] Retry Attempt 2: context_expansion default when boilerplate high (menu page chunks)
- [ ] Create `app/services/retry_planner.py`: fixed ladder (max 2), Attempt2 precision by missing_signals
- [ ] LLM suggested_queries fallback only
- [ ] Update `RetrievalService.retrieve()` to accept `retry_strategy`, `attempt`
- [ ] Update `AnswerService.generate()`: Gate before generate, Retry Planner for Attempt 2
- [ ] Log QualityReport (feature_scores, missing_signals), RetryStrategy
- [ ] Add metric `evidence_quality_score`
- [ ] Unit tests for Evidence Quality Gate and Retry Planner

### Phase 2 – Request Normalization
- [x] QuerySpec schema (`app/services/schemas.py`)
- [x] Rule-based Normalizer (`app/services/normalizer.py`): intent, entities, required_evidence, risk_level
- [x] Ambiguity detection ("what diff from this?" + pasted content)
- [x] Integrate Normalizer into AnswerService (before Retrieval)
- [x] RetrievalService accepts `query_spec`, uses keyword_queries/semantic_queries when present

### Phase 3 – Decision Router
- [x] Decision Router (`app/services/decision_router.py`)
- [x] `DecisionResult.reason`: `ambiguous_query` | `missing_constraints` | `missing_evidence_quality` | `high_risk_insufficient` | `sufficient`
- [x] ASK_USER response varies by reason (no LLM call)
- [x] Integrate Decision Router into AnswerService (after Evidence Quality Gate, before LLM)
- [x] Budget controls: `retrieval_latency_budget_ms`, `retrieval_token_budget`

---

*Updated: Phase 2 Normalizer + Phase 3 Decision Router implemented. Ambiguity short-circuit before retrieval.*
