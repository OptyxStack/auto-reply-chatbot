"""LLM-based document type classifier. Replaces URL-based inference with content-aware classification."""

import json
import re

from app.core.logging import get_logger
from app.services.archi_config import get_doc_type_classifier_enabled
from app.services.doc_type_service import get_doc_types_for_prompt, get_valid_doc_type_keys
from app.services.llm_gateway import get_llm_gateway
from app.services.model_router import get_model_for_task
from app.services.web_crawler import _doc_type_from_url

logger = get_logger(__name__)


def _build_classifier_prompt() -> str:
    """Build prompt from DB doc types or defaults."""
    types_list = get_doc_types_for_prompt()
    lines = [f"- {k}: {desc}" for k, desc in types_list]
    types_str = "|".join(f'"{k}"' for k, _ in types_list)
    return f"""Classify this document into exactly one type based on its content.

Types:
{chr(10).join(lines)}

Output JSON only, no markdown:
{{"doc_type": {types_str}}}"""


async def classify_doc_type(url: str, title: str, content: str) -> str:
    if not get_doc_type_classifier_enabled():
        return "other"

    # Truncate content to avoid token limit (e.g. 4k chars ~1k tokens)
    content_preview = (content or "").strip()[:4000]
    if not content_preview:
        return "other"

    user_content = f"URL: {url}\nTitle: {title}\n\nContent:\n{content_preview}"

    try:
        from app.core.tracing import current_llm_task_var
        current_llm_task_var.set("doc_type_classifier")
        llm = get_llm_gateway()
        model = get_model_for_task("doc_type_classifier")
        prompt = _build_classifier_prompt()
        resp = await llm.chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            model=model,
            max_tokens=32,
        )
        text = (resp.content or "").strip()
        if "```json" in text:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
            text = match.group(1) if match else text
        elif "```" in text:
            match = re.search(r"```\s*([\s\S]*?)\s*```", text)
            text = match.group(1) if match else text

        data = json.loads(text)
        doc_type = (data.get("doc_type") or "other").strip().lower()
        valid = get_valid_doc_type_keys()
        if doc_type in valid:
            logger.debug("doc_type_classifier", url=url[:60], doc_type=doc_type)
            return doc_type
        return "other"
    except Exception as e:
        logger.warning("doc_type_classifier_failed", url=url[:60], error=str(e))
        return "other"


async def resolve_doc_type(url: str, title: str, content: str) -> str:
    """
    Resolve doc_type: use LLM classifier when enabled (Settings UI), else URL-based fallback.
    """
    if get_doc_type_classifier_enabled():
        return await classify_doc_type(url, title, content)
    return _doc_type_from_url(url)
