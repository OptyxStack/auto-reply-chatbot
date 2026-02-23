"""Fetch and extract content from URLs for document ingestion."""

import re
from html import unescape

import httpx
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger(__name__)


def _clean_html(html: str) -> str:
    """Strip boilerplate and extract text from HTML."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract page title from HTML."""
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return "Untitled"


def fetch_content_from_url(url: str, timeout: float = 15.0) -> dict:
    """
    Fetch webpage and extract title + content.
    Returns {"title": str, "content": str, "raw_html": str} or raises.
    """
    if not url or not url.strip():
        raise ValueError("URL is required")
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SupportAI-Bot/1.0; +https://github.com/support-ai)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    content = _clean_html(html)

    if len(content) < 50:
        logger.warning("url_fetch_minimal_content", url=url, content_length=len(content))

    return {
        "title": title,
        "content": content,
        "raw_html": html,
    }
