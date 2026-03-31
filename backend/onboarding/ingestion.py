"""
Stage 2 — Link Ingestion.

Fetches and normalizes the content of a URL for downstream profile extraction.

Architecture: a clean Provider interface with two implementations:
  - HttpIngestionProvider   — real HTTP fetch using httpx (in requirements.txt)
  - MockIngestionProvider   — deterministic mock for testing and cold-start demo

The active provider is selected by IngestionProviderFactory based on
INGESTION_PROVIDER env var ("http" | "mock"). Default: "http" with
graceful fallback to mock on error.

This separation means:
  - Unit tests never make network calls.
  - The route handler never knows which provider ran.
  - Swapping to a headless-browser or LLM-powered fetcher = add a new provider class.

IngestionResult fields:
  url           : the URL that was requested
  raw_text      : best-effort plain text extracted from the page
  title         : <title> tag or inferred heading
  domain        : domain name (e.g. "acme")
  status        : "ok" | "fetch_error" | "parse_error" | "mock"
  error         : error message if status != "ok"
  provider_used : "http" | "mock"
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class IngestionResult:
    url: str
    raw_text: str                           # Plain text content (may be empty on error)
    title: Optional[str] = None
    domain: Optional[str] = None
    status: str = "ok"                      # "ok" | "fetch_error" | "parse_error" | "mock"
    error: Optional[str] = None
    provider_used: str = "unknown"
    word_count: int = 0

    def is_ok(self) -> bool:
        return self.status in ("ok", "mock")

    def summary_line(self) -> str:
        if self.is_ok():
            return f"[{self.provider_used}] '{self.title or self.domain}' — {self.word_count} words"
        return f"[{self.provider_used}] ERROR: {self.error}"


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------

class BaseIngestionProvider(ABC):
    @abstractmethod
    def fetch(self, url: str) -> IngestionResult:
        """Fetch and return normalized text content from url."""
        ...


# ---------------------------------------------------------------------------
# Provider 1: Real HTTP fetch (httpx)
# ---------------------------------------------------------------------------

class HttpIngestionProvider(BaseIngestionProvider):
    """
    Fetches a URL over HTTP and extracts readable text.

    Text extraction is intentionally simple:
      - Strip HTML tags via regex (no BeautifulSoup dependency for MVP).
      - Collapse whitespace.
      - Truncate at MAX_CHARS to keep payloads bounded.

    Future: use BeautifulSoup or a headless browser for richer extraction.
    Future: add caching layer to avoid re-fetching the same URL.
    """

    MAX_CHARS = 8_000   # Enough context for profile extraction; avoid token bloat
    TIMEOUT   = 8.0     # seconds

    def fetch(self, url: str) -> IngestionResult:
        domain = _extract_domain(url)
        try:
            import httpx
        except ImportError:
            return IngestionResult(
                url=url, raw_text="", domain=domain,
                status="fetch_error",
                error="httpx not installed — run: pip install httpx",
                provider_used="http",
            )

        try:
            response = httpx.get(
                url,
                timeout=self.TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "AMPS-Onboarding-Bot/1.0"},
            )
            response.raise_for_status()
        except Exception as exc:
            return IngestionResult(
                url=url, raw_text="", domain=domain,
                status="fetch_error",
                error=str(exc)[:200],
                provider_used="http",
            )

        try:
            raw_text, title = _extract_text_from_html(response.text)
            raw_text = raw_text[: self.MAX_CHARS]
            return IngestionResult(
                url=url,
                raw_text=raw_text,
                title=title or domain,
                domain=domain,
                status="ok",
                provider_used="http",
                word_count=len(raw_text.split()),
            )
        except Exception as exc:
            return IngestionResult(
                url=url, raw_text="", domain=domain,
                status="parse_error",
                error=str(exc)[:200],
                provider_used="http",
            )


# ---------------------------------------------------------------------------
# Provider 2: Mock ingestion (for testing + demo)
# ---------------------------------------------------------------------------

# Realistic mock content keyed by rough domain patterns.
# Covers common demo scenarios without any network call.
_MOCK_CORPUS: dict[str, dict] = {
    "linkedin": {
        "title": "LinkedIn Profile",
        "text": (
            "Alice Johnson — Head of Procurement at Meridian Capital. "
            "Experienced in vendor management, contract negotiation, and financial due diligence. "
            "Looking for high-quality research and analysis services across financial and legal domains. "
            "Based in New York. 500+ connections."
        ),
    },
    "github": {
        "title": "GitHub Profile",
        "text": (
            "Developer profile. Works on data infrastructure and analytics tooling. "
            "Interested in market intelligence and strategy research services. "
            "Organization: OpenData Labs."
        ),
    },
    "crunchbase": {
        "title": "Crunchbase Company Profile",
        "text": (
            "Meridian Capital — Series B fintech company. Founded 2018. "
            "Focus: AI-powered investment analytics. 45 employees. "
            "Looking for financial research, market intelligence, and legal analysis services."
        ),
    },
    "notion": {
        "title": "Notion Brief",
        "text": (
            "Research brief: We need quarterly market intelligence reports and financial analysis. "
            "Preferred output: structured summaries and bullet-point risk flags. "
            "Organization: Apex Strategy Group."
        ),
    },
    "docs.google": {
        "title": "Google Doc Brief",
        "text": (
            "Procurement brief for research services. "
            "Required: financial research, legal contract review. "
            "Preferred vendors with high accuracy and fast turnaround."
        ),
    },
    "default": {
        "title": "Web Page",
        "text": (
            "Organization profile page. "
            "Interested in professional research and analysis services. "
            "Seeking: financial research, legal analysis, market intelligence."
        ),
    },
}


class MockIngestionProvider(BaseIngestionProvider):
    """
    Returns deterministic mock content based on the URL domain.

    Used when INGESTION_PROVIDER=mock or when the HTTP provider fails.
    Content is realistic enough for the profile extractor to produce
    meaningful results.
    """

    def fetch(self, url: str) -> IngestionResult:
        domain = _extract_domain(url)
        corpus_key = "default"
        for key in _MOCK_CORPUS:
            if key in (domain or ""):
                corpus_key = key
                break

        entry = _MOCK_CORPUS[corpus_key]
        text = entry["text"]
        return IngestionResult(
            url=url,
            raw_text=text,
            title=entry["title"],
            domain=domain,
            status="mock",
            provider_used="mock",
            word_count=len(text.split()),
        )


# ---------------------------------------------------------------------------
# Factory — select provider from env
# ---------------------------------------------------------------------------

class IngestionProviderFactory:
    """
    Returns the appropriate ingestion provider.

    INGESTION_PROVIDER env var:
      "http"  → HttpIngestionProvider (default)
      "mock"  → MockIngestionProvider

    If http provider returns an error and INGESTION_FALLBACK_TO_MOCK=true,
    the factory will retry with the mock provider automatically.
    """

    @staticmethod
    def get() -> BaseIngestionProvider:
        provider_name = os.getenv("INGESTION_PROVIDER", "http").lower()
        if provider_name == "mock":
            return MockIngestionProvider()
        return HttpIngestionProvider()

    @staticmethod
    def fetch_with_fallback(url: str) -> IngestionResult:
        """
        Attempt HTTP fetch; fall back to mock if it fails and fallback is enabled.

        This is the recommended call site for production routes.
        """
        fallback_enabled = os.getenv("INGESTION_FALLBACK_TO_MOCK", "true").lower() == "true"
        provider = IngestionProviderFactory.get()
        result = provider.fetch(url)

        if not result.is_ok() and fallback_enabled and provider.provider_used != "mock":  # type: ignore[attr-defined]
            mock_result = MockIngestionProvider().fetch(url)
            mock_result.error = f"HTTP failed ({result.error}); using mock content"
            mock_result.status = "mock"
            return mock_result

        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().replace("www.", "")
        return netloc.split(".")[0] if netloc else None
    except Exception:
        return None


def _extract_text_from_html(html: str) -> tuple[str, Optional[str]]:
    """
    Minimal HTML → plain text conversion.
    Returns (text, title).

    Future: replace with BeautifulSoup or Trafilatura for better fidelity.
    """
    # Extract <title>
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else None

    # Remove script and style blocks entirely
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    # Remove all remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                          ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")]:
        html = html.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", html).strip()
    return text, title
