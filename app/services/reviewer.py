"""Reviewer gate: rule-based quality checks before returning answers."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.logging import get_logger
from app.search.base import EvidenceChunk

logger = get_logger(__name__)


class ReviewerStatus(str, Enum):
    PASS = "PASS"
    ASK_USER = "ASK_USER"
    RETRIEVE_MORE = "RETRIEVE_MORE"
    ESCALATE = "ESCALATE"


@dataclass
class ReviewerResult:
    """Result of reviewer gate."""

    status: ReviewerStatus
    reasons: list[str]
    suggested_queries: list[str]
    missing_fields: list[str]


# High-risk query patterns
HIGH_RISK_PATTERNS = [
    r"\b(refund|reimburse|money back)\b",
    r"\b(billing|invoice|payment dispute)\b",
    r"\b(legal|lawsuit|attorney)\b",
    r"\b(abuse|fraud|violation)\b",
    r"\b(cancel.*subscription|terminate)\b",
]

# Policy doc types required for high-risk
REQUIRED_POLICY_DOC_TYPES = {"policy", "tos"}


def _is_high_risk_query(query: str) -> bool:
    """Check if query matches high-risk patterns."""
    q = query.lower()
    return any(re.search(p, q, re.I) for p in HIGH_RISK_PATTERNS)


def _has_policy_citation(citations: list[dict], evidence: list[EvidenceChunk]) -> bool:
    """Check if any citation references policy/tos doc_type."""
    cited_ids = {c.get("chunk_id") for c in citations}
    for e in evidence:
        if e.chunk_id in cited_ids and e.doc_type in REQUIRED_POLICY_DOC_TYPES:
            return True
    return False


def _citation_coverage(answer: str, citations: list[dict]) -> float:
    """Estimate how much of answer is cited (rough heuristic)."""
    if not citations:
        return 0.0
    # Count sentences in answer
    sentences = re.split(r"[.!?]+", answer)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 1.0
    # Assume each citation covers at least one claim
    return min(1.0, len(citations) / max(1, len(sentences)))


def _has_uncited_numbers(answer: str) -> bool:
    """Check for numbers/prices that might need citation."""
    # Look for price-like patterns: $X, X%, dates, etc.
    price_pattern = r"\$[\d,]+\.?\d*|[\d]+%|\d{1,2}/\d{1,2}/\d{2,4}"
    matches = re.findall(price_pattern, answer)
    return len(matches) > 0


def _has_uncited_policy_claims(answer: str) -> bool:
    """Heuristic: policy-like phrases that should be cited."""
    policy_phrases = [
        r"according to (?:our |the )?policy",
        r"(?:we |the company )?(?:shall|must|may not)",
        r"within \d+ (?:days|hours)",
        r"(?:eligible|entitled) (?:for|to)",
    ]
    for p in policy_phrases:
        if re.search(p, answer, re.I):
            return True
    return False


class ReviewerGate:
    """Rule-based reviewer gate."""

    def __init__(
        self,
        require_citations_on_pass: bool = True,
        require_policy_for_high_risk: bool = True,
        min_citation_coverage: float = 0.3,
    ) -> None:
        self.require_citations_on_pass = require_citations_on_pass
        self.require_policy_for_high_risk = require_policy_for_high_risk
        self.min_citation_coverage = min_citation_coverage

    def review(
        self,
        decision: str,
        answer: str,
        citations: list[dict[str, Any]],
        evidence: list[EvidenceChunk],
        query: str,
        confidence: float,
        retrieval_attempt: int = 1,
        max_attempts: int = 2,
    ) -> ReviewerResult:
        """Run reviewer checks. Returns status and reasons."""
        reasons: list[str] = []
        suggested_queries: list[str] = []
        missing_fields: list[str] = []

        # 1. PASS decision checks
        if decision == "PASS":
            if self.require_citations_on_pass and not citations:
                reasons.append("PASS requires at least one citation")
                return ReviewerResult(
                    status=ReviewerStatus.ASK_USER,
                    reasons=reasons,
                    suggested_queries=[],
                    missing_fields=["citations"],
                )

            # Citations must correspond to evidence
            evidence_ids = {e.chunk_id for e in evidence}
            for c in citations:
                cid = c.get("chunk_id")
                if cid and cid not in evidence_ids:
                    reasons.append(f"Citation chunk_id {cid} not in evidence")
                    return ReviewerResult(
                        status=ReviewerStatus.ASK_USER,
                        reasons=reasons,
                        suggested_queries=[],
                        missing_fields=[],
                    )

            # Numbers/prices without citation
            if _has_uncited_numbers(answer) and len(citations) < 2:
                reasons.append("Answer contains numbers/prices but insufficient citations")
                return ReviewerResult(
                    status=ReviewerStatus.RETRIEVE_MORE,
                    reasons=reasons,
                    suggested_queries=[query, f"{query} pricing"],
                    missing_fields=[],
                )

            # Policy claims without citation
            if _has_uncited_policy_claims(answer) and len(citations) < 2:
                reasons.append("Answer contains policy-like claims but insufficient citations")
                return ReviewerResult(
                    status=ReviewerStatus.RETRIEVE_MORE,
                    reasons=reasons,
                    suggested_queries=[query, f"{query} policy"],
                    missing_fields=[],
                )

            # High-risk query: require policy citation
            if self.require_policy_for_high_risk and _is_high_risk_query(query):
                if not _has_policy_citation(citations, evidence):
                    reasons.append("High-risk query requires policy/tos citation")
                    return ReviewerResult(
                        status=ReviewerStatus.ESCALATE,
                        reasons=reasons,
                        suggested_queries=[],
                        missing_fields=[],
                    )

            # Citation coverage
            cov = _citation_coverage(answer, citations)
            if cov < self.min_citation_coverage and len(citations) < 2:
                reasons.append(f"Low citation coverage ({cov:.2f})")
                return ReviewerResult(
                    status=ReviewerStatus.RETRIEVE_MORE,
                    reasons=reasons,
                    suggested_queries=[query],
                    missing_fields=[],
                )

            return ReviewerResult(
                status=ReviewerStatus.PASS,
                reasons=[],
                suggested_queries=[],
                missing_fields=[],
            )

        # 2. ASK_USER - no additional checks
        if decision == "ASK_USER":
            return ReviewerResult(
                status=ReviewerStatus.ASK_USER,
                reasons=reasons,
                suggested_queries=[],
                missing_fields=missing_fields,
            )

        # 3. ESCALATE
        if decision == "ESCALATE":
            return ReviewerResult(
                status=ReviewerStatus.ESCALATE,
                reasons=reasons,
                suggested_queries=[],
                missing_fields=[],
            )

        # 4. RETRIEVE_MORE - check attempt limit
        if retrieval_attempt >= max_attempts:
            reasons.append(f"Max retrieval attempts ({max_attempts}) reached")
            return ReviewerResult(
                status=ReviewerStatus.ASK_USER,
                reasons=reasons,
                suggested_queries=[],
                missing_fields=["clarification"],
            )

        return ReviewerResult(
            status=ReviewerStatus.RETRIEVE_MORE,
            reasons=reasons,
            suggested_queries=[query],
            missing_fields=[],
        )
