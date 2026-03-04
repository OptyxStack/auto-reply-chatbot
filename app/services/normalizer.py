"""Request Normalizer – Phase 2: QuerySpec from raw query.

LLM-only: all queries go through LLM. Minimal fallback when LLM fails.
"""

import json
import re
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm_gateway import get_llm_gateway
from app.services.schemas import QuerySpec

logger = get_logger(__name__)

# LLM prompt for QuerySpec extraction (language-aware: translates if non-English)
NORMALIZER_SYSTEM_PROMPT_BASE = """You are a query analyzer for a support chatbot.

Analyze the user's query and conversation context. Output JSON only, no markdown.

Output schema:
{
  "canonical_query_en": "English translation or original if already English",
  "intent": "transactional|comparison|policy|troubleshooting|account|informational|ambiguous|social",
  "entities": ["product", "pricing", "plan", ...],
  "required_evidence": ["numbers_units", "transaction_link", "policy_language", "steps_structure", "has_any_url"],
  "risk_level": "low|medium|high",
  "is_ambiguous": false,
  "clarifying_questions": [],
  "keyword_queries": ["primary phrase for BM25 keyword search"],
  "semantic_queries": ["primary phrase for vector/semantic search"],
  "retrieval_rewrites": ["phrase1", "phrase2", ...],
  "skip_retrieval": false,
  "canned_response": "optional greeting when skip_retrieval is true",
  "product_type": "optional: main product/category from query (e.g. vps, dedicated, plan_a)",
  "os": "optional: OS or environment (e.g. windows, linux, macos)",
  "comparison_targets": ["optional: when comparing, list 2-3 items being compared"],
  "billing_cycle": "optional: monthly or yearly if mentioned"
}

keyword_queries: 1-2 phrases for BM25. Extract ONLY the current question's core terms. Ignore irrelevant prior messages (greetings, lyrics, noise). Example: "i forgot my account password" -> ["forgot password account recovery reset password"].
semantic_queries: 1-2 natural phrases for vector search. Same rule: use only the current user intent. Example: "i forgot my account password" -> ["forgot account password reset recovery"].

retrieval_rewrites: 2-5 short phrases for retry. Include synonyms and doc terms: "product pricing", "plan comparison". For policy queries (refund, terms), prefer policy-focused phrases first: "refund policy", "terms of service" before "order cancellation" (which can match order links). Empty if not needed.

Intent rules:
- social: ONLY pure greetings, thanks, or farewells with NO product/service/question. Examples: hi, hello, hey, hiii, chào, thanks, ok, bye. NOT social: "do you have X", "what plans do you offer", "do you provide Y" – these ask about products/services and need retrieval (use informational or transactional).
- transactional: price, cost, order, buy, subscribe, mua, giá, product names
- comparison: diff, compare, vs, khác, so sánh
- policy: refund, policy, terms, cancellation, hoàn tiền
- troubleshooting: how, step, setup, cách, hướng dẫn, fix
- account: account, login, billing, tài khoản
- informational: questions about products, services, features (do you provide X, do you have X, what is X, tell me about X)
- ambiguous: referent unclear (e.g. "what diff from this?") when user refers to prior message

skip_retrieval: true ONLY when intent is social. If the user asks about any product, service, or feature, use informational or transactional and skip_retrieval=false.
canned_response: when skip_retrieval is true, provide a friendly greeting like "Hello! Welcome. How can I help you today?"

Entities: domain terms relevant to the support context (e.g. product names, pricing, plans, features). Include synonyms if relevant.

product_type, os, comparison_targets, billing_cycle: Infer from the query when clear. E.g. "VPS pricing for Windows" -> product_type: "vps", os: "windows". "compare dedicated vs VDS" -> comparison_targets: ["dedicated", "vds"]. "monthly plans" -> billing_cycle: "monthly". Omit when not mentioned.

required_evidence: only include what the query needs:
- numbers_units: price/cost/specs
- transaction_link: order link, buy link
- policy_language: refund, terms, policy
- steps_structure: how-to, setup guide
- has_any_url: general links

risk_level: high for refund/legal/billing dispute/abuse; medium for cancellation/policy; low otherwise.

is_ambiguous: true if referent unclear (e.g. "this", "that" referring to prior content).

clarifying_questions: 1-3 questions when is_ambiguous; empty otherwise.

canonical_query_en: If the query is NOT in English, translate it to English first. Use this as the canonical form for retrieval. If already English, copy the query as-is."""

# Intent patterns (extended from intent_cache)
INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("transactional", ["price", "cost", "pricing", "order", "buy", "subscribe", "mua", "giá", "bao nhiêu"]),
    ("comparison", ["diff", "difference", "compare", "vs", "versus", "khác", "so sánh"]),
    ("policy", ["refund", "policy", "terms", "cancellation", "hoàn tiền", "chính sách"]),
    ("troubleshooting", ["how", "step", "setup", "cách", "hướng dẫn", "fix", "error"]),
    ("account", ["account", "login", "billing", "tài khoản"]),
    ("informational", []),  # default fallback
]

# Risk keywords → risk_level
RISK_HIGH = ["refund", "legal", "billing dispute", "abuse", "chargeback"]
RISK_MEDIUM = ["cancellation", "policy", "terms", "sla"]

# Stopwords: don't add to query context (noise)
CONTEXT_STOPWORDS = {"hello", "hi", "hey", "chào", "xin", "thanks", "thank", "ok", "okay"}

# Queries that need NO retrieval – greetings, social (rule-based path when normalizer_use_llm=False)
SKIP_RETRIEVAL_PATTERN = re.compile(
    r"^(hi|hello|hey|chào|xin\s*chào|thanks|thank\s*you|ok|okay|bye|goodbye|good\s*morning|good\s*afternoon|good\s*evening)\s*[!?.,;:\s\]]*$",
    re.I,
)
def _get_greeting_response() -> str:
    """Greeting for skip-retrieval queries. Uses app_name from config when set."""
    app_name = get_settings().app_name.strip()
    if app_name:
        return f"Hello! Welcome to {app_name} support. How can I help you today?"
    return "Hello! Welcome. How can I help you today?"

# Ambiguity: referent unclear
AMBIGUITY_PATTERNS = [
    r"what\s+diff(?:erence)?\s+from\s+this",
    r"what(?:'s)?\s+different\s+from\s+this",
    r"what\s+about\s+this",
    r"compare\s+to\s+this",
    r"diff\s+from\s+this",
    r"so\s+what\s+about\s+this",
]
AMBIGUITY_RE = re.compile("|".join(AMBIGUITY_PATTERNS), re.I)

# Citation-like content (user pasted our response)
CITATION_PATTERN = re.compile(r"\[[\w-]+\s+\|\s+https?://", re.I)


def _get_configured_domain_terms() -> list[str]:
    """Return normalized domain terms from config for optional rule enrichment."""
    raw_terms = (get_settings().normalizer_domain_terms or "").strip()
    if not raw_terms:
        return []

    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in raw_terms.split(","):
        term = raw_term.strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _parse_comma_list(raw: str) -> list[str]:
    """Parse comma-separated config string into normalized list."""
    if not (raw or "").strip():
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        t = item.strip().lower()
        if t and t not in seen:
            seen.add(t)
            terms.append(t)
    return terms


def _get_configured_slot_product_types() -> list[str]:
    """Return product types for slot extraction from config. Empty = disabled."""
    return _parse_comma_list(getattr(get_settings(), "normalizer_slot_product_types", "") or "")


def _get_configured_slot_os_types() -> list[str]:
    """Return OS types for os slot from config. Empty = disabled."""
    return _parse_comma_list(getattr(get_settings(), "normalizer_slot_os_types", "") or "")


def _collect_config_overrides_applied() -> list[str]:
    """Expose which hybrid normalizer compatibility switches are active."""
    settings = get_settings()
    overrides: list[str] = []
    if _get_configured_domain_terms():
        overrides.append("normalizer_domain_terms")
    if getattr(settings, "normalizer_query_expansion", False):
        overrides.append("normalizer_query_expansion")
    if getattr(settings, "normalizer_slots_enabled", False):
        overrides.append("normalizer_slots_enabled")
    if _get_configured_slot_product_types():
        overrides.append("normalizer_slot_product_types")
    if _get_configured_slot_os_types():
        overrides.append("normalizer_slot_os_types")
    return overrides


def _infer_intent(query: str) -> str:
    q = query.lower().strip()
    for intent, keywords in INTENT_PATTERNS:
        if intent == "informational":
            continue
        if any(kw in q for kw in keywords):
            return intent
    return "informational"


def _extract_entities(query: str) -> list[str]:
    """Extract configured domain entities from query."""
    domain_terms = _get_configured_domain_terms()
    if not domain_terms:
        return []

    entities: list[str] = []
    q = query.lower()
    for term in domain_terms:
        if term in q:
            entities.append(term)
    return list(dict.fromkeys(entities))


def _infer_required_evidence(intent: str, query: str) -> list[str]:
    """Infer required_evidence from intent and query."""
    q = query.lower()
    required: list[str] = []
    if intent == "transactional" or any(kw in q for kw in ["price", "cost", "pricing", "giá"]):
        required.extend(["numbers_units", "transaction_link"])
    if intent == "comparison" or any(kw in q for kw in ["diff", "difference", "compare", "khác", "so sánh"]):
        required.extend(["numbers_units", "has_any_url"])
    if any(kw in q for kw in ["link", "order", "mua", "buy", "subscribe"]):
        required.append("transaction_link")
    if intent == "policy" or any(kw in q for kw in ["refund", "policy", "terms"]):
        required.append("policy_language")
    if intent == "troubleshooting" or any(kw in q for kw in ["how", "step", "cách"]):
        required.append("steps_structure")
    return list(dict.fromkeys(required))


def _infer_minimal_required_evidence(intent: str, query: str) -> list[str]:
    """Infer minimal generic required_evidence for hybrid normalizer mode."""
    q = query.lower()
    required: list[str] = []

    if intent == "policy" or any(kw in q for kw in ["refund", "policy", "terms"]):
        required.append("policy_language")
    if intent == "troubleshooting" or any(kw in q for kw in ["how", "step", "cÃ¡ch"]):
        required.append("steps_structure")
    if intent == "comparison":
        required.append("has_any_url")
    if any(kw in q for kw in ["link", "url", "docs", "documentation"]):
        required.append("has_any_url")

    return list(dict.fromkeys(required))


def _infer_risk_level(query: str) -> str:
    q = query.lower()
    for kw in RISK_HIGH:
        if kw in q:
            return "high"
    for kw in RISK_MEDIUM:
        if kw in q:
            return "medium"
    return "low"


def _detect_ambiguity(
    query: str,
    conversation_history: list[dict[str, str]] | None,
) -> tuple[bool, list[str]]:
    """Detect if query is ambiguous (referent unclear). Returns (is_ambiguous, clarifying_questions)."""
    q = query.strip()
    # Short query with "this/that" referent
    has_ambiguous_phrase = bool(AMBIGUITY_RE.search(q))
    # User pasted long content (citation format or >200 chars)
    has_pasted_content = len(q) > 200 or bool(CITATION_PATTERN.search(q))
    # Or: short query + last assistant message was long (user referring to our answer)
    last_assistant_long = False
    if conversation_history and not has_pasted_content:
        for m in reversed(conversation_history):
            if m.get("role") == "assistant":
                content = (m.get("content") or "").strip()
                if len(content) > 150:
                    last_assistant_long = True
                break

    is_ambiguous = has_ambiguous_phrase and (has_pasted_content or last_assistant_long or len(q) > 100)
    if not is_ambiguous:
        return False, []

    clarifying = [
        "What would you like to compare this with? Another provider's offer, or a specific plan?",
        "Could you specify what 'this' refers to? For example: a competitor's plan, or a different product?",
    ]
    return True, clarifying


def _infer_user_goal(intent: str, query: str) -> str:
    """Infer the user goal from intent and query wording."""
    q = query.lower()
    if any(kw in q for kw in ["order", "buy", "subscribe", "checkout", "store", "link"]):
        return "order_link"
    if any(kw in q for kw in ["price", "cost", "pricing", "bao nhi", "gia"]):
        return "price_lookup"
    if any(kw in q for kw in ["refund", "policy", "terms", "cancellation"]):
        return "refund_policy"
    if intent == "comparison" or any(kw in q for kw in ["compare", "diff", "difference", "vs", "versus"]):
        return "feature_compare"
    if intent == "troubleshooting" or any(kw in q for kw in ["how", "setup", "install", "fix", "error", "step"]):
        return "setup_steps"
    if intent == "account":
        return "account_help"
    return "general_info"


def _extract_slots(query: str, entities: list[str]) -> dict[str, Any]:
    """Extract optional deployment-specific slots when enabled. Product/OS types come from config."""
    if not getattr(get_settings(), "normalizer_slots_enabled", False):
        return {}

    q = query.lower()
    slots: dict[str, Any] = {}

    product_types = _get_configured_slot_product_types()
    if product_types:
        for product in product_types:
            if product in entities:
                slots["product_type"] = product
                break
        comparison_targets = [name for name in product_types if name in entities]
        if len(comparison_targets) >= 2:
            slots["comparison_targets"] = comparison_targets[:3]

    os_types = _get_configured_slot_os_types()
    if os_types:
        for os_name in os_types:
            if os_name in entities:
                slots["os"] = os_name
                break

    if any(kw in q for kw in ["monthly", "/mo", "per month", "month"]):
        slots["billing_cycle"] = "monthly"
    elif any(kw in q for kw in ["annually", "annual", "yearly", "/year", "per year"]):
        slots["billing_cycle"] = "yearly"

    region_map = {
        "singapore": "sg",
        " sg ": "sg",
        "usa": "us",
        " us ": "us",
        "europe": "eu",
        "vietnam": "vn",
        " thailand ": "th",
    }
    q_with_pad = f" {q} "
    for needle, code in region_map.items():
        if needle in q_with_pad:
            slots["region"] = code
            break

    if any(kw in q for kw in ["order", "buy", "subscribe", "checkout", "store", "link"]):
        slots["requested_action"] = "order_link"
    elif any(kw in q for kw in ["price", "cost", "pricing"]):
        slots["requested_action"] = "price_lookup"

    return slots


def _infer_missing_slots(intent: str, query: str, resolved_slots: dict[str, Any]) -> list[str]:
    """Infer missing slots that could improve answer precision."""
    if not getattr(get_settings(), "normalizer_slots_enabled", False):
        return []

    q = query.lower()
    missing: list[str] = []

    if intent == "transactional":
        if any(kw in q for kw in ["price", "cost", "pricing", "order", "buy", "link"]) and "product_type" not in resolved_slots:
            missing.append("product_type")
        if any(kw in q for kw in ["price", "cost", "pricing"]) and "billing_cycle" not in resolved_slots:
            missing.append("billing_cycle")

    if intent == "comparison" and "comparison_targets" not in resolved_slots:
        missing.append("comparison_target")

    if intent == "troubleshooting" and "os" not in resolved_slots and "environment" not in resolved_slots:
        missing.append("environment")

    return list(dict.fromkeys(missing))


def _infer_ambiguity_type(is_ambiguous: bool, missing_slots: list[str]) -> str | None:
    """Classify ambiguity without changing current routing semantics."""
    if is_ambiguous:
        return "referential"
    if missing_slots:
        return "missing_constraints"
    return None


def _infer_retrieval_profile(intent: str, user_goal: str) -> str:
    """Map user intent and goal to a future retrieval profile."""
    if user_goal in ("price_lookup", "order_link") or intent == "transactional":
        return "pricing_profile"
    if user_goal == "refund_policy" or intent == "policy":
        return "policy_profile"
    if user_goal == "setup_steps" or intent == "troubleshooting":
        return "troubleshooting_profile"
    if user_goal == "feature_compare" or intent == "comparison":
        return "comparison_profile"
    if intent == "account":
        return "account_profile"
    return "generic_profile"


def _split_requirements(required_evidence: list[str], user_goal: str) -> tuple[list[str], list[str]]:
    """Split evidence requirements into hard and soft groups."""
    hard = list(dict.fromkeys(required_evidence))
    soft: list[str] = []

    if user_goal == "order_link" and "transaction_link" not in hard:
        hard.append("transaction_link")
    if user_goal == "price_lookup" and "numbers_units" not in hard:
        hard.append("numbers_units")
    if user_goal == "refund_policy" and "policy_language" not in hard:
        hard.append("policy_language")
    if user_goal == "setup_steps" and "steps_structure" not in hard:
        hard.append("steps_structure")

    if user_goal in ("price_lookup", "feature_compare") and "has_any_url" not in hard:
        soft.append("has_any_url")
    if user_goal == "general_info" and "has_any_url" not in hard:
        soft.append("has_any_url")

    return hard, list(dict.fromkeys(soft))


def _build_rewrite_candidates(
    query: str,
    keyword_queries: list[str],
    semantic_queries: list[str],
    user_goal: str,
    resolved_slots: dict[str, Any],
    missing_slots: list[str],
    retrieval_rewrites: list[str] | None = None,
) -> list[str]:
    """Build retrieval-friendly rewrite candidates for future retry logic."""
    candidates: list[str] = [query.strip()]
    if retrieval_rewrites:
        candidates.extend(r.strip() for r in retrieval_rewrites[:5] if r and r.strip())
    candidates.extend(keyword_queries[:2])
    candidates.extend(semantic_queries[:2])

    product_type = str(resolved_slots.get("product_type", "")).strip()
    if user_goal == "price_lookup" and product_type:
        candidates.append(f"{product_type} pricing monthly")
    if user_goal == "order_link" and product_type:
        candidates.append(f"{product_type} order link")
    if user_goal == "feature_compare" and "comparison_targets" in resolved_slots:
        targets = resolved_slots.get("comparison_targets") or []
        if isinstance(targets, list) and len(targets) >= 2:
            candidates.append(f"{targets[0]} vs {targets[1]} difference")
    if "billing_cycle" in missing_slots and product_type:
        candidates.append(f"{product_type} monthly pricing")

    return list(dict.fromkeys(c for c in candidates if c and c.strip()))


def _infer_answer_mode_hint(is_ambiguous: bool, missing_slots: list[str]) -> str:
    """Infer a future answer mode hint without changing current runtime flow."""
    if is_ambiguous:
        return "ask_user"
    if missing_slots:
        return "weak"
    return "strong"


def _build_query_spec(
    *,
    query: str,
    conversation_history: list[dict[str, str]] | None,
    intent: str,
    entities: list[str],
    required_evidence: list[str],
    risk_level: str,
    is_ambiguous: bool,
    clarifying_questions: list[str],
    source_lang: str | None = None,
    canonical_query_en: str | None = None,
    keyword_queries: list[str] | None = None,
    semantic_queries: list[str] | None = None,
    retrieval_rewrites: list[str] | None = None,
    extraction_mode: str = "rule_primary",
    llm_slots: dict[str, Any] | None = None,
) -> QuerySpec:
    """Create a richer QuerySpec while remaining backward-compatible."""
    original_query = query.strip()
    normalized_source_lang = (source_lang or "en").strip().lower() or "en"
    effective_query = (canonical_query_en or original_query).strip() or original_query
    translation_needed = bool(
        canonical_query_en
        and normalized_source_lang != "en"
        and canonical_query_en.strip()
        and canonical_query_en.strip() != original_query
    )

    if not entities:
        entities = _extract_entities(effective_query)
    if not required_evidence:
        required_evidence = _infer_minimal_required_evidence(intent, effective_query)
    if risk_level not in ("low", "medium", "high"):
        risk_level = _infer_risk_level(effective_query)

    if keyword_queries is None or semantic_queries is None:
        keyword_queries, semantic_queries = _build_queries(
            effective_query, intent, entities, conversation_history
        )

    if retrieval_rewrites:
        kw = keyword_queries[0] if keyword_queries else effective_query
        kw_lower = kw.lower()
        extra = [r.strip() for r in retrieval_rewrites[:3] if r and r.strip() and r.strip().lower() not in kw_lower]
        if extra:
            keyword_queries = [f"{kw} {' '.join(extra)}".strip()]

    resolved_slots = _extract_slots(effective_query, entities)
    if llm_slots:
        resolved_slots = {**resolved_slots, **llm_slots}
    missing_slots = _infer_missing_slots(intent, effective_query, resolved_slots)
    ambiguity_type = _infer_ambiguity_type(is_ambiguous, missing_slots)
    user_goal = _infer_user_goal(intent, effective_query)
    hard_requirements, soft_requirements = _split_requirements(required_evidence, user_goal)
    rewrite_candidates = _build_rewrite_candidates(
        effective_query,
        keyword_queries,
        semantic_queries,
        user_goal,
        resolved_slots,
        missing_slots,
        retrieval_rewrites=retrieval_rewrites,
    )
    answer_mode_hint = _infer_answer_mode_hint(is_ambiguous, missing_slots)

    return QuerySpec(
        intent=intent,
        entities=entities,
        constraints=dict(resolved_slots),
        required_evidence=required_evidence,
        risk_level=risk_level,
        keyword_queries=keyword_queries,
        semantic_queries=semantic_queries,
        clarifying_questions=clarifying_questions,
        is_ambiguous=is_ambiguous,
        canonical_query_en=canonical_query_en if translation_needed else None,
        original_query=original_query,
        source_lang=normalized_source_lang,
        translation_needed=translation_needed,
        user_goal=user_goal,
        resolved_slots=resolved_slots,
        missing_slots=missing_slots,
        ambiguity_type=ambiguity_type,
        answerable_without_clarification=not is_ambiguous,
        hard_requirements=hard_requirements,
        soft_requirements=soft_requirements,
        retrieval_profile=_infer_retrieval_profile(intent, user_goal),
        rewrite_candidates=rewrite_candidates,
        answer_mode_hint=answer_mode_hint,
        extraction_mode=extraction_mode,
        config_overrides_applied=_collect_config_overrides_applied(),
    )


def _build_queries(
    query: str,
    intent: str,
    entities: list[str],
    conversation_history: list[dict[str, str]] | None,
) -> tuple[list[str], list[str]]:
    """Build keyword_queries and semantic_queries for retrieval."""
    # Base: add conversation context terms
    base = query.strip()
    if conversation_history and len(conversation_history) >= 2:
        context_terms: list[str] = []
        for m in conversation_history[-4:]:
            content = (m.get("content") or "").strip()
            if m.get("role") == "user" and content and len(content) < 200:
                words = [
                    w for w in content.split()
                    if len(w) > 2 and w.lower() not in CONTEXT_STOPWORDS
                ][:5]
                context_terms.extend(words)
        if context_terms:
            seen: set[str] = set()
            unique: list[str] = []
            for t in context_terms:
                tl = t.lower()
                if tl not in seen and tl not in base.lower():
                    seen.add(tl)
                    unique.append(t)
            if unique:
                base = f"{' '.join(unique)} {base}".strip()

    semantic = base
    keyword = base

    if getattr(get_settings(), "normalizer_query_expansion", False):
        extras: list[str] = []
        if intent == "transactional":
            extras.extend(["pricing", "order"])
        elif intent == "comparison":
            extras.extend(["compare", "specs"])
        elif intent == "policy":
            extras.extend(["policy", "terms"])
        elif intent == "troubleshooting":
            extras.extend(["guide", "steps"])
        elif intent == "account":
            extras.extend(["account", "billing"])
        if entities:
            extras.extend(entities[:3])

        deduped_extras: list[str] = []
        seen_extras: set[str] = set()
        for extra in extras:
            normalized_extra = extra.strip().lower()
            if not normalized_extra or normalized_extra in seen_extras:
                continue
            seen_extras.add(normalized_extra)
            deduped_extras.append(extra.strip())
        if deduped_extras:
            keyword = f"{base} {' '.join(deduped_extras[:4])}".strip()

    return [keyword], [semantic]


def _parse_llm_slots(data: dict[str, Any]) -> dict[str, Any]:
    """Extract optional slots inferred by LLM from response. Empty/null values omitted."""
    slots: dict[str, Any] = {}
    pt = (data.get("product_type") or "").strip()
    if pt:
        slots["product_type"] = pt.lower()
    os_val = (data.get("os") or "").strip()
    if os_val:
        slots["os"] = os_val.lower()
    bc = (data.get("billing_cycle") or "").strip().lower()
    if bc in ("monthly", "yearly"):
        slots["billing_cycle"] = bc
    ct = data.get("comparison_targets")
    if isinstance(ct, list) and len(ct) >= 2:
        targets = [str(t).strip().lower() for t in ct[:3] if t]
        if len(targets) >= 2:
            slots["comparison_targets"] = targets
    return slots


def _get_normalizer_prompt(source_lang: str | None) -> str:
    """Build system prompt; add translation instruction when source is non-English."""
    base = NORMALIZER_SYSTEM_PROMPT_BASE
    if source_lang and source_lang.lower() != "en":
        base += f"\n\nIMPORTANT: The query is in {source_lang}. You MUST translate it to English and put the translation in canonical_query_en. Then analyze the English version."
    return base


async def _normalize_llm(
    query: str,
    conversation_history: list[dict[str, str]] | None,
    source_lang: str | None = None,
) -> QuerySpec | None:
    """LLM-based QuerySpec. Returns None on error (caller should fallback)."""
    from app.services.model_router import get_model_for_task

    model = get_model_for_task("normalizer")
    system_prompt = _get_normalizer_prompt(source_lang)

    user_parts = [f"Query: {query.strip()}"]
    if source_lang and source_lang != "en":
        user_parts.append(f"(Detected language: {source_lang})")
    if conversation_history and len(conversation_history) >= 2:
        ctx = "\n".join(
            f"{m.get('role', 'user')}: {(m.get('content') or '')[:300]}"
            for m in conversation_history[-4:]
        )
        user_parts.append(f"Conversation context:\n{ctx}")

    user_content = "\n\n".join(user_parts)

    try:
        from app.core.tracing import current_llm_task_var
        current_llm_task_var.set("normalizer")
        llm = get_llm_gateway()
        resp = await llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            model=model,
            max_tokens=512,
        )
        content = (resp.content or "").strip()
        # Extract JSON (handle markdown code blocks)
        if "```json" in content:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
            content = match.group(1) if match else content
        elif "```" in content:
            match = re.search(r"```\s*([\s\S]*?)\s*```", content)
            content = match.group(1) if match else content

        data = json.loads(content)

        intent = str(data.get("intent", "informational")).lower()
        if intent not in ("transactional", "comparison", "policy", "troubleshooting", "account", "informational", "ambiguous", "social"):
            intent = "informational"

        skip_retrieval = bool(data.get("skip_retrieval", False)) or intent == "social"
        canned_response = (data.get("canned_response") or "").strip()
        if skip_retrieval and not canned_response:
            canned_response = _get_greeting_response()

        if skip_retrieval:
            q_stripped = query.strip()
            return QuerySpec(
                intent="social",
                entities=[],
                constraints={},
                required_evidence=[],
                risk_level="low",
                keyword_queries=[],
                semantic_queries=[],
                clarifying_questions=[],
                is_ambiguous=False,
                skip_retrieval=True,
                canned_response=canned_response,
                original_query=q_stripped,
                source_lang=(source_lang or "en").strip().lower() or "en",
                translation_needed=False,
                user_goal="general_info",
                resolved_slots={},
                missing_slots=[],
                answerable_without_clarification=True,
                hard_requirements=[],
                soft_requirements=[],
                retrieval_profile="generic_profile",
                rewrite_candidates=[],
                answer_mode_hint="strong",
                extraction_mode="llm_primary",
                config_overrides_applied=_collect_config_overrides_applied(),
            )

        canonical_query_en = (data.get("canonical_query_en") or "").strip() or query.strip()
        entities = [str(e) for e in data.get("entities", []) if isinstance(e, str)][:10]
        if not entities:
            entities = _extract_entities(canonical_query_en)
        retrieval_rewrites = [
            str(r).strip()
            for r in data.get("retrieval_rewrites", [])
            if isinstance(r, str) and str(r).strip()
        ][:5]
        required_evidence = [str(r) for r in data.get("required_evidence", []) if isinstance(r, str)]
        if not required_evidence:
            required_evidence = _infer_minimal_required_evidence(intent, canonical_query_en)
        risk_level = str(data.get("risk_level", "low")).lower()
        if risk_level not in ("low", "medium", "high"):
            risk_level = _infer_risk_level(canonical_query_en)
        is_ambiguous = bool(data.get("is_ambiguous", False))
        clarifying_questions = [str(q) for q in data.get("clarifying_questions", []) if isinstance(q, str)][:3]
        if is_ambiguous and not clarifying_questions:
            _, clarifying_questions = _detect_ambiguity(query, conversation_history)
            clarifying_questions = clarifying_questions[:3]

        keyword_queries = [
            str(k).strip() for k in data.get("keyword_queries", [])
            if isinstance(k, str) and str(k).strip()
        ][:2]
        semantic_queries = [
            str(s).strip() for s in data.get("semantic_queries", [])
            if isinstance(s, str) and str(s).strip()
        ][:2]
        if keyword_queries or semantic_queries:
            if not keyword_queries:
                keyword_queries = semantic_queries[:1] if semantic_queries else [canonical_query_en]
            if not semantic_queries:
                semantic_queries = keyword_queries[:1] if keyword_queries else [canonical_query_en]
        else:
            keyword_queries, semantic_queries = _build_queries(
                canonical_query_en, intent, entities, conversation_history
            )

        llm_slots = _parse_llm_slots(data)

        spec = _build_query_spec(
            query=query,
            conversation_history=conversation_history,
            intent=intent,
            entities=entities,
            required_evidence=required_evidence,
            risk_level=risk_level,
            is_ambiguous=is_ambiguous,
            clarifying_questions=clarifying_questions,
            source_lang=source_lang,
            canonical_query_en=canonical_query_en,
            keyword_queries=keyword_queries,
            semantic_queries=semantic_queries,
            retrieval_rewrites=retrieval_rewrites if retrieval_rewrites else None,
            extraction_mode="llm_primary",
            llm_slots=llm_slots,
        )
        logger.info(
            "normalizer_llm",
            intent=intent,
            risk_level=risk_level,
            is_ambiguous=is_ambiguous,
            required_evidence=required_evidence,
            extraction_mode=spec.extraction_mode,
            config_overrides=spec.config_overrides_applied or [],
            retrieval_profile=spec.retrieval_profile,
            user_goal=spec.user_goal,
            missing_slots=spec.missing_slots[:3] if spec.missing_slots else [],
            canonical_query_en=canonical_query_en[:100] if canonical_query_en and len(canonical_query_en) > 100 else canonical_query_en,
            translated=spec.translation_needed,
        )
        return spec
    except Exception as e:
        logger.warning("normalizer_llm_failed", error=str(e), query_preview=query[:80])
        return None


def _build_minimal_fallback(query: str, source_lang: str | None = None) -> QuerySpec:
    """Minimal QuerySpec when LLM fails. Ensures pipeline continues."""
    q = query.strip()
    lang = (source_lang or "en").strip().lower() or "en"
    return QuerySpec(
        intent="informational",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=[q],
        semantic_queries=[q],
        clarifying_questions=[],
        is_ambiguous=False,
        skip_retrieval=False,
        canned_response=None,
        original_query=q,
        source_lang=lang,
        translation_needed=False,
        user_goal="general_info",
        resolved_slots={},
        missing_slots=[],
        answerable_without_clarification=True,
        hard_requirements=[],
        soft_requirements=[],
        retrieval_profile="generic_profile",
        rewrite_candidates=[q],
        answer_mode_hint="strong",
        extraction_mode="llm_fallback",
        config_overrides_applied=[],
    )


async def normalize(
    query: str,
    conversation_history: list[dict[str, str]] | None = None,
    locale: str | None = None,
    source_lang: str | None = None,
) -> QuerySpec:
    """Produce QuerySpec from raw query. LLM-only; minimal fallback on error."""
    q_stripped = query.strip()
    spec = await _normalize_llm(q_stripped, conversation_history, source_lang)
    if spec is not None:
        return spec
    logger.warning("normalizer_llm_fallback", reason="llm_failed", query_preview=q_stripped[:80])
    return _build_minimal_fallback(q_stripped, source_lang)
