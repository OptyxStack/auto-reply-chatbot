"""Decision Router – Phase 3: Pre-answer decision (PASS | ASK_USER | ESCALATE).

Runs after Evidence Quality Gate, before LLM. If ASK_USER or ESCALATE, return immediately
without calling LLM – use pre-generated human response.

Hybrid mode: Deterministic first; LLM for gray zone (cannot override ESCALATE → PASS).
"""

import json
import re
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm_gateway import get_llm_gateway
from app.search.base import EvidenceChunk

from app.services.evidence_quality import QualityReport
from app.services.schemas import DecisionResult, QuerySpec

logger = get_logger(__name__)


def _extract_partial_links(evidence: list[EvidenceChunk], max_links: int = 3) -> list[str]:
    """Extract useful URLs from evidence for ASK_USER (evidence gap)."""
    seen: set[str] = set()
    links: list[str] = []
    for e in evidence:
        url = (e.source_url or "").strip()
        if url and url not in seen and url.startswith("http"):
            seen.add(url)
            links.append(url)
            if len(links) >= max_links:
                break
    return links


def _build_ask_user_missing_constraints(query_spec: QuerySpec) -> str:
    """Human response when constraints are missing."""
    qs = query_spec.clarifying_questions
    if qs:
        intro = "I'd like to help you find the right plan. "
        questions = " ".join(f"• {q}" for q in qs[:3])
        return f"{intro}Could you tell me:\n{questions}"
    return "I need a bit more info to help. Could you specify your budget, preferred region, or plan type?"


def _build_ask_user_evidence_gap(
    query_spec: QuerySpec,
    quality_report: QualityReport,
    partial_links: list[str],
) -> str:
    """Human response when evidence quality is insufficient."""
    missing = quality_report.missing_signals

    # When we have relevant links, lead with them (user can self-serve)
    if partial_links:
        intro = "I found some relevant pages but couldn't extract enough detail for a full answer. "
        links = "\n".join(f"• {url}" for url in partial_links[:3])
        return f"{intro}Here are links you can check:\n{links}\n\nCould you rephrase your question or tell me what specifically you need?"

    if not missing:
        return "I couldn't find enough specific information. Could you rephrase or narrow your question?"

    parts = ["I couldn't find enough specific info on this in our docs."]
    if "missing_numbers" in missing:
        parts.append("Pricing details are missing.")
    if "missing_links" in missing or "missing_transaction_link" in missing:
        parts.append("Direct order links are missing.")
    if "missing_policy" in missing:
        parts.append("Policy/terms details are missing.")
    parts.append("Could you rephrase or specify what you need?")
    return " ".join(parts)


def _build_ask_user_ambiguous(query_spec: QuerySpec) -> str:
    """Human response when query is ambiguous."""

    qs = query_spec.clarifying_questions
    if qs:
        intro = "I'd like to clarify. "
        questions = "\n".join(f"• {q}" for q in qs[:3])
        return f"{intro}\n{questions}"
    return "Could you clarify what you need? For example: a specific product, feature, or topic?"


def _build_escalate_response() -> str:
    return "This request requires human review. A support agent will follow up shortly."


def _resolve_hard_requirements(
    query_spec: QuerySpec | None,
    required_evidence: list[str],
) -> list[str]:
    """Resolve the must-have evidence list for router decisions."""
    if query_spec and getattr(query_spec, "hard_requirements", None):
        return list(dict.fromkeys(query_spec.hard_requirements or []))
    # Fallback: required_evidence as hard when normalizer didn't set hard_requirements
    return list(dict.fromkeys(required_evidence or []))


def _can_offer_weak_pass(
    query_spec: QuerySpec | None,
    quality_report: QualityReport | None,
    evidence: list[EvidenceChunk],
    required_evidence: list[str],
) -> bool:
    """Return True when a bounded partial answer is safe enough.

    PASS_WEAK is only available when:
    - we have some evidence,
    - the query is not high risk,
    - clarification is not strictly required,
    - and all declared hard requirements are covered.
    """
    if not quality_report or not evidence:
        return False

    if query_spec and query_spec.is_ambiguous:
        return False

    if query_spec and query_spec.risk_level == "high":
        return False

    if query_spec and not getattr(query_spec, "answerable_without_clarification", True):
        return False

    if query_spec and getattr(query_spec, "answer_mode_hint", "strong") == "ask_user":
        return False

    hard_requirements = _resolve_hard_requirements(query_spec, required_evidence)
    if not hard_requirements:
        return False

    hard_coverage = quality_report.hard_requirement_coverage or {}
    for req in hard_requirements:
        if hard_coverage.get(req) is not True:
            return False

    return True


def route(
    query_spec: QuerySpec | None,
    quality_report: QualityReport | None,
    evidence: list[EvidenceChunk],
    required_evidence: list[str],
    passes_quality_gate: bool,
) -> DecisionResult:
    """Route to PASS | ASK_USER | ESCALATE. Run after Evidence Quality Gate, before LLM.

    Args:
        query_spec: From Normalizer (Phase 2). None = fallback (no normalizer).
        quality_report: From Evidence Quality Gate.
        evidence: Retrieved chunks.
        required_evidence: Evidence types required for this query.
        passes_quality_gate: Whether quality gate passed.

    Returns:
        DecisionResult with decision, reason, and optional pre-generated answer.
    """
    # 1. Ambiguous query → ASK_USER (no LLM)
    if query_spec and query_spec.is_ambiguous:
        answer = _build_ask_user_ambiguous(query_spec)
        return DecisionResult(
            decision="ASK_USER",
            reason="ambiguous_query",
            clarifying_questions=query_spec.clarifying_questions,
            partial_links=[],
            answer=answer,
            answer_policy="clarify",
            lane="ASK_USER",
        )

    # 2. High-risk + insufficient evidence → ESCALATE
    if query_spec and query_spec.risk_level == "high" and not passes_quality_gate:
        return DecisionResult(
            decision="ESCALATE",
            reason="high_risk_insufficient",
            clarifying_questions=[],
            partial_links=[],
            answer=_build_escalate_response(),
            answer_policy="human_handoff",
            lane="ESCALATE",
        )

    # 3. Evidence quality gate failed:
    #    - PASS_WEAK when all hard requirements are still covered
    #    - otherwise ASK_USER (evidence gap)
    if not passes_quality_gate:
        if _can_offer_weak_pass(query_spec, quality_report, evidence, required_evidence):
            return DecisionResult(
                decision="PASS",
                reason="partial_sufficient",
                clarifying_questions=[],
                partial_links=[],
                answer_policy="bounded",
                lane="PASS_WEAK",
            )

        partial_links = _extract_partial_links(evidence)
        answer = _build_ask_user_evidence_gap(
            query_spec or _fallback_query_spec(),
            quality_report or QualityReport(0.0, {}, [], None, None),
            partial_links,
        )
        return DecisionResult(
            decision="ASK_USER",
            reason="missing_evidence_quality",
            clarifying_questions=[],
            partial_links=partial_links,
            answer=answer,
            answer_policy="clarify",
            lane="ASK_USER",
        )

    # 4. Missing constraints (from QuerySpec) – optional, for future
    if query_spec and query_spec.constraints and not query_spec.constraints.get("complete", True):
        return DecisionResult(
            decision="ASK_USER",
            reason="missing_constraints",
            clarifying_questions=query_spec.clarifying_questions,
            partial_links=[],
            answer=_build_ask_user_missing_constraints(query_spec),
            answer_policy="clarify",
            lane="ASK_USER",
        )

    # 5. PASS → proceed to LLM
    return DecisionResult(
        decision="PASS",
        reason="sufficient",
        clarifying_questions=[],
        partial_links=[],
        answer_policy="direct",
        lane="PASS_STRONG",
    )


DECISION_ROUTER_LLM_PROMPT = """Given the context, should we PASS (proceed to generate answer) or ASK_USER (need clarification)?

Output JSON only:
{"decision": "PASS" | "ASK_USER", "reason": "brief reason"}

PASS when:
- Greetings, chitchat, or questions that don't need documentation (hi, hello, hey, hiii, thanks, ok, bye). We can answer without evidence.
- We have enough evidence to give a useful (possibly cautious) answer.
- We have PARTIAL evidence that can partially answer (e.g. some policy language, approximate pricing, related how-to). Prefer PASS with bounded answer over ASK_USER when evidence has relevant content.

ASK_USER when:
- Evidence is truly irrelevant or empty.
- Query needs clarification (ambiguous referent).
- High-risk query (refund dispute, legal) with zero relevant evidence."""


async def route_hybrid(
    query_spec: QuerySpec | None,
    quality_report: QualityReport | None,
    evidence: list[EvidenceChunk],
    required_evidence: list[str],
    passes_quality_gate: bool,
    query: str = "",
) -> DecisionResult:
    """Hybrid: deterministic first; LLM for gray zone when ASK_USER from quality gate fail."""
    dr = route(query_spec, quality_report, evidence, required_evidence, passes_quality_gate)

    # ESCALATE: never override
    if dr.decision == "ESCALATE":
        return dr

    # PASS: no need for LLM
    if dr.decision == "PASS":
        return dr

    # ASK_USER from quality gate fail: gray zone – LLM may suggest PASS with partial evidence
    if dr.decision != "ASK_USER" or not getattr(get_settings(), "decision_router_use_llm", False):
        return dr

    try:
        from app.core.tracing import current_llm_task_var
        from app.services.model_router import get_model_for_task

        current_llm_task_var.set("decision_router")
        llm = get_llm_gateway()
        model = get_model_for_task("decision_router")
        qr = quality_report or QualityReport(0.0, {}, [], None, None)
        user_goal = getattr(query_spec, "user_goal", "") if query_spec else ""
        intent = getattr(query_spec, "intent", "") if query_spec else ""
        user_content = f"""Query: {query}
Intent: {intent}
User goal: {user_goal}
Quality score: {qr.quality_score}
Missing signals: {qr.missing_signals}
Hard requirement coverage: {qr.hard_requirement_coverage or {}}
Evidence chunks: {len(evidence)}
Required evidence: {required_evidence}"""

        resp = await llm.chat(
            messages=[
                {"role": "system", "content": DECISION_ROUTER_LLM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            model=model,
            max_tokens=128,
        )
        content = (resp.content or "").strip()
        if "```json" in content:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
            content = match.group(1) if match else content
        data = json.loads(content)
        llm_decision = str(data.get("decision", "ASK_USER")).upper()
        try:
            from app.core.metrics import decision_router_llm_total, decision_router_llm_override
            decision_router_llm_total.inc()
        except Exception:
            pass
        if llm_decision == "PASS":
            try:
                from app.core.metrics import decision_router_llm_override
                decision_router_llm_override.inc()
            except Exception:
                pass
            logger.info(
                "decision_router_llm",
                decision="PASS",
                reason="gray_zone_override",
                llm_reason=data.get("reason", "")[:100],
            )
            return DecisionResult(
                decision="PASS",
                reason="llm_gray_zone_override",
                clarifying_questions=[],
                partial_links=[],
                answer_policy="bounded",
                lane="PASS_WEAK",
            )
    except Exception as e:
        logger.warning("decision_router_llm_failed", error=str(e))

    logger.debug(
        "decision_router_llm",
        decision="ASK_USER",
        reason="llm_kept_ask_user",
    )
    return dr


def _fallback_query_spec() -> QuerySpec:
    """Minimal QuerySpec when Normalizer not used."""
    return QuerySpec(
        intent="informational",
        entities=[],
        constraints={},
        required_evidence=[],
        risk_level="low",
        keyword_queries=[],
        semantic_queries=[],
        clarifying_questions=[],
        is_ambiguous=False,
    )
