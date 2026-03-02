# Plan: LLM Orchestration + Review + English-only with Auto-translate

## 1. Goal Overview

- **LLM controls flow**: LLM orchestrator drives steps, decides next step
- **LLM review**: After each important step, LLM reviews output before moving on
- **English-only**: Process only English; non-English input → LLM translates to English first

---

## 2. Proposed Flow (high-level)

```
[Input] → Language Gate (detect + translate) → [English Query]
    ↓
[LLM Orchestrator] → Decide: Intent Cache? / Normalize? / Skip? / Ambiguous?
    ↓
[Normalizer] → QuerySpec
    ↓
[Review 1: QuerySpec] ← LLM validate intent, required_evidence
    ↓
[Retrieval] → EvidencePack
    ↓
[Review 2: Evidence] ← LLM validate relevance
    ↓
[Quality Gate] → pass/fail
    ↓
[Hybrid Decision Router] → PASS / ASK_USER / ESCALATE (Deterministic + LLM gray zone)
    ↓
[LLM Generate] → Answer + citations
    ↓
[Review 3: Answer] ← LLM validate grounded, citations
    ↓
[Output] (English)
```

---

## 3. Steps That Should Have LLM Review After Completion

| # | Step | Output to review | Why review | Action on fail |
|---|------|------------------|------------|----------------|
| 1 | **Normalizer** | QuerySpec | Wrong intent/entities/required_evidence → retrieval + answer wrong | LLM suggest correction → retry normalizer or override |
| 2 | **Retrieval** | EvidencePack | Irrelevant evidence → wasted tokens, poor answer | LLM suggest query rewrite → retry retrieval |
| 3 | **Answer Generation** | Answer + citations | Answer not grounded, wrong citations | LLM suggest fix or ESCALATE |

**No separate LLM review needed:**
- Language Gate: rule-based detect + merge translate in Normalizer
- Quality Gate: rule-based, explainable, stable

**Hybrid Decision Router:** Deterministic + LLM for gray zone (see Phase 4).

---

## 4. Phase Details

### Phase 0: Language Gate (new)

**Input:** `user_message`

**Logic:**
1. **Detect language**: Rule-based (langdetect, fasttext) or lightweight LLM
   - If English → pass through
   - If not English → call LLM to translate to English
2. **Output:** `(query_en: str, source_lang: str | None)`
   - `source_lang=None` → already English
   - `source_lang="vi"` → translated from Vietnamese (can be used to translate answer back later)

**Config:** `language_gate_enabled`, `language_gate_translate_non_english`

---

### Phase 1: LLM Orchestrator (new)

**Input:** `query_en`, `conversation_history`

**LLM decides:**
- `skip_intent_cache`: does intent cache match? (who am i, what can you do)
- `skip_retrieval`: is it a greeting?
- `is_ambiguous`: is the query ambiguous?
- `next_step`: "intent_cache" | "normalize" | "ask_user" | "retrieve"

**Output:** `OrchestratorDecision`

**Benefit:** Replace rigid rules with LLM, more flexible for complex queries.

---

### Phase 2: Normalizer (existing)

**Output:** QuerySpec

**Review 1 – QuerySpec Review (new):**
- LLM receives: `query`, `QuerySpec`
- Asks: "Is intent correct? Are required_evidence appropriate for this query?"
- Output: `{ "pass": true | false, "suggestions": [...], "override": {...} }`
- If pass=false: can override QuerySpec or retry

---

### Phase 3: Retrieval (existing)

**Output:** EvidencePack

**Review 2 – Evidence Relevance Review (new):**
- LLM receives: `query`, `evidence_summaries` (top 3–5 chunks)
- Asks: "Is this evidence relevant to the query? Should we retry with different query?"
- Output: `{ "pass": true | false, "suggested_query": "...", "reason": "..." }`
- If pass=false: retry retrieval with suggested_query (if attempts remain)

---

### Phase 4: Quality Gate + Hybrid Decision Router

**Quality Gate:** Keep rule-based.

**Hybrid Decision Router (new):**
- Deterministic first: high-risk + no policy → ESCALATE (mandatory)
- Gray zone: LLM decides PASS / ASK_USER / ESCALATE
- Constraint: LLM cannot override ESCALATE → PASS

---

### Phase 5: Answer Generation (existing)

**Output:** Answer + citations

**Review 3 – Answer Review (upgrade Reviewer):**
- Current: rule-based Reviewer
- Proposal: **LLM Reviewer** replace or supplement rule-based
- LLM receives: `query`, `answer`, `citations`, `evidence`
- Asks: "Is the answer grounded in evidence? Are citations correct? Any hallucination?"
- Output: `{ "pass": true | false, "issues": [...], "suggested_fix": "..." }`
- If pass=false: can retry generate with suggested_fix or ASK_USER/ESCALATE

---

## 5. Development Plan (phases)

### Phase A: Language Gate (1–2 days)

| Task | Description |
|------|-------------|
| A1 | Add `langdetect` or fasttext for language detection |
| A2 | Add LLM translate step when `lang != "en"` |
| A3 | Config: `language_gate_enabled`, `language_gate_translate_non_english` |
| A4 | Integrate into `answer_service.generate()` at pipeline start |

**Output:** Input is always English before processing.

---

### Phase B: LLM Orchestrator (2–3 days)

| Task | Description |
|------|-------------|
| B1 | Design prompt for `OrchestratorDecision` schema |
| B2 | Implement `orchestrator_llm.py` – call LLM, parse JSON |
| B3 | Replace logic: Intent Cache, skip_retrieval, ambiguous with Orchestrator output |
| B4 | Fallback: when LLM fails → use current rule-based |
| B5 | Config: `orchestrator_use_llm` |

**Output:** LLM decides flow instead of fixed rules.

---

### Phase C: QuerySpec Review (1–2 days)

| Task | Description |
|------|-------------|
| C1 | Prompt: "Review QuerySpec for query X. Is intent/required_evidence correct?" |
| C2 | Implement `review_query_spec()` – call LLM, parse pass/suggestions |
| C3 | When pass=false: override QuerySpec or retry normalizer |
| C4 | Config: `normalizer_review_enabled` |

**Output:** QuerySpec is LLM-reviewed before retrieval.

---

### Phase D: Evidence Relevance Review (1–2 days)

| Task | Description |
|------|-------------|
| D1 | Prompt: "Review evidence relevance for query X. Is it relevant?" |
| D2 | Implement `review_evidence_relevance()` |
| D3 | When pass=false: retry retrieval with suggested_query (attempt 2) |
| D4 | Config: `retrieval_review_enabled` |

**Output:** Evidence is LLM-reviewed before generate.

---

### Phase E: LLM Answer Reviewer (2–3 days)

| Task | Description |
|------|-------------|
| E1 | Design prompt for Answer Review (grounded, citations, hallucination) |
| E2 | Implement `LLMReviewerGate` – replace/supplement `ReviewerGate` |
| E3 | When pass=false: retry generate with feedback or ASK_USER/ESCALATE |
| E4 | Config: `reviewer_use_llm` (rule-based remains fallback) |

**Output:** Answer is LLM-reviewed before returning to user.

---

### Phase F: Integration & Optimization (1–2 days)

| Task | Description |
|------|-------------|
| F1 | Consolidated config, enable/disable each review |
| F2 | Cost tuning: use lightweight model for review (gpt-4o-mini) |
| F3 | Timeout, retry for each LLM call |
| F4 | Metrics: review_pass_rate, review_retry_count |

---

## 6. Recommended Implementation Order

```
1. Phase A (Language Gate)     → Foundation: input always English
2. Phase C (QuerySpec Review) → Improve QuerySpec quality
3. Phase E (LLM Answer Review) → Improve answer quality (high impact)
4. Phase D (Evidence Review)   → Reduce token waste
5. Phase B (Orchestrator)     → Make flow flexible (most complex)
6. Phase F (Integration)      → Finalize
```

---

## 7. Consolidated Config

```env
# Language Gate
LANGUAGE_GATE_ENABLED=true
LANGUAGE_GATE_TRANSLATE_NON_ENGLISH=true

# Orchestrator
ORCHESTRATOR_USE_LLM=false

# Normalizer
NORMALIZER_USE_LLM=true
NORMALIZER_REVIEW_ENABLED=true

# Retrieval
RETRIEVAL_REVIEW_ENABLED=true

# Reviewer
REVIEWER_USE_LLM=true
REVIEWER_LLM_MODEL=gpt-4o-mini
```

---

## 8. Cost & Latency Estimates

| Step | LLM call | Model | Est. tokens | Latency |
|------|----------|-------|-------------|---------|
| Language translate | 1 | gpt-4o-mini | ~500 | ~200ms |
| Orchestrator | 1 | gpt-4o-mini | ~300 | ~150ms |
| Normalizer | 1 | gpt-4o-mini | ~400 | ~200ms |
| QuerySpec Review | 1 | gpt-4o-mini | ~300 | ~150ms |
| Evidence Review | 1 | gpt-4o-mini | ~500 | ~200ms |
| Answer Generate | 1 | gpt-4o | ~2000 | ~1s |
| Answer Review | 1 | gpt-4o-mini | ~600 | ~250ms |

**Total added:** ~4–5 LLM calls (when all enabled) → ~2–3s latency, ~$0.01–0.02/request (estimate).

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Higher cost | Enable each review via config; use lightweight model for review |
| High latency | Run in parallel when possible; cache when possible |
| LLM review wrong | Keep rule-based as fallback; log for analysis |
| Translation wrong | Translate only when detection is confident; can add "confidence" |

---

## 10. Summary

- **Language Gate**: Detect + translate non-English → English
- **Review points**: QuerySpec, Evidence, Answer (3 points)
- **Orchestrator**: LLM decides flow (optional, later phase)
- **Implementation order**: A → C → E → D → B → F
