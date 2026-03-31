"""
Stage 1 — Instruction Parser.

Parses a buyer's natural-language onboarding instruction and extracts:
  - the intent (enroll, update profile, re-enroll)
  - any URL mentioned inline (if not provided separately)
  - the buyer's display name or organization hint if stated
  - preferred task categories if mentioned

Input:  raw string, e.g. "Read this link and enroll me as a buyer agent."
Output: ParsedInstruction dataclass

This stage is intentionally deterministic (no LLM) so it always works
and is testable without any external calls.

Future: pass ParsedInstruction to an LLM for richer intent understanding,
disambiguation, and multi-step clarification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------

_ENROLL_KEYWORDS = {
    "enroll", "register", "sign up", "sign me up", "onboard",
    "add me", "create", "setup", "set up", "join",
}
_UPDATE_KEYWORDS = {"update", "change", "edit", "modify", "refresh"}
_RE_ENROLL_KEYWORDS = {"re-enroll", "re-register", "redo", "reset"}

# Category keywords map — detect if buyer mentions a category preference
_CATEGORY_KEYWORDS = {
    "financial_research":          ["financial", "finance", "earnings", "accounting", "investment"],
    "legal_analysis":              ["legal", "contract", "law", "compliance", "regulatory"],
    "market_intelligence":         ["market", "competitor", "industry", "landscape", "intelligence"],
    "strategy_business_research":  ["strategy", "strategic", "business", "gtm", "go-to-market"],
}

# URL pattern — extract any https?:// URL embedded in the instruction
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class ParsedInstruction:
    raw: str                                # Original text unchanged
    intent: str                             # "enroll" | "update" | "re-enroll" | "unknown"
    url_in_text: Optional[str] = None       # URL extracted from instruction text (if any)
    name_hint: Optional[str] = None         # Name/org extracted from "I'm from X" patterns
    preferred_categories: List[str] = field(default_factory=list)
    confidence: float = 1.0                 # Parsing confidence; drops if intent is ambiguous
    notes: List[str] = field(default_factory=list)  # Human-readable parser notes


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_instruction(raw: str) -> ParsedInstruction:
    """
    Parse a buyer's free-text onboarding instruction.

    Rules:
      1. Lowercased keyword scan for intent.
      2. Regex scan for inline URLs.
      3. Name/org hint extraction from "I'm [NAME]" or "from [ORG]" patterns.
      4. Category preference detection.

    Returns a ParsedInstruction with all findings.
    Does not raise — failures are recorded in notes and confidence is reduced.
    """
    if not raw or not raw.strip():
        return ParsedInstruction(
            raw=raw,
            intent="unknown",
            confidence=0.0,
            notes=["Empty instruction provided"],
        )

    text = raw.strip()
    lower = text.lower()
    notes: list[str] = []

    # --- 1. Intent detection ---
    intent = "unknown"
    if any(kw in lower for kw in _RE_ENROLL_KEYWORDS):
        intent = "re-enroll"
    elif any(kw in lower for kw in _UPDATE_KEYWORDS):
        intent = "update"
    elif any(kw in lower for kw in _ENROLL_KEYWORDS):
        intent = "enroll"
    else:
        notes.append("No clear enrollment intent detected; defaulting to 'enroll'")
        intent = "enroll"   # Assume enroll by default — most common action
        confidence_penalty = 0.2
    confidence = 1.0 - (0.2 if intent == "unknown" else 0.0)

    # --- 2. Inline URL extraction ---
    url_matches = _URL_PATTERN.findall(text)
    url_in_text = url_matches[0] if url_matches else None
    if url_in_text:
        notes.append(f"URL extracted from instruction text: {url_in_text}")
    if len(url_matches) > 1:
        notes.append(f"Multiple URLs found; using first: {url_in_text}")

    # --- 3. Name / org hint extraction ---
    name_hint = None
    # Pattern: "I'm [Name]" / "I am [Name]"
    m = re.search(r"\bi(?:'m| am)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)*)", text)
    if m:
        name_hint = m.group(1)
        notes.append(f"Name hint extracted: '{name_hint}'")
    else:
        # Pattern: "from [Org]" / "at [Org]"
        m2 = re.search(r"\b(?:from|at)\s+([A-Z][A-Za-z0-9 &,.-]{2,40})", text)
        if m2:
            name_hint = m2.group(1).strip()
            notes.append(f"Org hint extracted: '{name_hint}'")

    # --- 4. Category preferences ---
    preferred: list[str] = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            preferred.append(category)
    if preferred:
        notes.append(f"Category preferences detected: {preferred}")

    return ParsedInstruction(
        raw=raw,
        intent=intent,
        url_in_text=url_in_text,
        name_hint=name_hint,
        preferred_categories=preferred,
        confidence=confidence,
        notes=notes,
    )
