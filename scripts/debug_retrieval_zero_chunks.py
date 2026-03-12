#!/usr/bin/env python3
"""Debug why retrieval returns 0 chunks (BM25=0, Vector=0).

Usage:
    python scripts/debug_retrieval_zero_chunks.py
    python scripts/debug_retrieval_zero_chunks.py --query "my rdp"
    python scripts/debug_retrieval_zero_chunks.py --query "RDP can't connect" --with-context
"""

import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from app.core.config import get_settings
from app.search.embeddings import get_embedding_provider
from app.search.opensearch_client import OpenSearchClient
from app.search.qdrant_client import QdrantSearchClient
from app.services.retrieval_planner import build_retrieval_plan_for_attempt
from app.services.normalizer import normalize


async def check_opensearch_connection(opensearch: OpenSearchClient) -> dict:
    """Check OpenSearch connectivity and index stats."""
    result = {"ok": False, "error": None, "index_exists": False}
    try:
        await opensearch.search(
            query="test",
            top_n=1,
            doc_types=None,
            boost_pricing=False,
            use_highlight=False,
        )
        result["ok"] = True
        result["index_exists"] = True
    except Exception as e:
        result["error"] = str(e)
    return result


async def check_qdrant_connection(qdrant: QdrantSearchClient) -> dict:
    """Check Qdrant connectivity and collection stats."""
    result = {"ok": False, "error": None, "collection_exists": False, "points_count": 0}
    try:
        collection = get_settings().qdrant_collection
        client = qdrant._get_client()
        try:
            info = client.get_collection(collection)
            result["ok"] = True
            result["collection_exists"] = True
            result["points_count"] = info.points_count or 0
        except Exception as e:
            if "not found" in str(e).lower():
                result["ok"] = True
                result["collection_exists"] = False
            else:
                result["error"] = str(e)
    except Exception as e:
        result["error"] = str(e)
    return result


async def run_bm25_raw(opensearch: OpenSearchClient, query: str, top_n: int = 20) -> list:
    """BM25 search with NO doc_type filter."""
    return await opensearch.search(
        query=query,
        top_n=top_n,
        doc_types=None,
        boost_pricing=False,
        use_highlight=False,
    )


async def run_bm25_filtered(
    opensearch: OpenSearchClient,
    query: str,
    doc_types: list[str],
    top_n: int = 30,
    page_kinds: list[str] | None = None,
) -> list:
    """BM25 search WITH doc_type filter (and optional page_kinds)."""
    return await opensearch.search(
        query=query,
        top_n=top_n,
        doc_types=doc_types,
        boost_pricing=False,
        use_highlight=False,
        page_kinds=page_kinds,
    )


async def run_vector_raw(qdrant, embedder, query: str, top_n: int = 20) -> list:
    """Vector search with NO doc_type filter."""
    vectors = await embedder.embed([query])
    if not vectors or not vectors[0]:
        return []
    return qdrant.search(vector=vectors[0], top_n=top_n, doc_types=None)


async def run_vector_filtered(qdrant, embedder, query: str, doc_types: list[str], top_n: int = 30) -> list:
    """Vector search WITH doc_type filter."""
    vectors = await embedder.embed([query])
    if not vectors or not vectors[0]:
        return []
    return qdrant.search(vector=vectors[0], top_n=top_n, doc_types=doc_types)


async def main_async(args) -> int:
    settings = get_settings()
    opensearch = OpenSearchClient()
    qdrant = QdrantSearchClient()
    embedder = get_embedding_provider()

    query = args.query or "my rdp"
    print("=" * 70)
    print(f"DEBUG: Why retrieval returns 0 chunks for query: {query!r}")
    print("=" * 70)

    # --- 1. Connection & index check ---
    print("\n--- 1. OPENSEARCH ---")
    os_result = await check_opensearch_connection(opensearch)
    if os_result["error"]:
        print(f"  ERROR: {os_result['error']}")
        print("  -> OpenSearch may be down or misconfigured. Check OPENSEARCH_HOST, docker-compose.")
    else:
        print(f"  Connected: OK")
        print(f"  Index '{settings.opensearch_index}' exists: {os_result['index_exists']}")
        if not os_result["index_exists"]:
            print("  -> Index missing. Run ingestion first.")

    print("\n--- 2. QDRANT ---")
    qd_result = await check_qdrant_connection(qdrant)
    if qd_result["error"]:
        print(f"  ERROR: {qd_result['error']}")
        print("  -> Qdrant may be down. Check QDRANT_HOST, docker-compose.")
    else:
        print(f"  Connected: OK")
        print(f"  Collection '{settings.qdrant_collection}' exists: {qd_result['collection_exists']}")
        print(f"  Points count: {qd_result['points_count']}")
        if not qd_result["collection_exists"] or qd_result["points_count"] == 0:
            print("  -> Collection empty or missing. Run ingestion first.")

    # --- 3. BM25 raw (no filter) ---
    print("\n--- 3. BM25 RAW (no doc_type filter) ---")
    try:
        chunks = await run_bm25_raw(opensearch, query, top_n=30)
        print(f"  Query: {query!r} -> {len(chunks)} chunks")
        if chunks:
            for i, c in enumerate(chunks[:5], 1):
                print(f"    {i}. [{c.doc_type}] score={c.score:.3f} {c.source_url or '?'}")
        else:
            print("  -> 0 chunks. Index may be empty, or query terms don't match any document.")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    # --- 4. BM25 with troubleshooting doc_types ---
    print("\n--- 4. BM25 WITH doc_types=[howto, faq, docs, conversation] ---")
    doc_types = ["howto", "faq", "docs", "conversation"]
    try:
        chunks = await run_bm25_filtered(opensearch, query, doc_types, top_n=30)
        print(f"  Query: {query!r} -> {len(chunks)} chunks")
        if chunks:
            for i, c in enumerate(chunks[:5], 1):
                print(f"    {i}. [{c.doc_type}] score={c.score:.3f} {c.source_url or '?'}")
        else:
            print("  -> 0 chunks. No howto/faq/docs/conversation chunks match. Try broader terms.")
    except Exception as e:
        print(f"  ERROR: {e}")

    # --- 4b. BM25 with plan doc_types only (faq, howto, docs - NO conversation) ---
    print("\n--- 4b. BM25 WITH doc_types=[faq, howto, docs] (plan preferred, no conversation) ---")
    plan_doc_types = ["faq", "howto", "docs"]
    for test_query in [query, "RDP issue", "my remote desktop"]:
        try:
            chunks = await run_bm25_filtered(opensearch, test_query, plan_doc_types, top_n=30)
            print(f"  Query: {test_query!r} -> {len(chunks)} chunks")
            if chunks:
                for i, c in enumerate(chunks[:3], 1):
                    print(f"    {i}. [{c.doc_type}] score={c.score:.3f} {c.source_url or '?'}")
        except Exception as e:
            print(f"  Query: {test_query!r} ERROR: {e}")

    # --- 4c. BM25 with page_kinds filter (troubleshooting profile) ---
    print("\n--- 4c. BM25 WITH doc_types=[faq,howto,docs] + page_kinds=[howto,faq,product_page,pricing_table] ---")
    troubleshooting_page_kinds = ["howto", "faq", "product_page", "pricing_table"]
    try:
        chunks = await run_bm25_filtered(
            opensearch, "RDP issue", plan_doc_types, top_n=30, page_kinds=troubleshooting_page_kinds
        )
        print(f"  Query: 'RDP issue' -> {len(chunks)} chunks")
        if chunks:
            for i, c in enumerate(chunks[:3], 1):
                md = (c.metadata or {}) if hasattr(c, "metadata") else {}
                pk = md.get("page_kind", "?") if isinstance(md, dict) else "?"
                print(f"    {i}. [{c.doc_type}] page_kind={pk} score={c.score:.3f} {c.source_url or '?'}")
        else:
            print("  -> 0 chunks. Likely page_kind missing on indexed chunks. Chunks without page_kind are excluded.")
    except Exception as e:
        print(f"  ERROR: {e}")

    # --- 4d. VECTOR with plan doc_types (no page_kinds) ---
    print("\n--- 4d. VECTOR WITH doc_types=[faq, howto, docs] ---")
    for test_query in [query, "my remote desktop"]:
        try:
            chunks = await run_vector_filtered(qdrant, embedder, test_query, plan_doc_types, top_n=30)
            print(f"  Query: {test_query!r} -> {len(chunks)} chunks")
            if chunks:
                for i, c in enumerate(chunks[:3], 1):
                    print(f"    {i}. [{c.doc_type}] score={c.score:.3f} {c.source_url or '?'}")
        except Exception as e:
            print(f"  Query: {test_query!r} ERROR: {e}")

    # --- 5. Vector raw ---
    print("\n--- 5. VECTOR RAW (no doc_type filter) ---")
    try:
        chunks = await run_vector_raw(qdrant, embedder, query, top_n=30)
        print(f"  Query: {query!r} -> {len(chunks)} chunks")
        if chunks:
            for i, c in enumerate(chunks[:5], 1):
                print(f"    {i}. [{c.doc_type}] score={c.score:.3f} {c.source_url or '?'}")
        else:
            print("  -> 0 chunks. Collection empty or embedding failed.")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    # --- 6. Normalizer + plan ---
    spec = None
    conv = (
        [{"role": "user", "content": "cant connect"}, {"role": "assistant", "content": "What are you trying to connect to?"}]
        if args.with_context
        else []
    )
    if args.normalize:
        print("\n--- 6. NORMALIZER + RETRIEVAL PLAN ---")
        try:
            spec = await normalize(query, conversation_history=conv)
            if spec:
                print(f"  keyword_queries: {getattr(spec, 'keyword_queries', [])}")
                print(f"  semantic_queries: {getattr(spec, 'semantic_queries', [])}")
                print(f"  doc_type_prior: {getattr(spec, 'doc_type_prior', [])}")
            plan, _ = await build_retrieval_plan_for_attempt(
                base_query=query,
                attempt=1,
                query_spec=spec,
                conversation_history=conv,
            )
            print(f"  plan.query_keyword: {plan.query_keyword}")
            print(f"  plan.query_semantic: {plan.query_semantic}")
            print(f"  plan.preferred_doc_types: {plan.preferred_doc_types}")
        except Exception as e:
            print(f"  ERROR: {e}")

    # --- 7. Full retrieval ---
    print("\n--- 7. FULL RETRIEVAL PIPELINE ---")
    try:
        from app.services.retrieval import RetrievalService

        svc = RetrievalService()
        if spec is None and args.normalize:
            spec = await normalize(query, conversation_history=conv)
        pack = await svc.retrieve(query=query, query_spec=spec)
        stats = pack.retrieval_stats or {}
        print(f"  bm25_count: {stats.get('bm25_count', 0)}")
        print(f"  vector_count: {stats.get('vector_count', 0)}")
        print(f"  merged_count: {stats.get('merged_count', 0)}")
        print(f"  Final chunks: {len(pack.chunks)}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("ROOT CAUSE CHECKLIST:")
    print("  - OpenSearch/Qdrant down? -> Check step 1, 2")
    print("  - Index/collection empty? -> Run ingestion (scripts/ingest_*.py)")
    print("  - doc_type filter too strict? -> Compare step 3 vs 4 (raw vs filtered)")
    print("  - page_kind filter returns 0? -> Step 4c. Fix: Settings > Archi v3 > Page kind filter = OFF")
    print("    or re-ingest with page_kind metadata (reingest_all.py)")
    print("  - Query doesn't match? -> Try 'RDP', 'remote desktop', 'troubleshoot'")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug retrieval returning 0 chunks")
    parser.add_argument("--query", type=str, default="my rdp")
    parser.add_argument("--normalize", action="store_true", help="Run normalizer for plan")
    parser.add_argument("--with-context", action="store_true", help="Include conversation context")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
