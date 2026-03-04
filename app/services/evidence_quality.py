"""Evidence Quality Gate – Phase 1: Domain-agnostic scoring by features.

Score by evidence features, not domain logic. doc_type only as weak prior.
PASS only when all required features >= per-feature thresholds.

When evidence_quality_use_llm=True, LLM evaluates quality instead of regex.
"""

import json
import re
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger
from app.search.base import EvidenceChunk

from app.services.evidence_hygiene import compute_hygiene

logger = get_logger(__name__)

# Number + unit patterns
NUMBER_UNIT_PATTERN = re.compile(
    r"\$[\d,]+\.?\d*|"
    r"[\d,]+\.?\d*\s*(?:USD|VND|EUR|GBP|/mo|/month|/year|%|MB|GB|TB)\b|"
    r"\b\d+\s*(?:USD|VND|EUR|GBP|%|MB|GB|TB)\b",
    re.I,
)
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.I)
# Order/store paths + product pages that lead to order (billing, vps, dedicated, proxies)
TRANSACTION_PATH_PATTERN = re.compile(
    r"/(?:order|store|checkout|cart|buy|purchase|subscribe|billing)/?|"
    r"/(?:dedicated-servers|proxies|semi-dedicated|vps)/?|"
    r"(?:dedicated-servers|proxies|semi-dedicated|-vps|vps|billing)\.(?:php|html?)|"
    r"order_link|order\s*link",
    re.I,
)

# Policy language – normative pattern groups
POLICY_OBLIGATION = re.compile(
    r"\b(must|shall|required|prohibited|obliged)\b", re.I
)
POLICY_ENTITLEMENT = re.compile(
    r"\b(eligible|refund|within|fee applies|entitled)\b", re.I
)
POLICY_SCOPE = re.compile(
    r"\b(terms|policy|SLA|abuse|cancellation)\b", re.I
)

# Steps structure
STEPS_PATTERN = re.compile(
    r"\b\d+[.)]\s|\b(?:step\s+\d+|first|second|third)\b|\n\s*[-*•]\s",
    re.I,
)

# Boilerplate
BOILERPLATE_PATTERNS = [
    r"\bcontact\s+(?:us|support)\b",
    r"\bcopyright\s+©?\s*\d{4}",
    r"\b(?:privacy|terms)\s+(?:of\s+)?(?:service|policy)\b",
    r"\bmenu\b",
    r"\ball\s+rights\s+reserved\b",
]
BOILERPLATE_RE = re.compile("|".join(BOILERPLATE_PATTERNS), re.I)

# Trust tier: official > user-generated (weak prior)
TRUST_OFFICIAL = {"policy", "tos", "pricing", "docs", "faq"}
TRUST_USER = {"ticket", "forum", "user_generated"}


@dataclass
class QualityReport:
    """Explainable quality report."""

    quality_score: float  # 0–1 aggregate
    feature_scores: dict[str, float]
    missing_signals: list[str]
    staleness_risk: float | None
    boilerplate_risk: float | None
    sufficiency_scores: dict[str, float] | None = None
    hard_requirement_coverage: dict[str, bool] | None = None
    gate_pass: bool | None = None  # LLM v2: direct pass/fail; when set, passes_quality_gate uses it


# required_evidence → feature mapping
REQUIRED_TO_FEATURE = {
    "numbers": "numbers_units",
    "numbers_units": "numbers_units",
    "links": "has_any_url",
    "has_any_url": "has_any_url",
    "transaction_link": "has_transaction_link",
    "has_transaction_link": "has_transaction_link",
    "policy_clause": "policy_language",
    "policy_language": "policy_language",
    "steps": "steps_structure",
    "steps_structure": "steps_structure",
    "citations": "has_any_url",  # links suffice for citations
}

# feature → missing_signal
FEATURE_TO_MISSING = {
    "numbers_units": "missing_numbers",
    "has_any_url": "missing_links",
    "has_transaction_link": "missing_transaction_link",
    "policy_language": "missing_policy",
    "steps_structure": "missing_steps",
    "content_density": "boilerplate_risk",
    "boilerplate_ratio": "boilerplate_risk",
}


def _score_numbers_units(chunks: list[EvidenceChunk]) -> float:
    n = len(chunks)
    if n == 0:
        return 0.0
    count = sum(
        1
        for c in chunks
        if NUMBER_UNIT_PATTERN.search((c.full_text or c.snippet) or "")
    )
    return count / n


def _score_has_any_url(chunks: list[EvidenceChunk]) -> float:
    n = len(chunks)
    if n == 0:
        return 0.0
    count = sum(
        1
        for c in chunks
        if URL_PATTERN.search((c.full_text or c.snippet) or "") or URL_PATTERN.search(c.source_url or "")
    )
    return count / n


def _score_has_transaction_link(chunks: list[EvidenceChunk]) -> float:
    n = len(chunks)
    if n == 0:
        return 0.0
    count = 0
    for c in chunks:
        text = (c.full_text or c.snippet) or ""
        combined = f"{text} {c.source_url or ''}"
        if TRANSACTION_PATH_PATTERN.search(combined):
            count += 1
    return count / n


def _score_policy_language(chunks: list[EvidenceChunk]) -> float:
    """Score based on normative patterns (obligation, entitlement, scope)."""
    n = len(chunks)
    if n == 0:
        return 0.0
    scores = []
    for c in chunks:
        text = (c.full_text or c.snippet) or ""
        groups_matched = 0
        if POLICY_OBLIGATION.search(text):
            groups_matched += 1
        if POLICY_ENTITLEMENT.search(text):
            groups_matched += 1
        if POLICY_SCOPE.search(text):
            groups_matched += 1
        # 2+ groups → high confidence
        scores.append(1.0 if groups_matched >= 2 else (0.5 if groups_matched >= 1 else 0.0))
    return sum(scores) / n


def _score_steps_structure(chunks: list[EvidenceChunk]) -> float:
    n = len(chunks)
    if n == 0:
        return 0.0
    count = sum(
        1
        for c in chunks
        if STEPS_PATTERN.search((c.full_text or c.snippet) or "")
    )
    return count / n


def _score_content_density(chunks: list[EvidenceChunk]) -> float:
    sigs = compute_hygiene(chunks)
    return sigs.median_content_density


def _score_boilerplate_ratio(chunks: list[EvidenceChunk]) -> float:
    """Lower boilerplate = better. Return 1 - risk."""
    sigs = compute_hygiene(chunks)
    pct_bad = sigs.pct_chunks_boilerplate_gt_06 / 100.0
    return 1.0 - min(1.0, pct_bad)


def _score_freshness(chunks: list[EvidenceChunk]) -> float | None:
    """effective_date decay if metadata available. None = neutral."""
    # EvidenceChunk doesn't have effective_date; would need metadata
    return None


def _score_trust_tier(chunks: list[EvidenceChunk]) -> float:
    """doc_type weak prior: official > user-generated."""
    n = len(chunks)
    if n == 0:
        return 0.5
    official = sum(1 for c in chunks if (c.doc_type or "").lower() in TRUST_OFFICIAL)
    user = sum(1 for c in chunks if (c.doc_type or "").lower() in TRUST_USER)
    # 0.5 base, +0.25 if more official, -0.25 if more user
    base = 0.5
    if official > user:
        base += 0.25 * min(1.0, official / n)
    elif user > official:
        base -= 0.25 * min(1.0, user / n)
    return max(0.0, min(1.0, base))


def _derive_missing_signals(
    feature_scores: dict[str, float],
    required_evidence: list[str],
    thresholds: dict[str, float],
) -> list[str]:
    """Derive missing_signals from feature_scores and required_evidence."""
    missing: list[str] = []
    required_features = set()
    for req in required_evidence:
        feat = REQUIRED_TO_FEATURE.get(req, req)
        required_features.add(feat)

    for feat, score in feature_scores.items():
        thresh = thresholds.get(feat, 0.3)
        if feat in required_features and score < thresh:
            sig = FEATURE_TO_MISSING.get(feat, f"missing_{feat}")
            if sig not in missing:
                missing.append(sig)
        if feat == "boilerplate_ratio" and score < 0.4:
            if "boilerplate_risk" not in missing:
                missing.append("boilerplate_risk")

    return missing


def _compute_sufficiency_scores(chunks: list[EvidenceChunk]) -> dict[str, float]:
    """Compute max-hit sufficiency scores for hard requirements.

    These scores answer "do we have enough signal somewhere?" rather than
    "what fraction of all chunks contain this signal?".
    """
    if not chunks:
        return {
            "numbers_units": 0.0,
            "has_any_url": 0.0,
            "has_transaction_link": 0.0,
            "policy_language": 0.0,
            "steps_structure": 0.0,
        }

    return {
        "numbers_units": 1.0 if any(NUMBER_UNIT_PATTERN.search((c.full_text or c.snippet) or "") for c in chunks) else 0.0,
        "has_any_url": 1.0 if any(
            URL_PATTERN.search((c.full_text or c.snippet) or "") or URL_PATTERN.search(c.source_url or "")
            for c in chunks
        ) else 0.0,
        "has_transaction_link": 1.0 if any(
            TRANSACTION_PATH_PATTERN.search(f"{(c.full_text or c.snippet) or ''} {c.source_url or ''}")
            for c in chunks
        ) else 0.0,
        "policy_language": max(
            (
                (1.0 if sum(
                    (
                        1 if POLICY_OBLIGATION.search((c.full_text or c.snippet) or "") else 0,
                        1 if POLICY_ENTITLEMENT.search((c.full_text or c.snippet) or "") else 0,
                        1 if POLICY_SCOPE.search((c.full_text or c.snippet) or "") else 0,
                    )
                ) >= 2 else (
                    0.5 if (
                        POLICY_OBLIGATION.search((c.full_text or c.snippet) or "")
                        or POLICY_ENTITLEMENT.search((c.full_text or c.snippet) or "")
                        or POLICY_SCOPE.search((c.full_text or c.snippet) or "")
                    ) else 0.0
                ))
                for c in chunks
            ),
            default=0.0,
        ),
        "steps_structure": 1.0 if any(STEPS_PATTERN.search((c.full_text or c.snippet) or "") for c in chunks) else 0.0,
    }


def _passes_hard_requirement(req: str, sufficiency_scores: dict[str, float]) -> bool:
    """Check whether a hard requirement is sufficiently represented."""
    feat = REQUIRED_TO_FEATURE.get(req, req)
    score = sufficiency_scores.get(feat, 0.0)
    if feat == "policy_language":
        return score >= 0.5
    return score > 0.0


def _derive_hard_requirement_coverage(
    hard_requirements: list[str],
    sufficiency_scores: dict[str, float],
) -> dict[str, bool]:
    """Map hard requirements to explicit covered / uncovered flags."""
    coverage: dict[str, bool] = {}
    for req in hard_requirements:
        coverage[req] = _passes_hard_requirement(req, sufficiency_scores)
    return coverage


def evaluate_quality(
    chunks: list[EvidenceChunk],
    required_evidence: list[str] | None = None,
    hard_requirements: list[str] | None = None,
) -> QualityReport:
    """Evaluate evidence quality. Domain-agnostic, feature-based."""
    settings = get_settings()
    thresholds = getattr(settings, "evidence_feature_thresholds", None) or {
        "numbers_units": 0.3,
        "has_any_url": 0.2,
        "has_transaction_link": 0.2,
        "policy_language": 0.3,
        "steps_structure": 0.2,
        "content_density": 0.3,
        "boilerplate_ratio": 0.4,
    }

    hard_reqs = list(dict.fromkeys(hard_requirements or []))

    if not chunks:
        sufficiency_scores = _compute_sufficiency_scores([])
        hard_coverage = _derive_hard_requirement_coverage(hard_reqs, sufficiency_scores)
        return QualityReport(
            quality_score=0.0,
            feature_scores={},
            missing_signals=["missing_evidence"] if (required_evidence or hard_reqs) else [],
            staleness_risk=None,
            boilerplate_risk=1.0,
            sufficiency_scores=sufficiency_scores,
            hard_requirement_coverage=hard_coverage,
        )

    feature_scores = {
        "numbers_units": _score_numbers_units(chunks),
        "has_any_url": _score_has_any_url(chunks),
        "has_transaction_link": _score_has_transaction_link(chunks),
        "policy_language": _score_policy_language(chunks),
        "steps_structure": _score_steps_structure(chunks),
        "content_density": _score_content_density(chunks),
        "boilerplate_ratio": _score_boilerplate_ratio(chunks),
        "trust_tier": _score_trust_tier(chunks),
    }
    freshness = _score_freshness(chunks)
    if freshness is not None:
        feature_scores["freshness"] = freshness

    aggregate = sum(feature_scores.values()) / len(feature_scores)
    sufficiency_scores = _compute_sufficiency_scores(chunks)
    hard_coverage = _derive_hard_requirement_coverage(hard_reqs, sufficiency_scores)
    missing_signals = _derive_missing_signals(
        feature_scores,
        required_evidence or [],
        thresholds,
    )
    for req, covered in hard_coverage.items():
        if not covered:
            feat = REQUIRED_TO_FEATURE.get(req, req)
            sig = FEATURE_TO_MISSING.get(feat, f"missing_{feat}")
            if sig not in missing_signals:
                missing_signals.append(sig)

    sigs = compute_hygiene(chunks)
    boilerplate_risk = sigs.pct_chunks_boilerplate_gt_06 / 100.0

    return QualityReport(
        quality_score=round(aggregate, 3),
        feature_scores={k: round(v, 3) for k, v in feature_scores.items()},
        missing_signals=missing_signals,
        staleness_risk=None,  # would need metadata
        boilerplate_risk=round(boilerplate_risk, 3),
        sufficiency_scores={k: round(v, 3) for k, v in sufficiency_scores.items()},
        hard_requirement_coverage=hard_coverage,
    )


EVIDENCE_QUALITY_LLM_PROMPT = """You evaluate whether retrieved evidence is sufficient to answer the user's query. Be flexible and query-aware.

Output JSON only, no markdown:
{
  "pass": true | false,
  "numbers_units": 0.0-1.0,
  "has_any_url": 0.0-1.0,
  "has_transaction_link": 0.0-1.0,
  "policy_language": 0.0-1.0,
  "steps_structure": 0.0-1.0,
  "content_density": 0.0-1.0,
  "boilerplate_ratio": 0.0-1.0,
  "quality_score": 0.0-1.0,
  "missing_signals": []
}

pass: YOUR final decision. true = evidence suffices to answer; false = insufficient. Be generous: if evidence has relevant product/pricing links (vps, windows-vps, budget, order pages), pass=true even without exact $ numbers. Only pass=false when evidence is clearly irrelevant or empty.

Query-aware scoring:
- For "do you have X?" / product availability: evidence that confirms the product exists (e.g. dedicated-servers page for "dedicated server") is sufficient. quality_score 0.7+ if evidence directly answers.
- For price/cost questions: need numbers_units. quality_score low if missing.
- For policy/refund/terms: need policy_language.
- For how-to/step questions: need steps_structure.
- has_any_url: 1.0 if evidence has URLs; 0.0 otherwise
- has_transaction_link: 1.0 if evidence has product/order/store/checkout links (dedicated-servers, vps, proxies, billing, etc.); 0.0 otherwise
- content_density: 1.0 if substantive; 0.0 if mostly boilerplate
- boilerplate_ratio: 0.0 = no boilerplate, 1.0 = all boilerplate
- quality_score: 0-1. Be generous when evidence clearly answers the query. Strict when query needs specific data (price, policy) and evidence lacks it.
- missing_signals: only list critical gaps (e.g. "missing_numbers" for price questions). Empty if evidence suffices."""


async def evaluate_quality_llm(
    query: str,
    chunks: list[EvidenceChunk],
    required_evidence: list[str] | None = None,
    hard_requirements: list[str] | None = None,
) -> QualityReport:
    """LLM-based evidence quality evaluation. Falls back to regex on error."""
    hard_reqs = list(dict.fromkeys(hard_requirements or []))
    if not chunks:
        sufficiency_scores = _compute_sufficiency_scores([])
        hard_coverage = _derive_hard_requirement_coverage(hard_reqs, sufficiency_scores)
        return QualityReport(
            quality_score=0.0,
            feature_scores={},
            missing_signals=["missing_evidence"] if (required_evidence or hard_reqs) else [],
            staleness_risk=None,
            boilerplate_risk=1.0,
            sufficiency_scores=sufficiency_scores,
            hard_requirement_coverage=hard_coverage,
        )

    summaries = []
    for i, c in enumerate(chunks[:12], 1):
        text = (c.full_text or c.snippet or "")[:300]
        summaries.append(f"[{i}] {c.source_url or '?'}: {text}...")

    user_content = f"Query: {query[:400]}\n\nEvidence:\n" + "\n".join(summaries)
    if required_evidence or hard_reqs:
        user_content += f"\n\nRequired/hard: {required_evidence or []} {hard_reqs}"

    try:
        from app.core.tracing import current_llm_task_var
        from app.services.llm_gateway import get_llm_gateway
        from app.services.model_router import get_model_for_task

        current_llm_task_var.set("evidence_quality")
        llm = get_llm_gateway()
        model = get_model_for_task("evidence_quality")
        resp = await llm.chat(
            messages=[
                {"role": "system", "content": EVIDENCE_QUALITY_LLM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            model=model,
            max_tokens=256,
        )
        text = (resp.content or "").strip()
        if "```json" in text:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
            text = match.group(1) if match else text
        elif "```" in text:
            match = re.search(r"```\s*([\s\S]*?)\s*```", text)
            text = match.group(1) if match else text

        data = json.loads(text)
        gate_pass = bool(data["pass"]) if data.get("pass") is not None else None
        feature_scores = {
            "numbers_units": float(data.get("numbers_units", 0)),
            "has_any_url": float(data.get("has_any_url", 0)),
            "has_transaction_link": float(data.get("has_transaction_link", 0)),
            "policy_language": float(data.get("policy_language", 0)),
            "steps_structure": float(data.get("steps_structure", 0)),
            "content_density": float(data.get("content_density", 0.5)),
            "boilerplate_ratio": float(data.get("boilerplate_ratio", 0.5)),
        }
        quality_score = float(data.get("quality_score", 0.5))
        missing_signals = [str(x) for x in (data.get("missing_signals") or [])]

        sufficiency_scores = {
            k: v for k, v in feature_scores.items()
            if k in ("numbers_units", "has_any_url", "has_transaction_link", "policy_language", "steps_structure")
        }
        hard_coverage = _derive_hard_requirement_coverage(hard_reqs, sufficiency_scores)
        for req, covered in hard_coverage.items():
            if not covered:
                feat = REQUIRED_TO_FEATURE.get(req, req)
                sig = FEATURE_TO_MISSING.get(feat, f"missing_{feat}")
                if sig not in missing_signals:
                    missing_signals.append(sig)

        sigs = compute_hygiene(chunks)
        boilerplate_risk = sigs.pct_chunks_boilerplate_gt_06 / 100.0

        return QualityReport(
            quality_score=round(quality_score, 3),
            feature_scores={k: round(v, 3) for k, v in feature_scores.items()},
            missing_signals=missing_signals,
            staleness_risk=None,
            boilerplate_risk=round(boilerplate_risk, 3),
            sufficiency_scores={k: round(v, 3) for k, v in sufficiency_scores.items()},
            hard_requirement_coverage=hard_coverage,
            gate_pass=gate_pass,
        )
    except Exception as e:
        logger.warning("evidence_quality_llm_failed", error=str(e), query=query[:50])
        return evaluate_quality(chunks, required_evidence, hard_requirements=hard_reqs)


EVIDENCE_QUALITY_LLM_V2_PROMPT = """You evaluate whether retrieved evidence is sufficient to answer the user's query.

Output JSON only, no markdown:
{
  "pass": true | false,
  "confidence": 0.0-1.0,
  "reason": "one sentence",
  "missing_signals": []
}

Rules (apply consistently across all query types: policy, pricing, troubleshooting, account, informational):
- pass=true when evidence clearly answers the query OR contains partial but usable information.
- pass=false ONLY when evidence is irrelevant, empty, or completely lacks the requested type of information.
- Be generous: partial evidence that can partially answer = pass=true with lower confidence (0.4-0.7).
- For policy queries (refund, terms, cancellation): product-specific policy (e.g. "no refund for proxies", "promo not refundable") = policy_language present. pass=true.
- For pricing: approximate prices or links to pricing pages = pass=true. Exact numbers not required.
- For how-to/troubleshooting: partial steps or related docs = pass=true. Full step-by-step not required.
- missing_signals: only when pass=false. Use: missing_numbers, missing_transaction_link, missing_policy, missing_steps, missing_links. Empty if pass=true."""


async def evaluate_quality_llm_v2(
    query: str,
    chunks: list[EvidenceChunk],
    required_evidence: list[str] | None = None,
    hard_requirements: list[str] | None = None,
) -> QualityReport:
    """LLM v2: single pass/fail decision. Simpler, query-aware, no feature-score coupling."""
    hard_reqs = list(dict.fromkeys(hard_requirements or []))
    if not chunks:
        sufficiency_scores = _compute_sufficiency_scores([])
        hard_coverage = _derive_hard_requirement_coverage(hard_reqs, sufficiency_scores)
        return QualityReport(
            quality_score=0.0,
            feature_scores={},
            missing_signals=["missing_evidence"] if (required_evidence or hard_reqs) else [],
            staleness_risk=None,
            boilerplate_risk=1.0,
            sufficiency_scores=sufficiency_scores,
            hard_requirement_coverage=hard_coverage,
            gate_pass=False,
        )

    summaries = []
    for i, c in enumerate(chunks[:12], 1):
        text = (c.full_text or c.snippet or "")[:300]
        summaries.append(f"[{i}] {c.source_url or '?'}: {text}...")

    user_content = f"Query: {query[:400]}\n\nEvidence:\n" + "\n".join(summaries)
    if required_evidence or hard_reqs:
        user_content += f"\n\nHint (query context): {required_evidence or []} {hard_reqs}"

    try:
        from app.core.tracing import current_llm_task_var
        from app.services.llm_gateway import get_llm_gateway
        from app.services.model_router import get_model_for_task

        current_llm_task_var.set("evidence_quality_v2")
        llm = get_llm_gateway()
        model = get_model_for_task("evidence_quality")
        resp = await llm.chat(
            messages=[
                {"role": "system", "content": EVIDENCE_QUALITY_LLM_V2_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            model=model,
            max_tokens=256,
        )
        text = (resp.content or "").strip()
        if "```json" in text:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
            text = match.group(1) if match else text
        elif "```" in text:
            match = re.search(r"```\s*([\s\S]*?)\s*```", text)
            text = match.group(1) if match else text

        data = json.loads(text)
        gate_pass = bool(data.get("pass", False))
        confidence = float(data.get("confidence", 0.5))
        missing_signals = [str(x) for x in (data.get("missing_signals") or [])]

        sigs = compute_hygiene(chunks)
        boilerplate_risk = sigs.pct_chunks_boilerplate_gt_06 / 100.0

        # Always compute sufficiency for decision router (PASS_WEAK path when gate_pass=False)
        sufficiency_scores = _compute_sufficiency_scores(chunks)
        hard_coverage = _derive_hard_requirement_coverage(hard_reqs, sufficiency_scores)

        return QualityReport(
            quality_score=round(confidence, 3),
            feature_scores={},
            missing_signals=missing_signals,
            staleness_risk=None,
            boilerplate_risk=round(boilerplate_risk, 3),
            sufficiency_scores={k: round(v, 3) for k, v in sufficiency_scores.items()},
            hard_requirement_coverage=hard_coverage,
            gate_pass=gate_pass,
        )
    except Exception as e:
        logger.warning("evidence_quality_llm_v2_failed", error=str(e), query=query[:50])
        return evaluate_quality(chunks, required_evidence, hard_requirements=hard_reqs)


def infer_required_evidence(query: str) -> list[str]:
    """Rule-based inference of required_evidence from query (transactional vs policy)."""
    q = query.lower().strip()
    required: list[str] = []
    if any(kw in q for kw in ["price", "cost", "pricing", "giá", "bao nhiêu"]):
        required.extend(["numbers_units", "transaction_link"])
    if any(kw in q for kw in ["link", "order", "mua", "buy", "subscribe"]):
        required.append("transaction_link")
    if any(kw in q for kw in ["refund", "policy", "terms", "hoàn tiền", "chính sách"]):
        required.append("policy_language")
    if any(kw in q for kw in ["how", "step", "cách", "hướng dẫn"]):
        required.append("steps_structure")
    # Comparison queries (diff, difference, compare): need specs + links
    if any(kw in q for kw in ["diff", "difference", "compare", "khác", "so sánh"]):
        required.extend(["numbers_units", "has_any_url"])
    return list(dict.fromkeys(required))


def passes_quality_gate(
    report: QualityReport,
    required_evidence: list[str] | None,
    thresholds: dict[str, float] | None = None,
    hard_requirements: list[str] | None = None,
) -> bool:
    """PASS when hard requirements are sufficiently covered and soft ones meet thresholds.
    When report.gate_pass is set (LLM v1 or v2), use it directly and skip rule logic."""
    settings = get_settings()
    if not getattr(settings, "evidence_quality_enabled", True):
        return True

    if report.gate_pass is not None:
        return report.gate_pass

    thresh = thresholds or getattr(settings, "evidence_feature_thresholds", None) or {
        "numbers_units": 0.3,
        "has_any_url": 0.2,
        "has_transaction_link": 0.2,
        "policy_language": 0.3,
        "steps_structure": 0.2,
    }

    hard_reqs = list(dict.fromkeys(hard_requirements or []))
    hard_req_set = set(hard_reqs)
    hard_coverage = report.hard_requirement_coverage or {}
    sufficiency_scores = report.sufficiency_scores or {}

    if not required_evidence and not hard_reqs:
        # No required evidence → optional aggregate check
        agg_thresh = getattr(settings, "evidence_quality_threshold", 0.6)
        return report.quality_score >= agg_thresh

    for req in hard_reqs:
        covered = hard_coverage.get(req)
        if covered is None:
            covered = _passes_hard_requirement(req, sufficiency_scores)
        if not covered:
            return False

    soft_requirements = [
        req for req in (required_evidence or [])
        if req not in hard_req_set
    ]

    for req in soft_requirements:
        feat = REQUIRED_TO_FEATURE.get(req, req)
        score = report.feature_scores.get(feat, 0.0)
        min_score = thresh.get(feat, 0.3)
        if score < min_score:
            return False
    return True
