"""Tests for source loader taxonomy enrichment."""

import json

from app.services.source_loaders import load_pages_json


def test_load_pages_json_enriches_page_kind_and_product_family(tmp_path):
    path = tmp_path / "pricing.json"
    payload = {
        "source": "unit_test",
        "doc_type": "pricing",
        "pages": [
            {
                "url": "https://example.com/order/windows-vps",
                "title": "Windows VPS Order",
                "text": "Buy Windows VPS instantly with monthly billing and immediate setup support included.",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    docs = load_pages_json(path)

    assert len(docs) == 1
    metadata = docs[0]["metadata"] or {}
    assert metadata.get("page_kind") == "order_page"
    assert metadata.get("product_family") == "windows_vps"
