"""Tests for retrieval merge and planner-driven execution."""

import pytest

from app.search.base import SearchChunk
from app.services.retrieval import RetrievalService
from app.services.schemas import QuerySpec, RetrievalPlan


def test_merge_simple_by_chunk_id():
    """Simple merge: dedupe by chunk_id, prefer higher score."""
    svc = RetrievalService()
    bm25 = [
        SearchChunk("c1", "d1", "text1", "url1", "policy", 0.8),
        SearchChunk("c2", "d1", "text2", "url1", "policy", 0.6),
    ]
    vector = [
        SearchChunk("c1", "d1", "text1", "url1", "policy", 0.95),  # duplicate, higher score
        SearchChunk("c3", "d2", "text3", "url2", "faq", 0.7),
    ]
    merged = svc._merge_simple(bm25, vector)
    assert len(merged) == 3  # c1, c2, c3
    c1 = next(m for m in merged if m.chunk_id == "c1")
    assert c1.score == 0.95  # prefer higher score


def test_merge_with_rrf():
    """RRF merge: chunks appearing in both lists rank higher."""
    svc = RetrievalService()
    bm25 = [
        SearchChunk("c1", "d1", "text1", "url1", "policy", 0.8),
        SearchChunk("c2", "d1", "text2", "url1", "policy", 0.6),
    ]
    vector = [
        SearchChunk("c1", "d1", "text1", "url1", "policy", 0.95),
        SearchChunk("c3", "d2", "text3", "url2", "faq", 0.7),
    ]
    merged = svc._merge_with_rrf(bm25, vector, k=60)
    assert len(merged) == 3
    # c1 appears in both: RRF = 1/61 + 1/61 > c2 (1/62) or c3 (1/62)
    assert merged[0].chunk_id == "c1"
    assert merged[0].score > merged[1].score


@pytest.mark.asyncio
async def test_retrieve_uses_plan_budget_hint_as_authoritative(monkeypatch):
    class FakeOpenSearch:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def search(
            self,
            query: str,
            *,
            top_n: int = 50,
            doc_types: list[str] | None = None,
            boost_pricing: bool = False,
            prefer_snippet: bool = False,
        ) -> list[SearchChunk]:
            self.calls.append(
                {
                    "query": query,
                    "top_n": top_n,
                    "doc_types": list(doc_types or []),
                    "boost_pricing": boost_pricing,
                    "prefer_snippet": prefer_snippet,
                }
            )
            return [
                SearchChunk(
                    "bm25-1",
                    "d1",
                    "Refund policy allows cancellation in 7 days.",
                    "https://docs/policy",
                    "policy",
                    0.9,
                )
            ]

    class FakeQdrant:
        def search(
            self,
            *,
            vector: list[float],
            top_n: int = 50,
            doc_types: list[str] | None = None,
        ) -> list[SearchChunk]:
            _ = (vector, top_n, doc_types)
            return [
                SearchChunk(
                    "vec-1",
                    "d2",
                    "Policy details include refund windows and terms.",
                    "https://docs/policy-2",
                    "policy",
                    0.8,
                )
            ]

    class FakeEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            _ = texts
            return [[0.1, 0.2, 0.3]]

    class FakeReranker:
        async def rerank(self, query: str, chunks: list[SearchChunk], top_k: int):
            _ = query
            ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
            return [(c, c.score) for c in ranked[:top_k]]

    opensearch = FakeOpenSearch()
    svc = RetrievalService(
        opensearch=opensearch,
        qdrant=FakeQdrant(),
        embedding_provider=FakeEmbedder(),
        reranker=FakeReranker(),
    )
    monkeypatch.setattr(
        svc,
        "_settings",
        type(
            "S",
            (),
            {
                "retrieval_top_n": 50,
                "retrieval_top_k": 8,
                "retrieval_fusion": "simple",
                "retrieval_rrf_k": 60,
                "retrieval_plans_extra_chunks": 4,
                "retrieval_ensure_doc_type_min": 0,
                "evidence_selector_use_llm": False,
                "evidence_selector_fallback_top_k": 8,
            },
        )(),
    )

    spec = QuerySpec(
        intent="policy",
        entities=[],
        constraints={},
        required_evidence=["policy_language"],
        risk_level="high",
        keyword_queries=["fallback query from spec"],
        semantic_queries=["fallback query from spec"],
        clarifying_questions=[],
        is_ambiguous=False,
        hard_requirements=["different_requirement"],
        retrieval_profile="policy_profile",
        doc_type_prior=["faq"],
    )
    plan = RetrievalPlan(
        profile="policy_profile",
        attempt_index=1,
        reason="test_plan",
        query_keyword="refund cancellation policy",
        query_semantic="refund cancellation policy",
        preferred_doc_types=["policy"],
        fetch_n=11,
        rerank_k=2,
        budget_hint={
            "hard_requirements": ["policy_language"],
            "ensure_doc_types": ["policy"],
            "boost_pricing": False,
        },
    )

    pack = await svc.retrieve(
        "original query",
        query_spec=spec,
        retrieval_plan=plan,
    )

    assert pack.retrieval_stats["query_rewrite"]["keyword_query"] == "refund cancellation policy"
    assert pack.retrieval_stats["hard_requirements"] == ["policy_language"]
    assert opensearch.calls[0]["top_n"] == 11
    assert opensearch.calls[0]["doc_types"] == ["policy"]


@pytest.mark.asyncio
async def test_retrieve_fetches_conversation_as_secondary_source(monkeypatch):
    class FakeOpenSearch:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def search(self, query: str, *, top_n: int = 50, doc_types=None, boost_pricing=False, prefer_snippet=False):
            self.calls.append({"query": query, "doc_types": list(doc_types or []), "top_n": top_n})
            if doc_types == ["conversation"]:
                return [
                    SearchChunk("conv-1", "d2", "Customer bought extra IP for VPS via support.", "ticket://1", "conversation", 0.7),
                ]
            return [
                SearchChunk("price-1", "d1", "VPS plan starts at $10/month.", "https://docs/pricing", "pricing", 0.9),
            ]

    class FakeQdrant:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def search(self, *, vector, top_n: int = 50, doc_types=None):
            self.calls.append({"doc_types": list(doc_types or []), "top_n": top_n})
            if doc_types == ["conversation"]:
                return [
                    SearchChunk("conv-vec-1", "d3", "Extra IP can be added after order.", "ticket://2", "conversation", 0.65),
                ]
            return [
                SearchChunk("price-vec-1", "d4", "Monthly VPS pricing details.", "https://docs/pricing-2", "pricing", 0.8),
            ]

    class FakeEmbedder:
        async def embed(self, texts):
            _ = texts
            return [[0.1, 0.2]]

    class FakeReranker:
        async def rerank(self, query, chunks, top_k):
            _ = query
            ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
            return [(c, c.score) for c in ranked[:top_k]]

    svc = RetrievalService(
        opensearch=FakeOpenSearch(),
        qdrant=FakeQdrant(),
        embedding_provider=FakeEmbedder(),
        reranker=FakeReranker(),
    )
    monkeypatch.setattr(
        svc,
        "_settings",
        type(
            "S",
            (),
            {
                "retrieval_top_n": 20,
                "retrieval_top_k": 4,
                "retrieval_fusion": "simple",
                "retrieval_rrf_k": 60,
                "retrieval_plans_extra_chunks": 4,
                "retrieval_ensure_doc_type_min": 0,
                "evidence_selector_use_llm": False,
                "evidence_selector_fallback_top_k": 4,
            },
        )(),
    )

    plan = RetrievalPlan(
        profile="pricing_profile",
        attempt_index=1,
        reason="test_plan",
        query_keyword="buy more ip for my vps",
        query_semantic="buy more ip for my vps",
        active_hypothesis_name="primary",
        preferred_doc_types=["pricing"],
        preferred_sources=["conversation"],
        authoritative_doc_types=["pricing"],
        supporting_doc_types=["conversation"],
        active_required_evidence=["numbers_units"],
        fetch_n=10,
        rerank_k=4,
        budget_hint={"ensure_doc_types": ["pricing"], "preferred_sources": ["conversation"], "hard_requirements": []},
    )

    pack = await svc.retrieve("buy more ip", retrieval_plan=plan)

    assert pack.retrieval_stats["primary_doc_types"] == ["pricing"]
    assert pack.retrieval_stats["preferred_sources"] == ["conversation"]
    assert pack.retrieval_stats["supporting_bm25_count"] == 1
    assert any(chunk.doc_type == "conversation" for chunk in pack.chunks)


@pytest.mark.asyncio
async def test_retrieve_fans_out_diversity_doc_types(monkeypatch):
    class FakeOpenSearch:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def search(self, query: str, *, top_n: int = 50, doc_types=None, boost_pricing=False, prefer_snippet=False):
            _ = (query, boost_pricing, prefer_snippet)
            doc_types = list(doc_types or [])
            self.calls.append({"doc_types": doc_types, "top_n": top_n})
            if doc_types == ["howto"]:
                return [SearchChunk("how-1", "d2", "Step 1: open console", "https://docs/howto", "howto", 0.62)]
            if doc_types == ["docs"]:
                return [SearchChunk("doc-1", "d3", "Docs explain options", "https://docs/main", "docs", 0.6)]
            if doc_types == ["faq"]:
                return [SearchChunk("faq-1", "d4", "FAQ about common setup", "https://docs/faq", "faq", 0.58)]
            return [SearchChunk("price-1", "d1", "Base plan starts at $10", "https://docs/pricing", "pricing", 0.9)]

    class FakeQdrant:
        def search(self, *, vector, top_n: int = 50, doc_types=None):
            _ = (vector, top_n, doc_types)
            return []

    class FakeEmbedder:
        async def embed(self, texts):
            _ = texts
            return [[0.1, 0.2]]

    class FakeReranker:
        async def rerank(self, query, chunks, top_k):
            _ = query
            ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
            return [(c, c.score) for c in ranked[:top_k]]

    opensearch = FakeOpenSearch()
    svc = RetrievalService(
        opensearch=opensearch,
        qdrant=FakeQdrant(),
        embedding_provider=FakeEmbedder(),
        reranker=FakeReranker(),
    )
    monkeypatch.setattr(
        svc,
        "_settings",
        type(
            "S",
            (),
            {
                "retrieval_top_n": 20,
                "retrieval_top_k": 6,
                "retrieval_fusion": "simple",
                "retrieval_rrf_k": 60,
                "retrieval_plans_extra_chunks": 4,
                "retrieval_ensure_doc_type_min": 0,
                "retrieval_conversation_score_penalty": 0.55,
                "evidence_selector_use_llm": False,
                "evidence_selector_fallback_top_k": 6,
            },
        )(),
    )

    plan = RetrievalPlan(
        profile="generic_profile",
        attempt_index=1,
        reason="test_plan",
        query_keyword="how to configure service",
        query_semantic="how to configure service",
        preferred_doc_types=["pricing"],
        authoritative_doc_types=["pricing"],
        fetch_n=8,
        rerank_k=5,
        budget_hint={
            "boost_pricing": False,
            "ensure_doc_types": ["pricing"],
            "hard_requirements": [],
            "diversity_doc_types": ["howto", "docs", "faq"],
            "diversity_fetch_per_type": 2,
        },
    )

    pack = await svc.retrieve("configure service", retrieval_plan=plan)

    called_doc_types = [call["doc_types"] for call in opensearch.calls]
    assert ["howto"] in called_doc_types
    assert ["docs"] in called_doc_types
    assert ["faq"] in called_doc_types
    assert pack.retrieval_stats["diversity_doc_types"] == ["howto", "docs", "faq"]
    covered = set(pack.retrieval_stats.get("diversity_doc_types_covered") or [])
    assert {"howto", "docs", "faq"} <= covered


def test_retain_supporting_conversation_chunk_preserves_one_when_selector_drops_it():
    selected = [
        (SearchChunk("p1", "d1", "pricing", "https://docs/pricing", "pricing", 0.9), 0.9),
        (SearchChunk("f1", "d2", "faq", "https://docs/faq", "faq", 0.6), 0.6),
    ]
    candidates = selected + [
        (SearchChunk("c1", "d3", "conversation", "ticket://1", "conversation", 0.7), 0.7),
    ]

    updated = RetrievalService._retain_supporting_conversation_chunk(
        selected,
        candidates,
        max_items=2,
    )

    assert len(updated) == 2
    assert any(chunk.doc_type == "conversation" for chunk, _ in updated)


@pytest.mark.asyncio
async def test_retrieve_passes_page_kind_and_product_family_hints(monkeypatch):
    monkeypatch.setattr(
        "app.services.archi_config.get_page_kind_filter_enabled",
        lambda: True,
    )

    class FakeOpenSearch:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def search(
            self,
            query: str,
            *,
            top_n: int = 50,
            doc_types=None,
            boost_pricing=False,
            prefer_snippet=False,
            page_kinds=None,
            product_families=None,
            page_kind_weights=None,
            product_family_weights=None,
        ):
            _ = (query, boost_pricing, prefer_snippet)
            self.calls.append(
                {
                    "doc_types": list(doc_types or []),
                    "page_kinds": list(page_kinds or []),
                    "product_families": list(product_families or []),
                    "page_kind_weights": dict(page_kind_weights or {}),
                    "product_family_weights": dict(product_family_weights or {}),
                }
            )
            return [
                SearchChunk(
                    "bm25-1",
                    "d1",
                    "Windows VPS order page",
                    "https://example.com/order/windows-vps",
                    "pricing",
                    0.9,
                    metadata={"page_kind": "order_page", "product_family": "windows_vps"},
                )
            ]

    class FakeQdrant:
        def search(self, *, vector, top_n=50, doc_types=None, page_kinds=None, product_families=None):
            _ = (vector, top_n, doc_types, page_kinds, product_families)
            return []

    class FakeEmbedder:
        async def embed(self, texts):
            _ = texts
            return [[0.1, 0.2]]

    class FakeReranker:
        async def rerank(self, query, chunks, top_k):
            _ = query
            ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
            return [(c, c.score) for c in ranked[:top_k]]

    opensearch = FakeOpenSearch()
    svc = RetrievalService(
        opensearch=opensearch,
        qdrant=FakeQdrant(),
        embedding_provider=FakeEmbedder(),
        reranker=FakeReranker(),
    )
    monkeypatch.setattr(
        svc,
        "_settings",
        type(
            "S",
            (),
            {
                "retrieval_top_n": 20,
                "retrieval_top_k": 4,
                "retrieval_fusion": "simple",
                "retrieval_rrf_k": 60,
                "retrieval_plans_extra_chunks": 4,
                "retrieval_ensure_doc_type_min": 0,
                "retrieval_conversation_score_penalty": 0.55,
                "retrieval_page_kind_weighting_enabled": True,
                "evidence_selector_use_llm": False,
                "evidence_selector_fallback_top_k": 4,
            },
        )(),
    )

    plan = RetrievalPlan(
        profile="pricing_profile",
        attempt_index=1,
        reason="test_plan",
        query_keyword="windows vps order link",
        query_semantic="windows vps order link",
        preferred_doc_types=["pricing", "docs"],
        authoritative_doc_types=["pricing", "docs"],
        fetch_n=8,
        rerank_k=4,
        budget_hint={
            "preferred_page_kinds": ["order_page", "product_page"],
            "supporting_page_kinds": ["pricing_table"],
            "page_kind_weights": {"order_page": 1.45, "product_page": 1.25},
            "product_family_hints": ["windows_vps"],
            "product_family_weights": {"windows_vps": 1.2},
            "demote_doc_types": ["faq", "blog"],
        },
    )

    pack = await svc.retrieve("windows vps order link", retrieval_plan=plan)

    assert pack.chunks
    assert opensearch.calls
    first_call = opensearch.calls[0]
    assert "order_page" in first_call["page_kinds"]
    assert "windows_vps" in first_call["product_families"]
    assert first_call["page_kind_weights"].get("order_page") == pytest.approx(1.45)


@pytest.mark.asyncio
async def test_retrieve_keeps_product_family_hints_when_page_kind_flag_off(monkeypatch):
    class FakeOpenSearch:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def search(
            self,
            query: str,
            *,
            top_n: int = 50,
            doc_types=None,
            boost_pricing=False,
            prefer_snippet=False,
            page_kinds=None,
            product_families=None,
            page_kind_weights=None,
            product_family_weights=None,
        ):
            _ = (query, boost_pricing, prefer_snippet)
            self.calls.append(
                {
                    "page_kinds": list(page_kinds or []),
                    "product_families": list(product_families or []),
                    "page_kind_weights": dict(page_kind_weights or {}),
                    "product_family_weights": dict(product_family_weights or {}),
                }
            )
            return [
                SearchChunk(
                    "bm25-1",
                    "d1",
                    "Windows VPS order page",
                    "https://example.com/order/windows-vps",
                    "pricing",
                    0.9,
                    metadata={"page_kind": "order_page", "product_family": "windows_vps"},
                )
            ]

    class FakeQdrant:
        def search(self, *, vector, top_n=50, doc_types=None, page_kinds=None, product_families=None):
            _ = (vector, top_n, doc_types, page_kinds, product_families)
            return []

    class FakeEmbedder:
        async def embed(self, texts):
            _ = texts
            return [[0.1, 0.2]]

    class FakeReranker:
        async def rerank(self, query, chunks, top_k):
            _ = query
            ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
            return [(c, c.score) for c in ranked[:top_k]]

    opensearch = FakeOpenSearch()
    svc = RetrievalService(
        opensearch=opensearch,
        qdrant=FakeQdrant(),
        embedding_provider=FakeEmbedder(),
        reranker=FakeReranker(),
    )
    monkeypatch.setattr(
        svc,
        "_settings",
        type(
            "S",
            (),
            {
                "retrieval_top_n": 20,
                "retrieval_top_k": 4,
                "retrieval_fusion": "simple",
                "retrieval_rrf_k": 60,
                "retrieval_plans_extra_chunks": 4,
                "retrieval_ensure_doc_type_min": 0,
                "retrieval_conversation_score_penalty": 0.55,
                "retrieval_page_kind_weighting_enabled": True,
                "page_kind_filter_enabled": False,
                "evidence_selector_use_llm": False,
                "evidence_selector_fallback_top_k": 4,
            },
        )(),
    )

    plan = RetrievalPlan(
        profile="pricing_profile",
        attempt_index=1,
        reason="test_plan",
        query_keyword="windows vps order link",
        query_semantic="windows vps order link",
        preferred_doc_types=["pricing", "docs"],
        authoritative_doc_types=["pricing", "docs"],
        fetch_n=8,
        rerank_k=4,
        budget_hint={
            "preferred_page_kinds": ["order_page", "product_page"],
            "supporting_page_kinds": ["pricing_table"],
            "page_kind_weights": {"order_page": 1.45, "product_page": 1.25},
            "product_family_hints": ["windows_vps"],
            "product_family_weights": {"windows_vps": 1.2},
            "demote_doc_types": ["faq", "blog"],
        },
    )

    await svc.retrieve("windows vps order link", retrieval_plan=plan)

    first_call = opensearch.calls[0]
    assert first_call["page_kinds"] == []
    assert first_call["page_kind_weights"] == {}
    assert first_call["product_families"] == ["windows_vps"]
    assert first_call["product_family_weights"] == {"windows_vps": pytest.approx(1.2)}


@pytest.mark.asyncio
async def test_retrieve_relaxes_metadata_filters_when_search_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "app.services.archi_config.get_page_kind_filter_enabled",
        lambda: True,
    )

    class FakeOpenSearch:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def search(
            self,
            query: str,
            *,
            top_n: int = 50,
            doc_types=None,
            boost_pricing=False,
            prefer_snippet=False,
            page_kinds=None,
            product_families=None,
            page_kind_weights=None,
            product_family_weights=None,
        ):
            _ = (query, top_n, doc_types, boost_pricing, prefer_snippet, page_kind_weights, product_family_weights)
            self.calls.append(
                {
                    "page_kinds": list(page_kinds or []),
                    "product_families": list(product_families or []),
                }
            )
            if product_families:
                return []
            return [
                SearchChunk(
                    "bm25-1",
                    "d1",
                    "Windows VPS product page",
                    "https://example.com/windows-vps",
                    "docs",
                    0.8,
                    metadata={"page_kind": "product_page"},
                )
            ]

    class FakeQdrant:
        def search(self, *, vector, top_n=50, doc_types=None, page_kinds=None, product_families=None):
            _ = (vector, top_n, doc_types, page_kinds, product_families)
            return []

    class FakeEmbedder:
        async def embed(self, texts):
            _ = texts
            return [[0.1, 0.2]]

    class FakeReranker:
        async def rerank(self, query, chunks, top_k):
            _ = query
            ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
            return [(c, c.score) for c in ranked[:top_k]]

    opensearch = FakeOpenSearch()
    svc = RetrievalService(
        opensearch=opensearch,
        qdrant=FakeQdrant(),
        embedding_provider=FakeEmbedder(),
        reranker=FakeReranker(),
    )
    monkeypatch.setattr(
        svc,
        "_settings",
        type(
            "S",
            (),
            {
                "retrieval_top_n": 20,
                "retrieval_top_k": 4,
                "retrieval_fusion": "simple",
                "retrieval_rrf_k": 60,
                "retrieval_plans_extra_chunks": 4,
                "retrieval_ensure_doc_type_min": 0,
                "retrieval_conversation_score_penalty": 0.55,
                "retrieval_page_kind_weighting_enabled": True,
                "evidence_selector_use_llm": False,
                "evidence_selector_fallback_top_k": 4,
            },
        )(),
    )

    plan = RetrievalPlan(
        profile="generic_profile",
        attempt_index=1,
        reason="test_plan",
        query_keyword="windows vps singapore",
        query_semantic="windows vps singapore",
        preferred_doc_types=["pricing", "docs", "faq"],
        authoritative_doc_types=["pricing", "docs"],
        fetch_n=8,
        rerank_k=4,
        budget_hint={
            "preferred_page_kinds": ["product_page"],
            "supporting_page_kinds": ["pricing_table"],
            "page_kind_weights": {"product_page": 1.1},
            "product_family_hints": ["windows_vps"],
            "product_family_weights": {"windows_vps": 1.2},
        },
    )

    pack = await svc.retrieve("windows vps singapore", retrieval_plan=plan)

    assert pack.chunks
    assert len(opensearch.calls) >= 2
    assert opensearch.calls[0]["product_families"] == ["windows_vps"]
    assert opensearch.calls[1]["product_families"] == []
