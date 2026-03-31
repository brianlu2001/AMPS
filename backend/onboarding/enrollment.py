"""
Stage 4 — Enrollment Orchestrator.

Coordinates all onboarding pipeline stages:
  1. instruction_parser  → ParsedInstruction
  2. ingestion           → IngestionResult
  3. profile_extractor   → ExtractedProfile
  4. enrollment          → BuyerProfile persisted in store + ActivityLog emitted

Entry point:
  run_onboarding(instruction, url, user_id, store) -> OnboardingResult

OnboardingResult is the API response shape — human-readable, demo-friendly,
contains both the created BuyerProfile and a full trace of what each stage did.

Error handling:
  - Each stage is wrapped; failures populate OnboardingResult.error and
    set success=False without raising to the caller.
  - Partial success is possible: if URL fetch fails but instruction provided
    enough signal, enrollment can still proceed at lower confidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.user import BuyerProfile
from .ingestion import IngestionProviderFactory, IngestionResult
from .instruction_parser import ParsedInstruction, parse_instruction
from .profile_extractor import ExtractedProfile, extract_profile


# ---------------------------------------------------------------------------
# OnboardingResult — the API response and log payload
# ---------------------------------------------------------------------------

@dataclass
class OnboardingResult:
    """
    Complete record of a buyer onboarding attempt.
    Returned by run_onboarding() and serialized directly as the API response.
    """
    success: bool
    profile: Optional[BuyerProfile]         # None if enrollment failed entirely

    # Per-stage outputs (always present for observability)
    parsed_instruction: Optional[Dict[str, Any]] = None
    ingestion_summary: Optional[Dict[str, Any]] = None
    extracted_fields: Optional[Dict[str, Any]] = None

    # Human-readable outcome
    message: str = ""
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "confidence": self.confidence,
            "profile": self.profile.dict() if self.profile else None,
            "pipeline_trace": {
                "instruction_parsing": self.parsed_instruction,
                "link_ingestion": self.ingestion_summary,
                "profile_extraction": self.extracted_fields,
            },
            "warnings": self.warnings,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class OnboardingValidationError(ValueError):
    pass


def validate_onboarding_input(instruction: str, url: Optional[str]) -> None:
    """
    Raise OnboardingValidationError with a clear message if inputs are invalid.

    Rules:
      - instruction must be provided and at least 5 characters
      - URL, if provided, must start with http:// or https://
    """
    if not instruction or len(instruction.strip()) < 5:
        raise OnboardingValidationError(
            "Instruction is required and must be at least 5 characters. "
            "Example: 'Read this link and enroll me as a buyer agent.'"
        )
    if url is not None:
        url = url.strip()
        if url and not url.lower().startswith(("http://", "https://")):
            raise OnboardingValidationError(
                f"Invalid URL '{url}'. URLs must start with http:// or https://"
            )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_onboarding(
    instruction: str,
    url: Optional[str],
    user_id: str,
    store: Any,                             # InMemoryStore (avoid circular import)
) -> OnboardingResult:
    """
    Run the full buyer onboarding pipeline.

    Args:
        instruction : buyer's natural-language instruction
        url         : optional context URL (may also be embedded in instruction)
        user_id     : the authenticated User.id to associate with the profile
        store       : the InMemoryStore instance

    Returns:
        OnboardingResult with full pipeline trace and the created BuyerProfile.

    Never raises — all exceptions are caught and returned as OnboardingResult.error.
    """
    warnings: list[str] = []

    # ------------------------------------------------------------------
    # Pre-flight validation
    # ------------------------------------------------------------------
    try:
        validate_onboarding_input(instruction, url)
    except OnboardingValidationError as exc:
        return OnboardingResult(
            success=False,
            profile=None,
            error=str(exc),
            message="Onboarding failed: invalid input.",
        )

    # ------------------------------------------------------------------
    # Stage 1: Parse instruction
    # ------------------------------------------------------------------
    try:
        parsed: ParsedInstruction = parse_instruction(instruction)
    except Exception as exc:
        return OnboardingResult(
            success=False, profile=None,
            error=f"Instruction parsing failed: {exc}",
            message="Onboarding failed at instruction parsing stage.",
        )

    # Merge URL from instruction text if not provided separately
    effective_url = url or parsed.url_in_text
    if not url and parsed.url_in_text:
        warnings.append(f"URL extracted from instruction text: {parsed.url_in_text}")

    # ------------------------------------------------------------------
    # Stage 2: URL ingestion
    # ------------------------------------------------------------------
    ingestion: Optional[IngestionResult] = None
    if effective_url:
        try:
            ingestion = IngestionProviderFactory.fetch_with_fallback(effective_url)
            if not ingestion.is_ok():
                warnings.append(
                    f"URL ingestion issue: {ingestion.error or ingestion.status}. "
                    "Profile built from instruction only."
                )
        except Exception as exc:
            warnings.append(f"URL ingestion exception: {exc}. Continuing without URL content.")
            ingestion = None
    else:
        warnings.append("No URL provided. Profile will be built from instruction text only.")

    # Build a minimal stub ingestion result if we have no URL content
    if ingestion is None:
        from .ingestion import IngestionResult as IR
        ingestion = IR(url="", raw_text="", status="mock", provider_used="none")

    # ------------------------------------------------------------------
    # Stage 3: Profile extraction
    # ------------------------------------------------------------------
    try:
        extracted: ExtractedProfile = extract_profile(ingestion, parsed)
    except Exception as exc:
        return OnboardingResult(
            success=False, profile=None,
            error=f"Profile extraction failed: {exc}",
            message="Onboarding failed at profile extraction stage.",
            parsed_instruction=_parsed_to_dict(parsed),
            ingestion_summary=_ingestion_to_dict(ingestion),
        )

    # Aggregate warnings from all stages
    warnings.extend(parsed.notes)
    warnings.extend(extracted.notes)

    # ------------------------------------------------------------------
    # Stage 4: Enrollment — create and persist BuyerProfile
    # ------------------------------------------------------------------

    # Check for duplicate enrollment by user_id
    existing = next(
        (b for b in store.buyers.values() if b.user_id == user_id), None
    )
    if existing:
        warnings.append(
            f"User already has a buyer profile (id={existing.id}). "
            "Returning existing profile — re-enroll not yet supported."
        )
        message = _build_success_message(extracted, existing, re_enrolled=False)
        return OnboardingResult(
            success=True,
            profile=existing,
            parsed_instruction=_parsed_to_dict(parsed),
            ingestion_summary=_ingestion_to_dict(ingestion),
            extracted_fields=_extracted_to_dict(extracted),
            message=message,
            confidence=extracted.confidence,
            warnings=warnings,
        )

    profile = BuyerProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        context_source_url=effective_url,
        onboarding_raw_prompt=instruction,
        organization=extracted.organization,
        task_history_count=0,
        created_at=datetime.utcnow(),
        # Extended fields (see models/user.py)
        display_name_hint=extracted.display_name,
        industry_hint=extracted.industry_hint,
        preferred_categories=extracted.preferred_categories,
        use_case_summary=extracted.use_case_summary,
        onboarding_confidence=extracted.confidence,
        onboarding_source=extracted.extraction_source,
    )

    store.buyers[profile.id] = profile
    store.log(
        event_type="buyer.onboarded",
        entity_type="buyer",
        entity_id=profile.id,
        actor_id=user_id,
        actor_role="buyer",
        message=(
            f"Buyer enrolled: {extracted.organization or 'Unknown'} "
            f"[confidence={extracted.confidence:.0%}] "
            f"[source={extracted.extraction_source}]"
        ),
        metadata={
            "url": effective_url,
            "instruction": instruction,
            "organization": extracted.organization,
            "industry": extracted.industry_hint,
            "preferred_categories": extracted.preferred_categories,
        },
    )

    message = _build_success_message(extracted, profile, re_enrolled=False)
    return OnboardingResult(
        success=True,
        profile=profile,
        parsed_instruction=_parsed_to_dict(parsed),
        ingestion_summary=_ingestion_to_dict(ingestion),
        extracted_fields=_extracted_to_dict(extracted),
        message=message,
        confidence=extracted.confidence,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Human-readable message builder
# ---------------------------------------------------------------------------

def _build_success_message(
    extracted: ExtractedProfile,
    profile: BuyerProfile,
    re_enrolled: bool,
) -> str:
    verb = "Re-enrolled" if re_enrolled else "Enrolled"
    org = extracted.organization or "Unknown organization"
    cats = ", ".join(c.replace("_", " ") for c in extracted.preferred_categories) or "general"
    confidence_pct = f"{extracted.confidence:.0%}"
    source_note = {
        "http":             "URL content fetched successfully",
        "mock":             "URL content mocked (real fetch failed or mock mode active)",
        "instruction_only": "Built from instruction text only — no URL content",
        "none":             "No URL provided",
    }.get(extracted.extraction_source, extracted.extraction_source)

    return (
        f"{verb} as buyer agent. "
        f"Organization: {org}. "
        f"Service interests: {cats}. "
        f"Confidence: {confidence_pct}. "
        f"Profile ID: {profile.id}. "
        f"Source: {source_note}."
    )


# ---------------------------------------------------------------------------
# Dict serializers for pipeline trace
# ---------------------------------------------------------------------------

def _parsed_to_dict(p: ParsedInstruction) -> Dict[str, Any]:
    return {
        "intent": p.intent,
        "url_extracted_from_text": p.url_in_text,
        "name_hint": p.name_hint,
        "preferred_categories": p.preferred_categories,
        "confidence": p.confidence,
        "notes": p.notes,
    }


def _ingestion_to_dict(i: IngestionResult) -> Dict[str, Any]:
    return {
        "url": i.url or None,
        "status": i.status,
        "provider": i.provider_used,
        "title": i.title,
        "domain": i.domain,
        "word_count": i.word_count,
        "error": i.error,
    }


def _extracted_to_dict(e: ExtractedProfile) -> Dict[str, Any]:
    return {
        "organization": e.organization,
        "display_name": e.display_name,
        "industry_hint": e.industry_hint,
        "preferred_categories": e.preferred_categories,
        "use_case_summary": e.use_case_summary,
        "extraction_source": e.extraction_source,
        "confidence": e.confidence,
        "notes": e.notes,
    }
