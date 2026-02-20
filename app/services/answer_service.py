"""Answer generation with grounding and reviewer gate."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.search.base import EvidenceChunk
from app.services.llm_gateway import LLMGateway, get_llm_gateway
from app.services.orchestrator import Orchestrator
from app.services.retrieval import EvidencePack, RetrievalService
from app.services.reviewer import ReviewerGate, ReviewerResult, ReviewerStatus

logger = get_logger(__name__)


@dataclass
class AnswerOutput:
    """Structured answer output."""

    decision: str  # PASS | ASK_USER | ESCALATE
    answer: str
    followup_questions: list[str]
    citations: list[dict[str, str]]
    confidence: float
    debug: dict[str, Any] = field(default_factory=dict)


SYSTEM_PROMPT = """You are a support assistant for a single company. You must ONLY use the provided evidence to answer. Never guess or make up information.

RULES:
1. Use ONLY the provided evidence chunks. Do not add information from your training.
2. When the user asks about plans, products, or pricing: LIST specific options with names, specs, and prices when available in the evidence. Do not give a generic answer.
3. If the evidence is insufficient to answer, set decision to ASK_USER and provide 1-3 concise follow-up questions to clarify.
4. For high-risk topics (refunds, billing disputes, legal, abuse), if you cannot find clear policy evidence, set decision to ESCALATE.
5. Always cite your sources. For each key claim, include a citation with chunk_id and source_url.
6. If you cite a chunk, it MUST be in the evidence list.
7. Respond with valid JSON matching the output schema.

OUTPUT SCHEMA (JSON):
{
  "decision": "PASS" | "ASK_USER" | "ESCALATE",
  "answer": "your grounded answer",
  "followup_questions": ["question1", "question2"],
  "citations": [{"chunk_id": "...", "source_url": "...", "doc_type": "..."}],
  "confidence": 0.0 to 1.0
}

Evidence chunks will be provided in the user message."""


def _format_evidence_for_prompt(evidence: list[EvidenceChunk], max_chars_per_chunk: int = 1200) -> str:
    """Format evidence for LLM prompt. Truncates each chunk to stay within context limits."""
    parts = []
    for i, e in enumerate(evidence, 1):
        text = (e.full_text or e.snippet) or ""
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk] + "..."
        parts.append(
            f"[Chunk {e.chunk_id}]\n"
            f"Source: {e.source_url}\n"
            f"Type: {e.doc_type}\n"
            f"Content: {text}\n"
        )
    return "\n---\n".join(parts)


def _parse_llm_response(content: str) -> dict[str, Any]:
    """Parse LLM JSON response, with fallback."""
    # Try to extract JSON from response
    content = content.strip()
    # Handle markdown code blocks
    if "```json" in content:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
        if match:
            content = match.group(1)
    elif "```" in content:
        match = re.search(r"```\s*([\s\S]*?)\s*```", content)
        if match:
            content = match.group(1)

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning("llm_json_parse_failed", error=str(e), content_preview=content[:200])
        return {
            "decision": "ASK_USER",
            "answer": content[:500] if content else "I couldn't format my response properly. Could you rephrase your question?",
            "followup_questions": ["Could you provide more details about your question?"],
            "citations": [],
            "confidence": 0.0,
        }


class AnswerService:
    """Orchestrates retrieval, LLM generation, and reviewer gate."""

    def __init__(
        self,
        retrieval: RetrievalService | None = None,
        llm: LLMGateway | None = None,
        reviewer: ReviewerGate | None = None,
        orchestrator: Orchestrator | None = None,
    ) -> None:
        self._settings = get_settings()
        self._retrieval = retrieval or RetrievalService()
        self._llm = llm or get_llm_gateway()
        self._reviewer = reviewer or ReviewerGate()
        self._orchestrator = orchestrator or Orchestrator(
            primary_model=self._settings.llm_model,
            fallback_model=self._settings.llm_fallback_model,
        )

    async def generate(
        self,
        query: str,
        conversation_history: list[dict[str, str]] | None = None,
        trace_id: str | None = None,
    ) -> AnswerOutput:
        """Generate grounded answer with retrieval and reviewer gate."""
        max_attempts = self._settings.max_retrieval_attempts
        attempt = 1
        evidence_pack: EvidencePack | None = None
        last_reviewer_result: ReviewerResult | None = None

        while attempt <= max_attempts:
            # Retrieve
            evidence_pack = await self._retrieval.retrieve(query)
            evidence = evidence_pack.chunks

            if not evidence:
                return AnswerOutput(
                    decision="ASK_USER",
                    answer="I couldn't find relevant information in our knowledge base. Could you rephrase your question or provide more context?",
                    followup_questions=["What specific topic are you asking about?"],
                    citations=[],
                    confidence=0.0,
                    debug={
                        "trace_id": trace_id,
                        "retrieval_stats": evidence_pack.retrieval_stats,
                        "attempt": attempt,
                    },
                )

            # Build messages
            max_chars = self._settings.llm_max_evidence_chars
            user_content = f"User question: {query}\n\nEvidence:\n{_format_evidence_for_prompt(evidence, max_chars)}"
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if conversation_history:
                for m in conversation_history[-4:]:  # Last 4 messages (fit 16k context)
                    messages.append({"role": m["role"], "content": m["content"]})
            messages.append({"role": "user", "content": user_content})

            # LLM call (model routing via orchestrator)
            model = self._orchestrator.get_model_for_query(query)
            try:
                llm_resp = await self._llm.chat(
                    messages=messages,
                    temperature=self._settings.llm_temperature,
                    model=model,
                )
            except Exception as e:
                logger.error("answer_llm_failed", error=str(e))
                return AnswerOutput(
                    decision="ESCALATE",
                    answer="I'm sorry, I encountered an error. Please try again or contact support.",
                    followup_questions=[],
                    citations=[],
                    confidence=0.0,
                    debug={"trace_id": trace_id, "error": str(e)},
                )

            parsed = _parse_llm_response(llm_resp.content)
            decision = parsed.get("decision", "ASK_USER")
            answer = parsed.get("answer", "")
            followup = parsed.get("followup_questions", [])
            citations = parsed.get("citations", [])
            confidence = float(parsed.get("confidence", 0.0))

            # Reviewer gate
            last_reviewer_result = self._reviewer.review(
                decision=decision,
                answer=answer,
                citations=citations,
                evidence=evidence,
                query=query,
                confidence=confidence,
                retrieval_attempt=attempt,
                max_attempts=max_attempts,
            )

            if last_reviewer_result.status == ReviewerStatus.PASS:
                try:
                    from app.core.metrics import decision_total
                    decision_total.labels(decision="PASS").inc()
                except Exception:
                    pass
                return AnswerOutput(
                    decision="PASS",
                    answer=answer,
                    followup_questions=[],
                    citations=citations,
                    confidence=confidence,
                    debug={
                        "trace_id": trace_id,
                        "retrieval_stats": evidence_pack.retrieval_stats,
                        "attempt": attempt,
                    },
                )

            if last_reviewer_result.status == ReviewerStatus.ASK_USER:
                try:
                    from app.core.metrics import decision_total
                    decision_total.labels(decision="ASK_USER").inc()
                except Exception:
                    pass
                return AnswerOutput(
                    decision="ASK_USER",
                    answer=answer,
                    followup_questions=followup or ["Could you provide more details?"],
                    citations=citations,
                    confidence=confidence,
                    debug={
                        "trace_id": trace_id,
                        "retrieval_stats": evidence_pack.retrieval_stats,
                        "reviewer_reasons": last_reviewer_result.reasons,
                    },
                )

            if last_reviewer_result.status == ReviewerStatus.ESCALATE:
                try:
                    from app.core.metrics import decision_total, escalation_rate
                    decision_total.labels(decision="ESCALATE").inc()
                    escalation_rate.inc()
                except Exception:
                    pass
                return AnswerOutput(
                    decision="ESCALATE",
                    answer=answer or "This request requires human review. A support agent will follow up.",
                    followup_questions=[],
                    citations=citations,
                    confidence=confidence,
                    debug={
                        "trace_id": trace_id,
                        "retrieval_stats": evidence_pack.retrieval_stats,
                        "reviewer_reasons": last_reviewer_result.reasons,
                    },
                )

            # RETRIEVE_MORE - try suggested queries
            if last_reviewer_result.suggested_queries and attempt < max_attempts:
                query = last_reviewer_result.suggested_queries[0]
                attempt += 1
                continue

            attempt += 1

        # Max attempts reached
        return AnswerOutput(
            decision="ASK_USER",
            answer=answer if last_reviewer_result else "I need more information to help. Could you clarify your question?",
            followup_questions=followup or ["What specifically would you like to know?"],
            citations=citations,
            confidence=confidence,
            debug={
                "trace_id": trace_id,
                "retrieval_stats": evidence_pack.retrieval_stats if evidence_pack else {},
                "reviewer_reasons": last_reviewer_result.reasons if last_reviewer_result else [],
                "max_attempts_reached": True,
            },
        )
