#!/usr/bin/env python3
"""Run replay-style offline eval and write baseline dashboard artifacts."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

from app.services.answer_service import AnswerService
from app.services.offline_eval import (
    dump_eval_run_json,
    dump_eval_run_markdown,
    load_eval_cases_jsonl,
    persist_eval_run,
    run_offline_eval,
)


def _default_run_id() -> str:
    return datetime.now().strftime("baseline-%Y%m%d-%H%M%S")


def _rate(value: float | None) -> float:
    return float(value or 0.0)


def _threshold_violation(name: str, observed: float | None, max_allowed: float | None) -> str | None:
    if max_allowed is None:
        return None
    rate = _rate(observed)
    if rate <= max_allowed:
        return None
    return f"{name}: observed={rate:.4f} > allowed={max_allowed:.4f}"


async def _run(args: argparse.Namespace) -> int:
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    run_id = args.run_id or _default_run_id()
    output_json = Path(args.output_json) if args.output_json else Path("artifacts/offline_eval") / f"{run_id}.json"
    output_md = Path(args.output_md) if args.output_md else output_json.with_suffix(".md")

    cases = load_eval_cases_jsonl(dataset_path)
    if args.min_cases and len(cases) < args.min_cases:
        print(
            f"[warn] dataset has {len(cases)} cases; target baseline set is >= {args.min_cases}. "
            "Run can continue, but this is below golden-set target."
        )

    service = None if args.use_recorded_output else AnswerService()
    summary, results = await run_offline_eval(
        service,
        cases,
        run_id=run_id,
        use_recorded_output=args.use_recorded_output,
    )

    dump_eval_run_json(output_json, summary, results)
    dump_eval_run_markdown(output_md, summary, results)
    if args.persist:
        await persist_eval_run(cases, results)

    print(f"run_id={summary.run_id}")
    print(f"cases={summary.case_count} pass_rate={summary.pass_rate:.2%}")
    print(f"wrong_but_cited_rate={_rate(summary.wrong_but_cited_rate):.2%}")
    print(f"answer_type_mismatch_rate={_rate(summary.answer_type_mismatch_rate):.2%}")
    print(f"partial_without_disclaimer_rate={_rate(summary.partial_without_disclaimer_rate):.2%}")
    print(f"faq_returned_for_link_lookup_rate={_rate(summary.faq_returned_for_link_lookup_rate):.2%}")
    print(f"json={output_json}")
    print(f"md={output_md}")

    violations = [
        _threshold_violation(
            "wrong_but_cited_rate",
            summary.wrong_but_cited_rate,
            args.max_wrong_but_cited_rate,
        ),
        _threshold_violation(
            "answer_type_mismatch_rate",
            summary.answer_type_mismatch_rate,
            args.max_answer_type_mismatch_rate,
        ),
        _threshold_violation(
            "partial_without_disclaimer_rate",
            summary.partial_without_disclaimer_rate,
            args.max_partial_without_disclaimer_rate,
        ),
        _threshold_violation(
            "faq_returned_for_link_lookup_rate",
            summary.faq_returned_for_link_lookup_rate,
            args.max_faq_for_link_lookup_rate,
        ),
    ]
    violations = [v for v in violations if v]
    if violations:
        print("[fail] regression guardrails violated:")
        for line in violations:
            print(f"  - {line}")
        return 2
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline replay eval baseline")
    parser.add_argument(
        "--dataset",
        default="tests/fixtures/offline_eval_replay_cases.jsonl",
        help="Path to replay JSONL dataset",
    )
    parser.add_argument("--run-id", default=None, help="Explicit run id")
    parser.add_argument("--output-json", default=None, help="Output JSON path")
    parser.add_argument("--output-md", default=None, help="Output markdown dashboard path")
    parser.add_argument(
        "--min-cases",
        type=int,
        default=100,
        help="Warn when dataset has fewer cases than this target",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist eval run into eval_cases/eval_results tables",
    )
    parser.add_argument(
        "--use-recorded-output",
        action="store_true",
        help="Use recorded_output from dataset instead of calling AnswerService",
    )
    parser.add_argument(
        "--max-wrong-but-cited-rate",
        type=float,
        default=None,
        help="Fail if wrong_but_cited rate exceeds this threshold",
    )
    parser.add_argument(
        "--max-answer-type-mismatch-rate",
        type=float,
        default=None,
        help="Fail if answer_type_mismatch rate exceeds this threshold",
    )
    parser.add_argument(
        "--max-partial-without-disclaimer-rate",
        type=float,
        default=None,
        help="Fail if partial_without_disclaimer rate exceeds this threshold",
    )
    parser.add_argument(
        "--max-faq-for-link-lookup-rate",
        type=float,
        default=None,
        help="Fail if faq_returned_for_link_lookup rate exceeds this threshold",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
