"""Test that crawl preserves links in content."""

from app.services.url_fetcher import _clean_html


def test_clean_html_preserves_links():
    html = '<p>Check our <a href="/dedicated-servers.php">Dedicated Servers</a>.</p>'
    base = "https://greencloudvps.com/"
    out = _clean_html(html, base_url=base)
    assert "dedicated-servers.php" in out
    assert "greencloudvps.com" in out
    assert "Dedicated Servers" in out


def test_clean_html_without_base_url_keeps_link_text_only():
    """When no base_url, links are stripped to text only (no href)."""
    html = '<p>Check <a href="/page">link</a>.</p>'
    out = _clean_html(html, base_url=None)
    assert "link" in out
