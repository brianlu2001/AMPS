"""
Stage 3 — Profile Extractor.

Takes the raw text from the ingestion stage and extracts structured
buyer profile fields using deterministic heuristics.

Input:  IngestionResult + ParsedInstruction
Output: ExtractedProfile dataclass

Extraction strategy (all deterministic, no LLM):
  - organization:   keyword patterns, domain name fallback
  - display_name:   "I'm [Name]" from instruction, or organization
  - industry_hint:  keyword matching from a vocabulary list
  - preferred_categories: carry forward from instruction parser + text scan
  - use_case_summary: short constructed sentence from findings

Why deterministic for MVP:
  - Always works, no latency, no API key required.
  - Output is predictable and testable.
  - Makes it easy to diff mock vs. real LLM output when LLM is added.

Future: send (instruction + ingested_text) to an LLM with a structured
extraction prompt. The ExtractedProfile schema becomes the output schema.
Keep this module as the fallback if LLM extraction fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .ingestion import IngestionResult
from .instruction_parser import ParsedInstruction


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class ExtractedProfile:
    organization: Optional[str]
    display_name: Optional[str]
    industry_hint: Optional[str]
    preferred_categories: List[str]
    use_case_summary: Optional[str]
    extraction_source: str          # "http" | "mock" | "instruction_only"
    confidence: float               # 0.0–1.0; based on how much was found
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Vocabulary for heuristic extraction
# ---------------------------------------------------------------------------

_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "fintech / finance":    ["fintech", "finance", "investment", "capital", "banking", "fund", "wealth"],
    "legal / law":          ["law firm", "legal", "counsel", "attorney", "litigation", "compliance"],
    "consulting":           ["consulting", "advisory", "strategy", "management consulting"],
    "technology":           ["software", "saas", "platform", "developer", "data", "ai", "ml", "tech"],
    "healthcare":           ["health", "medical", "pharma", "biotech", "clinical"],
    "private equity / vc":  ["private equity", "venture capital", "portfolio", "deal flow", "pe firm"],
    "research":             ["research", "think tank", "institute", "academic", "university"],
}

_ORG_PATTERNS = [
    # Explicit mentions: "at Acme Corp", "from Acme Corp", "representing Acme"
    r"\b(?:at|from|representing|for|with)\s+([A-Z][A-Za-z0-9 &,.-]{2,40}?)(?:\.|,|\s+(?:and|who|that|which)|\Z)",
    # Job title patterns: "Head of X at OrgName"
    r"\bat\s+([A-Z][A-Za-z0-9 &,.-]{2,40})(?:\b|\.)",
    # "OrgName — ..." (LinkedIn-style title pattern)
    r"—\s*([A-Z][A-Za-z0-9 &,.-]{2,40})\b",
    # "Organization: OrgName"
    r"[Oo]rganization[:\s]+([A-Z][A-Za-z0-9 &,.-]{2,40})\b",
]

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "financial_research":         ["financial", "finance", "earnings", "accounting", "investment", "revenue"],
    "legal_analysis":             ["legal", "contract", "law", "compliance", "regulatory", "clause"],
    "market_intelligence":        ["market", "competitor", "industry", "landscape", "intelligence", "competitive"],
    "strategy_business_research": ["strategy", "strategic", "business", "gtm", "go-to-market", "procurement"],
}


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract_profile(
    ingestion: IngestionResult,
    instruction: ParsedInstruction,
) -> ExtractedProfile:
    """
    Extract structured profile fields from ingested content + parsed instruction.

    Never raises — failures reduce confidence and add notes instead.
    """
    notes: list[str] = []
    text = ingestion.raw_text or ""
    combined = f"{instruction.raw} {text}".strip()
    confidence = 0.5  # start at 0.5; improve as we find more signals

    # ------------------------------------------------------------------
    # 1. Organization
    # ------------------------------------------------------------------
    organization: Optional[str] = None

    # Try instruction name hint first (highest confidence)
    if instruction.name_hint:
        organization = instruction.name_hint
        confidence = min(confidence + 0.2, 1.0)
        notes.append(f"Organization from instruction hint: '{organization}'")

    # Try regex patterns on ingested text
    if not organization and text:
        for pattern in _ORG_PATTERNS:
            m = re.search(pattern, text)
            if m:
                candidate = m.group(1).strip().rstrip(".,")
                # Sanity: reject very short or all-lowercase candidates
                if len(candidate) >= 3 and any(c.isupper() for c in candidate):
                    organization = candidate
                    confidence = min(confidence + 0.15, 1.0)
                    notes.append(f"Organization from text pattern: '{organization}'")
                    break

    # Fallback: capitalize the domain name
    if not organization and ingestion.domain:
        organization = ingestion.domain.replace("-", " ").title()
        notes.append(f"Organization from domain fallback: '{organization}'")

    # ------------------------------------------------------------------
    # 2. Display name
    # ------------------------------------------------------------------
    display_name: Optional[str] = instruction.name_hint or organization

    # Try "Name — Title" LinkedIn-style extraction from text
    if not display_name or display_name == organization:
        m = re.search(r"^([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s+[—–-]", text)
        if m:
            display_name = m.group(1)
            notes.append(f"Display name from text: '{display_name}'")

    # ------------------------------------------------------------------
    # 3. Industry hint
    # ------------------------------------------------------------------
    industry_hint: Optional[str] = None
    combined_lower = combined.lower()
    for industry, keywords in _INDUSTRY_KEYWORDS.items():
        if any(kw in combined_lower for kw in keywords):
            industry_hint = industry
            confidence = min(confidence + 0.1, 1.0)
            notes.append(f"Industry detected: '{industry_hint}'")
            break

    # ------------------------------------------------------------------
    # 4. Preferred categories (merge instruction + text scan)
    # ------------------------------------------------------------------
    preferred: set[str] = set(instruction.preferred_categories)
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in combined_lower for kw in keywords):
            preferred.add(category)
    preferred_categories = sorted(preferred)
    if preferred_categories:
        confidence = min(confidence + 0.1, 1.0)

    # ------------------------------------------------------------------
    # 5. Use-case summary (constructed sentence)
    # ------------------------------------------------------------------
    use_case_summary: Optional[str] = None
    parts = []
    if organization:
        parts.append(f"{organization}")
    if industry_hint:
        parts.append(f"operating in {industry_hint}")
    if preferred_categories:
        readable = [c.replace("_", " ") for c in preferred_categories]
        parts.append(f"seeking {', '.join(readable)}")
    if parts:
        use_case_summary = " — ".join(parts) + "."
    else:
        use_case_summary = "Buyer agent enrolled from provided context."

    # ------------------------------------------------------------------
    # 6. Penalize if content came only from instruction (less signal)
    # ------------------------------------------------------------------
    source = ingestion.provider_used
    if not text or len(text.split()) < 10:
        confidence = max(confidence - 0.2, 0.2)
        notes.append("Low content signal — confidence reduced")
        source = "instruction_only"

    return ExtractedProfile(
        organization=organization,
        display_name=display_name,
        industry_hint=industry_hint,
        preferred_categories=preferred_categories,
        use_case_summary=use_case_summary,
        extraction_source=source,
        confidence=round(confidence, 2),
        notes=notes,
    )
