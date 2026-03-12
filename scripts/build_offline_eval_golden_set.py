#!/usr/bin/env python3
"""Build a replay golden set (100+) from real ticket traces."""

from __future__ import annotations

import argparse
import html
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

CATEGORY_ORDER = ["link", "pricing", "policy", "troubleshooting", "general"]
CATEGORY_WEIGHTS = {
    "link": 0.24,
    "pricing": 0.24,
    "policy": 0.20,
    "troubleshooting": 0.20,
    "general": 0.12,
}
ANSWER_TYPE_BY_CATEGORY = {
    "link": "direct_link",
    "pricing": "pricing",
    "policy": "policy",
    "troubleshooting": "troubleshooting",
    "general": "general",
}
REQUIRED_EVIDENCE_BY_CATEGORY = {
    "link": ["transaction_link"],
    "pricing": ["numbers_units"],
    "policy": ["policy_language"],
    "troubleshooting": ["steps_structure"],
    "general": [],
}
GENERIC_SUBJECTS = {
    "",
    "question",
    "support",
    "help",
    "request received",
    "[request received]",
    "ticket",
}
LINK_KEYWORDS = (
    "link",
    "order",
    "buy",
    "purchase",
    "checkout",
    "cart",
    "where can i",
    "url",
)
PRICING_KEYWORDS = (
    "price",
    "cost",
    "how much",
    "monthly",
    "billing",
    "discount",
    "coupon",
    "promotion",
    "per month",
)
POLICY_KEYWORDS = (
    "refund",
    "policy",
    "tos",
    "terms",
    "cancel",
    "cancellation",
    "chargeback",
    "guarantee",
)
TROUBLESHOOTING_KEYWORDS = (
    "how to",
    "can't",
    "cannot",
    "unable",
    "error",
    "issue",
    "problem",
    "not working",
    "reset",
    "configure",
    "setup",
    "install",
    "access",
    "connection",
    "reboot",
)
URL_RE = re.compile(r"https?://[^\s)\]>]+", re.IGNORECASE)
PRICE_RE = re.compile(r"\$\s?\d+(?:[.,]\d+)?(?:\s*/\s*(?:mo|month|monthly))?", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
AMBIGUOUS_RE = re.compile(r"^(what about|how about|this one|that one|this|that|it|same as above)\b", re.IGNORECASE)


@dataclass
class CandidateCase:
    category: str
    score: float
    case: dict[str, Any]


def _clean_text(value: Any, *, max_len: int = 600) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\r", "\n")
    text = TAG_RE.sub(" ", text)
    text = SPACE_RE.sub(" ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return text


def _extract_urls(text: str, limit: int = 3) -> list[str]:
    urls = []
    for raw in URL_RE.findall(text or ""):
        url = raw.strip().rstrip(".,);")
        if url and url not in urls:
            urls.append(url)
            if len(urls) >= limit:
                break
    return urls


def _pick_query_fragment(text: str) -> str:
    lines = [segment.strip(" -:") for segment in re.split(r"[\n]+", text) if segment.strip()]
    if not lines:
        return ""
    for line in lines:
        if 12 <= len(line) <= 320 and "?" in line:
            return line
    for line in lines:
        low = line.lower()
        if any(k in low for k in LINK_KEYWORDS + PRICING_KEYWORDS + POLICY_KEYWORDS + TROUBLESHOOTING_KEYWORDS):
            return line[:320]
    return lines[0][:320]


def _extract_customer_query(ticket: dict[str, Any]) -> str:
    subject = _clean_text(ticket.get("subject"), max_len=180)
    description = _clean_text(ticket.get("description"), max_len=1200)
    metadata = ticket.get("metadata") if isinstance(ticket.get("metadata"), dict) else {}
    replies = metadata.get("replies") if isinstance(metadata.get("replies"), list) else []

    customer_reply = ""
    for reply in replies:
        if not isinstance(reply, dict):
            continue
        role = str(reply.get("role", "")).strip().lower()
        if role == "customer":
            customer_reply = _clean_text(reply.get("content"), max_len=1200)
            if customer_reply:
                break

    base = customer_reply or description or subject
    fragment = _pick_query_fragment(base)
    if not fragment:
        return ""

    subject_norm = subject.lower().strip()
    if subject and subject_norm not in GENERIC_SUBJECTS and subject.lower() not in fragment.lower():
        combined = f"{subject}: {fragment}"
    else:
        combined = fragment
    return _clean_text(combined, max_len=320)


def _extract_staff_answer(ticket: dict[str, Any]) -> str:
    metadata = ticket.get("metadata") if isinstance(ticket.get("metadata"), dict) else {}
    replies = metadata.get("replies") if isinstance(metadata.get("replies"), list) else []
    for reply in replies:
        if not isinstance(reply, dict):
            continue
        role = str(reply.get("role", "")).strip().lower()
        if role == "staff":
            content = _clean_text(reply.get("content"), max_len=900)
            if content:
                return content
    return ""


def _is_ambiguous_query(query: str) -> bool:
    q = (query or "").strip()
    if not q:
        return True
    ql = q.lower()
    if AMBIGUOUS_RE.search(ql):
        return True
    words = ql.split()
    if len(words) <= 4 and any(w in {"this", "that", "it", "one"} for w in words):
        return True
    return False


def _classify_category(query: str, staff_answer: str) -> str:
    text = f"{query}\n{staff_answer}".lower()
    if any(k in text for k in LINK_KEYWORDS):
        return "link"
    if any(k in text for k in PRICING_KEYWORDS):
        return "pricing"
    if any(k in text for k in POLICY_KEYWORDS):
        return "policy"
    if any(k in text for k in TROUBLESHOOTING_KEYWORDS):
        return "troubleshooting"
    return "general"


def _guess_doc_type(url: str) -> str:
    low = (url or "").lower()
    if any(x in low for x in ("policy", "refund", "terms", "tos")):
        return "policy"
    if any(x in low for x in ("faq", "/blog")):
        return "faq"
    if any(x in low for x in ("docs", "knowledgebase", "/kb", "how-to", "howto")):
        return "howto"
    if any(x in low for x in ("order", "cart", "store", "billing", "pricing", "plan")):
        return "pricing"
    return "other"


def _build_expected_contains(category: str, query: str, staff_answer: str) -> list[str]:
    out: list[str] = []
    ql = query.lower()
    al = staff_answer.lower()

    if category == "link":
        urls = _extract_urls(staff_answer, limit=1)
        if urls:
            out.extend(urls)
        elif "order" in ql:
            out.append("order")
        else:
            out.append("link")
    elif category == "pricing":
        prices = PRICE_RE.findall(staff_answer)
        if prices:
            out.append(prices[0].strip())
        out.append("$")
    elif category == "policy":
        out.append("refund" if ("refund" in ql or "refund" in al) else "policy")
    elif category == "troubleshooting":
        if "step" in al:
            out.append("step")
        elif "restart" in al:
            out.append("restart")
        else:
            out.append("fix")
    return list(dict.fromkeys([s for s in out if s]))


def _derive_answer_mode(category: str, decision: str, staff_answer: str) -> str | None:
    if decision != "PASS":
        return None
    answer = (staff_answer or "").lower()
    if category == "link":
        return "partial" if not _extract_urls(staff_answer, limit=1) else "exact"
    if category == "pricing":
        return "partial" if not PRICE_RE.search(answer) else "exact"
    if category == "policy":
        return "partial" if "refund" not in answer and "policy" not in answer else "exact"
    if category == "troubleshooting":
        return "partial" if "step" not in answer and "please" not in answer else "exact"
    return "exact"


def _build_recorded_output(
    ticket_id: str,
    decision: str,
    answer: str,
    answer_mode: str | None,
) -> dict[str, Any]:
    urls = _extract_urls(answer, limit=3)
    citations: list[dict[str, str]] = []
    evidence_summary: list[dict[str, str]] = []
    for idx, url in enumerate(urls, start=1):
        row = {
            "chunk_id": f"trace-{ticket_id}-{idx}",
            "source_url": url,
            "doc_type": _guess_doc_type(url),
        }
        citations.append(dict(row))
        evidence_summary.append(dict(row))

    if decision == "ASK_USER":
        lane = "ASK_USER"
        reason = "ambiguous_query"
        confidence = 0.0
    elif answer_mode == "partial":
        lane = "PASS_WEAK"
        reason = "answerable_with_refinement"
        confidence = 0.55
    else:
        lane = "PASS_STRONG"
        reason = "sufficient"
        confidence = 0.8

    return {
        "decision": decision,
        "answer": answer,
        "followup_questions": [],
        "citations": citations,
        "confidence": confidence,
        "debug": {
            "evidence_summary": evidence_summary,
            "decision_router": {
                "decision": decision,
                "lane": lane,
                "reason": reason,
            },
        },
    }


def _score_candidate(
    category: str,
    decision: str,
    answer_mode: str | None,
    staff_answer: str,
) -> float:
    score = 0.0
    if category in {"link", "pricing", "policy"}:
        score += 1.5
    if answer_mode == "partial":
        score += 3.0
    if decision == "ASK_USER":
        score += 2.0
    if category == "link" and not _extract_urls(staff_answer, limit=1):
        score += 2.0
    if category == "pricing" and not PRICE_RE.search(staff_answer or ""):
        score += 1.0
    return score


def _build_case(ticket: dict[str, Any], index: int) -> CandidateCase | None:
    query = _extract_customer_query(ticket)
    if len(query) < 8:
        return None

    staff_answer = _extract_staff_answer(ticket)
    category = _classify_category(query, staff_answer)
    ambiguous = _is_ambiguous_query(query)
    decision = "ASK_USER" if ambiguous else "PASS"
    answer_mode = _derive_answer_mode(category, decision, staff_answer)

    if decision == "ASK_USER":
        answer_text = "Could you clarify which product or plan you mean?"
    elif staff_answer:
        answer_text = staff_answer
    else:
        answer_text = "Based on available information, please contact support with more details."
        answer_mode = "partial"

    ticket_id = str(ticket.get("external_id") or ticket.get("id") or f"idx-{index}")
    case_name = f"trace_{ticket_id}_{index}"
    tags = [
        "replay",
        "real_trace",
        f"category_{category}",
    ]
    if answer_mode == "partial":
        tags.append("trace_error_candidate")

    expected_contains = _build_expected_contains(category, query, answer_text)
    expected_type = ANSWER_TYPE_BY_CATEGORY[category]
    related_types = ["pricing"] if expected_type == "direct_link" else []

    case = {
        "name": case_name,
        "input": query,
        "tags": tags,
        "expected_decision": decision,
        "expected_answer_type": expected_type if decision == "PASS" else "clarification",
        "acceptable_related_types": related_types,
        "expected_answer_mode": answer_mode,
        "replay_category": category,
        "expected_chunk_ids": [],
        "required_evidence": REQUIRED_EVIDENCE_BY_CATEGORY[category],
        "expected_answer_contains": expected_contains,
        "forbidden_answer_contains": [],
        "metadata": {
            "source": "sample_conversations",
            "trace_external_id": str(ticket.get("external_id") or ""),
            "trace_ticket_id": str(ticket.get("id") or ""),
            "trace_status": str(ticket.get("status") or ""),
            "trace_priority": str(ticket.get("priority") or ""),
        },
        "recorded_output": _build_recorded_output(ticket_id, decision, answer_text, answer_mode),
    }
    score = _score_candidate(category, decision, answer_mode, staff_answer)
    return CandidateCase(category=category, score=score, case=case)


def _normalized_query_key(query: str) -> str:
    return SPACE_RE.sub(" ", (query or "").lower()).strip()


def _allocate_targets(total: int) -> dict[str, int]:
    targets = {cat: int(total * CATEGORY_WEIGHTS[cat]) for cat in CATEGORY_ORDER}
    allocated = sum(targets.values())
    remaining = max(0, total - allocated)
    idx = 0
    while remaining > 0:
        cat = CATEGORY_ORDER[idx % len(CATEGORY_ORDER)]
        targets[cat] += 1
        remaining -= 1
        idx += 1
    return targets


def _iter_conversations(path: Path, max_items: int = 0) -> Iterator[dict[str, Any]]:
    """Stream conversation objects from source JSON without loading full file."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        in_array = False
        in_string = False
        escape = False
        depth = 0
        buffer: list[str] = []
        yielded = 0

        for line in fh:
            segment = line
            if not in_array:
                if '"conversations"' not in line:
                    continue
                bracket = line.find("[")
                if bracket == -1:
                    in_array = True
                    continue
                in_array = True
                segment = line[bracket + 1 :]

            i = 0
            while i < len(segment):
                ch = segment[i]
                if depth == 0:
                    if ch == "{":
                        depth = 1
                        in_string = False
                        escape = False
                        buffer = ["{"]
                    elif ch == "]":
                        return
                    i += 1
                    continue

                buffer.append(ch)
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                else:
                    if ch == '"':
                        in_string = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                obj = json.loads("".join(buffer))
                            except json.JSONDecodeError:
                                obj = None
                            if isinstance(obj, dict):
                                yield obj
                                yielded += 1
                                if max_items and yielded >= max_items:
                                    return
                            buffer = []
                i += 1


def _load_existing_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")


def build_golden_set(
    *,
    source_json: Path,
    output_jsonl: Path,
    target_count: int,
    seed: int,
    max_scan: int,
    include_existing: Path | None,
) -> dict[str, Any]:
    rand = random.Random(seed)
    pools: dict[str, list[CandidateCase]] = {cat: [] for cat in CATEGORY_ORDER}
    pool_cap = max(400, target_count * 14)
    scanned = 0
    built = 0

    for idx, ticket in enumerate(_iter_conversations(source_json, max_items=max_scan), start=1):
        scanned += 1
        candidate = _build_case(ticket, idx)
        if candidate is None:
            continue
        built += 1
        bucket = pools[candidate.category]
        if len(bucket) < pool_cap:
            bucket.append(candidate)
            continue
        min_idx = min(range(len(bucket)), key=lambda i: bucket[i].score)
        if candidate.score > bucket[min_idx].score:
            bucket[min_idx] = candidate
        elif rand.random() < 0.02:
            bucket[rand.randrange(len(bucket))] = candidate

    targets = _allocate_targets(target_count)
    selected: list[dict[str, Any]] = []
    selected_names: set[str] = set()
    selected_queries: set[str] = set()

    existing_rows: list[dict[str, Any]] = []
    if include_existing:
        existing_rows = _load_existing_cases(include_existing)

    for row in existing_rows:
        if len(selected) >= target_count:
            break
        query_key = _normalized_query_key(str(row.get("input", "")))
        name = str(row.get("name", "")).strip()
        if not query_key or not name or query_key in selected_queries or name in selected_names:
            continue
        selected.append(row)
        selected_names.add(name)
        selected_queries.add(query_key)

    by_category: dict[str, list[CandidateCase]] = {}
    for cat in CATEGORY_ORDER:
        by_category[cat] = sorted(
            pools[cat],
            key=lambda c: (c.score, c.case.get("name", "")),
            reverse=True,
        )

    for cat in CATEGORY_ORDER:
        quota = targets.get(cat, 0)
        if quota <= 0:
            continue
        for candidate in by_category[cat]:
            if len(selected) >= target_count:
                break
            query_key = _normalized_query_key(str(candidate.case.get("input", "")))
            name = str(candidate.case.get("name", ""))
            if not query_key or not name or query_key in selected_queries or name in selected_names:
                continue
            selected.append(candidate.case)
            selected_names.add(name)
            selected_queries.add(query_key)
            quota -= 1
            if quota == 0:
                break

    if len(selected) < target_count:
        leftovers: list[CandidateCase] = []
        for cat in CATEGORY_ORDER:
            leftovers.extend(by_category[cat])
        leftovers.sort(key=lambda c: (c.score, c.case.get("name", "")), reverse=True)
        for candidate in leftovers:
            if len(selected) >= target_count:
                break
            query_key = _normalized_query_key(str(candidate.case.get("input", "")))
            name = str(candidate.case.get("name", ""))
            if not query_key or not name or query_key in selected_queries or name in selected_names:
                continue
            selected.append(candidate.case)
            selected_names.add(name)
            selected_queries.add(query_key)

    selected = selected[:target_count]
    selected.sort(key=lambda row: (str(row.get("replay_category", "")), str(row.get("name", ""))))
    _write_jsonl(output_jsonl, selected)

    category_counts = {cat: 0 for cat in CATEGORY_ORDER}
    partial_count = 0
    for row in selected:
        category = str(row.get("replay_category") or "general")
        category_counts[category] = category_counts.get(category, 0) + 1
        if str(row.get("expected_answer_mode") or "").lower() == "partial":
            partial_count += 1

    return {
        "output": str(output_jsonl),
        "scanned": scanned,
        "built_candidates": built,
        "selected": len(selected),
        "category_counts": category_counts,
        "partial_cases": partial_count,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build offline eval replay golden set from real traces")
    parser.add_argument(
        "--source-json",
        default="source/sample_conversations.json",
        help="Path to source conversations JSON",
    )
    parser.add_argument(
        "--output",
        default="tests/fixtures/offline_eval_replay_cases_golden.jsonl",
        help="Output replay JSONL path",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=120,
        help="Number of replay cases to emit",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for stable sampling",
    )
    parser.add_argument(
        "--max-scan",
        type=int,
        default=0,
        help="Maximum conversations to scan (0 = full file)",
    )
    parser.add_argument(
        "--include-existing",
        default="tests/fixtures/offline_eval_replay_cases.jsonl",
        help="Optional existing replay JSONL to include first",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    source_json = Path(args.source_json)
    if not source_json.exists():
        raise FileNotFoundError(f"source file not found: {source_json}")

    include_existing = Path(args.include_existing) if args.include_existing else None
    summary = build_golden_set(
        source_json=source_json,
        output_jsonl=Path(args.output),
        target_count=max(1, int(args.target_count)),
        seed=int(args.seed),
        max_scan=max(0, int(args.max_scan)),
        include_existing=include_existing,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
