# Comparison: archi_v3 vs PHUONG_AN_LLM_ORCHESTRATION – Pros, Cons & Plan Adjustments

## 1. Should we upgrade to archi_v3?

**Conclusion: Yes, we should upgrade.** archi_v3 has a clearer design, clean separation of LLM vs Deterministic, and is production-ready.

---

## 2. Detailed Comparison

| Aspect | archi_v3 | Current PHUONG_AN |
|--------|----------|-------------------|
| **Translation** | Merged in LLM Normalizer (1 step) | Separate Language Gate (detect + translate) |
| **Orchestrator** | None – fixed flow | LLM Orchestrator (optional) |
| **Normalizer** | LLM Normalizer: translate + QuerySpec in 1 call | Normalizer + separate QuerySpec Review |
| **Evidence** | LLM Evidence Evaluator → advise Retry Planner | Evidence Relevance Review → retry |
| **Answer** | Generate → Self-Critic → Citation Validator → Final Polish | Generate → Answer Review |
| **Translate-back** | No (output always English) | No |
| **Retry** | Self-critic: max 1 regenerate | Review fail → retry or ESCALATE |

---

## 3. Advantages of archi_v3

| Advantage | Details |
|-----------|---------|
| **More concise** | Translation merged in Normalizer → fewer steps, fewer LLM calls |
| **Clearer** | Separation: LLM (understanding, reasoning) vs Deterministic (safe, auditable) |
| **Self-Critic** | Generate → Self-Critic → regenerate once if fail → limited retry |
| **Final Polish** | Improves clarity, structure, tone (does not modify factual content) |
| **Evidence Evaluator** | Advises only, does not override deterministic gate |
| **Auditability** | Deterministic gates remain intact, easy to trace |

---

## 4. Disadvantages / Risks of archi_v3

| Disadvantage | Mitigation |
|--------------|------------|
| **Heavy LLM Normalizer** | Use lightweight model (gpt-4o-mini), optimize prompt |
| **Many LLM calls** | Enable/disable each step via config; cache when possible |
| **Final Polish may drift** | Clear prompt: "Cannot modify factual content" |
| **Self-critic + regenerate** | Limit to 1 regenerate, avoid loop |

---

## 5. Adjust PHUONG_AN Plan to Align with archi_v3

### 5.1 Remove / Merge

| Remove | Reason |
|--------|--------|
| **Separate Language Gate** | Merge into LLM Normalizer |
| **LLM Orchestrator** | archi_v3 uses fixed flow, simpler |
| **Separate QuerySpec Review** | Trust LLM Normalizer; add lightweight check if needed |

### 5.2 Add / Change

| Add | Description |
|-----|-------------|
| **Language-aware LLM Normalizer** | Accept `source_lang`, translate internally if needed, output `canonical_query_en` + QuerySpec |
| **LLM Evidence Evaluator** | Replace Evidence Review; output `relevance_score`, `coverage_gaps`, `retry_needed`, `suggested_query` – advises Retry Planner only |
| **LLM Self-Critic** | After Generate; check unsupported claims, incomplete; fail → regenerate once |
| **Deterministic Citation Validator** | Keep rule-based (already in Reviewer) |
| **LLM Final Polish** | Improve clarity, structure, tone |
| **Hybrid Decision Router** | Deterministic rules first; gray zone → LLM decides; LLM cannot override ESCALATE |

### 5.3 Remove

| Remove | Reason |
|--------|--------|
| **Translate-back** | Output to client is always English |

### 5.4 Keep Unchanged

- Deterministic Evidence Quality Gate
- Retrieval (Attempt 1 + 2, Retry Planner)
- Intent cache, skip_retrieval, ambiguous (can be handled in Normalizer)

### 5.5 Hybrid Decision Router (new)

| Component | Description |
|-----------|-------------|
| **Deterministic first** | High-risk + no policy → ESCALATE (mandatory); other hard rules |
| **LLM for gray zone** | Quality gate pass but weak evidence; quality fail but partial info; unclear risk |
| **Constraint** | LLM cannot change ESCALATE → PASS |

---

## 6. Adjusted Development Plan (per archi_v3)

### Phase A: Language Detection + LLM Normalizer (2–3 days)

| Task | Description |
|------|-------------|
| A1 | Add `langdetect` (non-LLM) → `source_lang` |
| A2 | Upgrade LLM Normalizer: accept `source_lang`, translate internally if ≠ en |
| A3 | Output: `canonical_query_en`, QuerySpec, `intent_cache_match`, `is_ambiguous`, `query_rewrites` |
| A4 | Remove separate Language Gate; integrate at pipeline start |

**Output:** One LLM call for: detect + translate (if needed) + QuerySpec.

---

### Phase B: LLM Evidence Evaluator (1–2 days)

| Task | Description |
|------|-------------|
| B1 | Prompt: evaluate relevance, coverage gaps, retry_needed, suggested_query |
| B2 | Output schema: `{ relevance_score, coverage_gaps, retry_needed, suggested_query }` |
| B3 | Advise only: Retry Planner uses `suggested_query` when retry_needed |
| B4 | Deterministic Quality Gate still decides pass/fail |

**Output:** LLM Evidence Evaluator supplements input for Retry Planner.

---

### Phase C: LLM Self-Critic + Regenerate (2 days)

| Task | Description |
|------|-------------|
| C1 | Prompt: check unsupported claims, incomplete, hallucination |
| C2 | Output: `{ pass, issues, suggested_fix }` |
| C3 | Fail → regenerate once with feedback (max 2 generation attempts) |
| C4 | Deterministic Citation Validator after Generate (keep current logic) |

**Output:** Self-Critic + 1 regenerate if fail.

---

### Phase D: LLM Final Polish (1 day)

| Task | Description |
|------|-------------|
| D1 | Prompt: improve clarity, structure, tone; do not modify factual content |
| D2 | Run after Citation Validator |
| D3 | Config: `final_polish_enabled` |

**Output:** Answer is polished before returning.

---

### Phase E: Hybrid Decision Router (1–2 days)

| Task | Description |
|------|-------------|
| E1 | Run Deterministic rules first; if clear (e.g. ESCALATE high-risk) → use directly |
| E2 | Gray zone: call LLM with query, QuerySpec, evidence summary, quality_report |
| E3 | Output: `{ decision, reason, confidence, clarifying_questions, partial_links }` |
| E4 | Constraint: LLM cannot override ESCALATE → PASS |
| E5 | Config: `decision_router_use_llm` |

**Output:** Hybrid Decision Router – hard rules + LLM for gray zone.

---

### Phase F: Integration & Optimization (1–2 days)

| Task | Description |
|------|-------------|
| F1 | Refactor `answer_service` per archi_v3 flow |
| F2 | Consolidated config, enable/disable each step |
| F3 | Metrics, logging, observability |
| F4 | Fallback when LLM fails |

---

## 7. Recommended Implementation Order

```
1. Phase A (Language Detect + LLM Normalizer)  → Foundation
2. Phase B (Evidence Evaluator)                → Improve retrieval
3. Phase C (Self-Critic + Regenerate)          → Improve answer
4. Phase D (Final Polish)                      → UX
5. Phase E (Hybrid Decision Router)            → Gray zone decisions
6. Phase F (Integration)                       → Finalize
```

---

## 8. Combined Flow (archi_v3)

```
Input
  ↓
detect_language (fast, non-LLM)
  ↓
LLM Normalizer (language-aware, translate internally if needed)
  → intent_cache_match? → return
  → is_ambiguous? → ask_user
  ↓
Retrieval Attempt 1
  ↓
LLM Evidence Evaluator (advise)
  ↓
Deterministic Evidence Quality Gate
  ├── FAIL → Retry Planner → Retrieval Attempt 2
  └── PASS
        ↓
Hybrid Decision Router (Deterministic + LLM gray zone)
  ├── ASK_USER / ESCALATE → return
  └── PASS
        ↓
LLM Answer Generation
  ↓
LLM Self-Critic
  ├── FAIL → Regenerate (max 1)
  └── PASS
        ↓
Deterministic Citation Validator
  ↓
LLM Final Polish
  ↓
Output (English)
```

---

## 9. Proposed Config (archi_v3)

```env
# Language
LANGUAGE_DETECT_ENABLED=true

# Normalizer (merge translate + QuerySpec)
NORMALIZER_USE_LLM=true
NORMALIZER_LLM_MODEL=gpt-4o-mini

# Evidence Evaluator
EVIDENCE_EVALUATOR_ENABLED=true
EVIDENCE_EVALUATOR_LLM_MODEL=gpt-4o-mini

# Self-Critic
SELF_CRITIC_ENABLED=true
SELF_CRITIC_REGENERATE_MAX=1

# Final Polish
FINAL_POLISH_ENABLED=true

# Hybrid Decision Router
DECISION_ROUTER_USE_LLM=true
DECISION_ROUTER_LLM_MODEL=gpt-4o-mini
```

---

## 10. Summary

| Question | Answer |
|----------|--------|
| **Should we upgrade to archi_v3?** | Yes – clear design, production-ready |
| **Main advantages** | Concise (merged translate), Self-Critic + limited regenerate, Final Polish, Hybrid Decision Router |
| **Plan adjustments** | Remove separate Language Gate + Orchestrator + Translate-back; merge translate into Normalizer; add Evidence Evaluator, Self-Critic, Final Polish, Hybrid Decision Router |
| **Order** | A → B → C → D → E → F |
