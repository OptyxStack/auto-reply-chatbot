#!/usr/bin/env python3
"""
Ingest documents from source/ JSON files into the database.
Run from project root: python scripts/ingest_from_source.py

Requires: PostgreSQL, Redis, OpenSearch, Qdrant running (or docker-compose up).
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _doc_type_from_url(url: str) -> str:
    """Infer doc_type from URL."""
    url_lower = url.lower()
    if "terms" in url_lower or "tos" in url_lower:
        return "tos"
    if "privacy" in url_lower or "policy" in url_lower:
        return "policy"
    if "faq" in url_lower or "faqs" in url_lower:
        return "faq"
    if "docs" in url_lower or "documentation" in url_lower:
        return "howto"
    if "vps" in url_lower or "billing" in url_lower or "store" in url_lower:
        return "pricing"
    return "other"


def load_green_cloud_docs_full(path: Path) -> list[dict]:
    """Load green_cloud_docs_full.json - pages with url, title, text."""
    with open(path) as f:
        data = json.load(f)
    docs = []
    for p in data.get("pages", []):
        url = p.get("url")
        text = p.get("text", "").strip()
        if not url or len(text) < 50:  # Skip empty/short pages
            continue
        docs.append({
            "url": url,
            "title": p.get("title", "Untitled"),
            "raw_text": text,
            "doc_type": _doc_type_from_url(url),
            "metadata": {"source": data.get("source", "")},
            "source_file": path.name,
        })
    return docs


def load_green_cloud_docs_knowledge(path: Path) -> list[dict]:
    """Load green_cloud_docs_knowledge.json - articles with url, title, snippet."""
    with open(path) as f:
        data = json.load(f)
    docs = []
    for a in data.get("articles", []):
        url = a.get("url")
        snippet = a.get("snippet", "").strip()
        if not url or len(snippet) < 50:
            continue
        docs.append({
            "url": url,
            "title": a.get("title", "Untitled"),
            "raw_text": snippet,
            "doc_type": _doc_type_from_url(url),
            "metadata": {"key_points": a.get("key_points", [])},
            "source_file": path.name,
        })
    return docs


def load_greencloudvps_plans(path: Path) -> list[dict]:
    """Load greencloudvps_advanced_data.json or additional_plans - plans list."""
    with open(path) as f:
        data = json.load(f)
    docs = []
    for plan in data.get("plans", []):
        source_url = plan.get("source_url") or plan.get("order_link", "")
        plan_name = plan.get("plan_name", "unknown")
        url = f"{source_url}#plan-{plan_name}" if source_url else f"plan://{plan_name}"
        text_parts = [f"Plan: {plan_name}"]
        if plan.get("price_raw"):
            text_parts.append(f"Price: {plan['price_raw']}")
        if plan.get("billing_cycle"):
            text_parts.append(f"Billing: {plan['billing_cycle']}")
        for k in ("ram", "cpu", "storage", "bandwidth", "port", "os", "location"):
            if plan.get(k):
                text_parts.append(f"{k}: {plan[k]}")
        if plan.get("order_link"):
            text_parts.append(f"Order: {plan['order_link']}")
        text = "\n".join(text_parts)
        docs.append({
            "url": url,
            "title": f"Plan {plan_name}",
            "raw_text": text,
            "doc_type": "pricing",
            "metadata": {
                "product": plan_name,
                "category": "VPS Plans",
                "plan_name": plan_name,
                "price_raw": plan.get("price_raw"),
                "order_link": plan.get("order_link"),
            },
            "source_file": path.name,
        })
    return docs


def load_greencloud_chatbot_master(path: Path) -> list[dict]:
    """Load greencloud_chatbot_master.json - sales_knowledge + docs_knowledge."""
    with open(path) as f:
        data = json.load(f)
    docs = []
    datasets = data.get("datasets", {})

    # Sales knowledge: product_categories with summary + plans
    sales = datasets.get("sales_knowledge", {})
    if sales:
        global_highlights = sales.get("global_highlights", [])
        for cat in sales.get("product_categories", []):
            url = cat.get("url", "")
            summary = cat.get("summary", "").strip()
            if not url or len(summary) < 30:
                continue
            plans_text = []
            for p in cat.get("plans", [])[:20]:  # Limit plans per doc
                plans_text.append(
                    f"{p.get('plan_name', '')}: ${p.get('price_usd_month', 0)}/mo - "
                    f"{p.get('memory', '')} RAM, {p.get('storage', '')} storage"
                )
            full_text = summary + "\n\nPlans:\n" + "\n".join(plans_text) if plans_text else summary
            docs.append({
                "url": url,
                "title": cat.get("title", cat.get("category", "Untitled")),
                "raw_text": full_text,
                "doc_type": "pricing",
                "metadata": {
                    "product": cat.get("category"),
                    "category": cat.get("category"),
                    "global_highlights": global_highlights[:5],
                },
                "source_file": path.name,
            })

    # Skip docs_knowledge - overlaps with green_cloud_docs_full.json (full text preferred)

    return docs


def load_all_docs(source_dir: Path, files: list[str] | None = None) -> list[dict]:
    """Load docs from all JSON files in source_dir."""
    from app.services.source_loaders import load_all_docs as _load
    return _load(source_dir, files)


async def ensure_migrations() -> None:
    """Run migrations if documents table does not exist."""
    from sqlalchemy import text
    from app.db.session import engine
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM documents LIMIT 1"))
    except Exception:
        print("Tables not found. Running migrations...")
        import subprocess
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parent.parent,
        )
        if result.returncode != 0:
            raise RuntimeError("Migrations failed. Run: alembic upgrade head")
        print("Migrations complete.")


async def run_ingest(docs: list[dict], skip_existing: bool = True) -> dict:
    """Run ingestion via IngestionService."""
    await ensure_migrations()

    from app.db.session import async_session_factory
    from app.services.ingestion import IngestionService

    svc = IngestionService()
    results = {"ok": 0, "skipped": 0, "error": 0}

    for i, doc in enumerate(docs):
        try:
            async with async_session_factory() as session:
                result = await svc.ingest_document(doc, session)
                if result:
                    results["ok"] += 1
                else:
                    results["skipped"] += 1
        except Exception as e:
            results["error"] += 1
            print(f"  Error doc {i} ({doc.get('url', '')[:50]}): {e}")

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{len(docs)}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Ingest docs from source/ JSON files")
    parser.add_argument("--source-dir", default="source", help="Path to source directory")
    parser.add_argument("--files", nargs="*", help="Specific files to load (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Only load, don't ingest")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        print(f"Source directory not found: {source_dir}")
        sys.exit(1)

    print("Loading documents from JSON files...")
    docs = load_all_docs(source_dir, args.files)
    print(f"Total documents to ingest: {len(docs)}")

    if not docs:
        print("No documents to ingest.")
        sys.exit(0)

    if args.dry_run:
        print("Dry run - skipping ingest.")
        print(f"Sample: {docs[0]}")
        sys.exit(0)

    print("Running ingestion...")
    results = asyncio.run(run_ingest(docs))
    print(f"Done: {results['ok']} ok, {results['skipped']} skipped, {results['error']} errors")


if __name__ == "__main__":
    main()
