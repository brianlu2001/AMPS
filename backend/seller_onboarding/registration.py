"""
Seller Onboarding Registration Orchestrator.

Entry point: run_seller_registration(request, user_id, store, registry)

Pipeline stages:
  1. validate_seller_registration()   — field-level validation
  2. _build_profile()                 — assemble SellerProfile
  3. _trigger_auditor_review()        — create SellerOnboardingReview, queue for audit
  4. _persist_and_register()          — save to store, register agent in registry, log

RegistrationResult is the API response shape — structured, human-readable,
and includes the full review readiness state for the observability console.

Agent class selection:
  The appropriate BaseSellerAgent subclass is chosen based on
  specialization_categories. When a seller covers multiple categories,
  the first listed category determines the agent class for MVP.
  Future: support multi-category execution adapters.

External agent adapter:
  agent_type="mock"         → existing mock sellers (no external calls)
  agent_type="external_api" → future: call external_agent_api_url (post-MVP)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..agents.registry import AgentRegistry
from ..agents.seller import (
    BaseSellerAgent,
    FinancialResearchSeller,
    LegalAnalysisSeller,
    MarketIntelligenceSeller,
    StrategyResearchSeller,
)
from ..models.enums import ApprovalStatus, PricingModel, TaskCategory
from ..models.task import SellerOnboardingReview
from ..models.user import SellerProfile
from .validation import ValidationResult, validate_seller_registration

# ---------------------------------------------------------------------------
# Agent class selector — maps first category to execution class
# ---------------------------------------------------------------------------
# Future: replace with a plugin registry so new categories don't require
# editing this file.

_CATEGORY_TO_AGENT_CLASS: Dict[str, type] = {
    "financial_research":         FinancialResearchSeller,
    "legal_analysis":             LegalAnalysisSeller,
    "market_intelligence":        MarketIntelligenceSeller,
    "strategy_business_research": StrategyResearchSeller,
}

# Quality threshold for auto-approve vs. needs_review
_AUTO_APPROVE_SCORE_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RegistrationResult:
    success: bool
    seller_profile: Optional[SellerProfile]
    onboarding_review: Optional[SellerOnboardingReview]
    validation: Optional[ValidationResult]
    message: str
    next_steps: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "next_steps": self.next_steps,
            "seller_profile": self.seller_profile.dict() if self.seller_profile else None,
            "onboarding_review": self.onboarding_review.dict() if self.onboarding_review else None,
            "validation": {
                "valid": self.validation.valid,
                "errors": self.validation.errors,
                "warnings": self.validation.warnings,
            } if self.validation else None,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_seller_registration(
    request: Dict[str, Any],
    user_id: str,
    store: Any,         # InMemoryStore — avoid circular import
    registry: AgentRegistry,
) -> RegistrationResult:
    """
    Run the full seller registration pipeline.

    Args:
        request  : validated dict from POST /seller/register body
        user_id  : the authenticated User.id registering as a seller
        store    : InMemoryStore singleton
        registry : AgentRegistry singleton

    Returns:
        RegistrationResult — never raises.
    """
    # ------------------------------------------------------------------
    # Stage 1: Validate
    # ------------------------------------------------------------------
    validation = validate_seller_registration(request)
    if not validation.valid:
        return RegistrationResult(
            success=False,
            seller_profile=None,
            onboarding_review=None,
            validation=validation,
            message=(
                f"Registration failed validation. "
                f"{len(validation.errors)} error(s) must be fixed before submitting."
            ),
            error="; ".join(validation.errors),
        )

    # ------------------------------------------------------------------
    # Stage 2: Check for duplicate registration
    # ------------------------------------------------------------------
    existing = next(
        (s for s in store.sellers.values() if s.user_id == user_id), None
    )
    if existing:
        return RegistrationResult(
            success=False,
            seller_profile=existing,
            onboarding_review=None,
            validation=validation,
            message=(
                f"User already has a seller profile (id={existing.id}, "
                f"status={existing.approval_status}). "
                "Re-registration is not yet supported."
            ),
            error="duplicate_registration",
        )

    # ------------------------------------------------------------------
    # Stage 3: Build SellerProfile
    # ------------------------------------------------------------------
    profile = _build_profile(request, user_id)

    # ------------------------------------------------------------------
    # Stage 4: Trigger auditor review
    # ------------------------------------------------------------------
    review = _trigger_auditor_review(profile, store)
    profile.onboarding_review_id = review.id

    # ------------------------------------------------------------------
    # Stage 5: Persist + register agent + log
    # ------------------------------------------------------------------
    store.sellers[profile.id] = profile
    store.seller_onboarding_reviews[review.id] = review

    # Register agent in the execution registry
    agent = _instantiate_agent(profile)
    if agent:
        registry.register_seller(agent)

    store.log(
        event_type="seller.registered",
        entity_type="seller",
        entity_id=profile.id,
        actor_id=user_id,
        actor_role="seller",
        message=(
            f"Seller registered: '{profile.display_name}' "
            f"[{', '.join(profile.specialization_categories)}] "
            f"— status: {profile.approval_status}"
        ),
        metadata={
            "categories": profile.specialization_categories,
            "pricing_model": profile.pricing_model,
            "base_price": profile.base_price,
            "review_id": review.id,
            "review_status": review.review_status,
        },
    )

    # Determine next steps based on review outcome
    next_steps = _build_next_steps(profile, review)
    message = _build_message(profile, review)

    return RegistrationResult(
        success=True,
        seller_profile=profile,
        onboarding_review=review,
        validation=validation,
        message=message,
        next_steps=next_steps,
    )


# ---------------------------------------------------------------------------
# Profile builder
# ---------------------------------------------------------------------------

def _build_profile(data: Dict[str, Any], user_id: str) -> SellerProfile:
    """Assemble a SellerProfile from validated registration data."""
    categories = [TaskCategory(c) for c in data["specialization_categories"]]
    pricing = PricingModel(data["pricing_model"])

    return SellerProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        display_name=data["display_name"].strip(),
        description=data.get("description", "").strip() or None,
        website_url=data.get("website_url"),
        contact_email=data.get("contact_email"),
        specialization_categories=categories,
        supported_output_types=data.get("supported_output_types", ["report"]),
        expertise_claims=data.get("expertise_claims", []),
        benchmark_references=data.get("benchmark_references", []),
        pricing_model=pricing,
        base_price=data.get("base_price"),
        quote_notes=data.get("quote_notes"),
        estimated_minutes=int(data.get("estimated_minutes", 30)),
        capacity=int(data.get("capacity", 10)),
        confidence_score=float(data.get("confidence_score", 0.75)),
        approval_status=ApprovalStatus.NEEDS_REVIEW,
        agent_type=data.get("agent_type", "mock"),
        external_agent_api_url=data.get("external_agent_api_url"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Auditor review trigger
# ---------------------------------------------------------------------------

def _trigger_auditor_review(
    profile: SellerProfile,
    store: Any,
) -> SellerOnboardingReview:
    """
    Create a SellerOnboardingReview record for the new seller.

    MVP: auto-scores the profile using heuristic rules and sets
    review_status to "approved" or "needs_review" based on a threshold.

    Future: set review_status="queued" and let the auditor agent evaluate
    asynchronously via a background job or webhook.
    """
    issues: list[str] = []
    recommendations: list[str] = []

    # --- Completeness scoring ---
    completeness = 1.0
    if not profile.description:
        completeness -= 0.15
        issues.append("Missing description")
    if not profile.expertise_claims:
        completeness -= 0.20
        issues.append("No expertise claims provided")
    elif len(profile.expertise_claims) < 2:
        completeness -= 0.08
        recommendations.append("Add at least 2 expertise claims for stronger credibility")
    if not profile.website_url:
        completeness -= 0.05
        recommendations.append("Add a website_url for transparency")
    if not profile.benchmark_references:
        completeness -= 0.05
        recommendations.append("Add benchmark_references (portfolio items, publications)")

    # --- Expertise credibility scoring ---
    expertise = 1.0
    avg_claim_len = (
        sum(len(c) for c in profile.expertise_claims) / len(profile.expertise_claims)
        if profile.expertise_claims else 0
    )
    if avg_claim_len < 20:
        expertise -= 0.25
        issues.append("Expertise claims are too brief — provide more detail")
    if profile.confidence_score > 0.95:
        expertise -= 0.10
        recommendations.append(
            "Self-reported confidence > 0.95 requires strong evidence in expertise claims"
        )

    # --- Pricing clarity scoring ---
    pricing_clarity = 1.0
    if profile.pricing_model == "fixed" and not profile.base_price:
        pricing_clarity -= 0.30
        issues.append("Fixed pricing selected but no base_price provided")
    if profile.pricing_model == "quoted" and not profile.quote_notes:
        pricing_clarity -= 0.10
        recommendations.append("Add quote_notes to explain your quoting logic for buyers")

    # --- Category fit scoring ---
    # All four categories are valid — score deduction only for suspicious mismatches
    category_fit = 1.0
    if len(profile.specialization_categories) > 3:
        category_fit -= 0.10
        recommendations.append(
            "Covering 4 categories is unusual — consider narrowing specialization"
        )

    # --- Capacity realism scoring ---
    capacity_realism = 1.0
    if profile.capacity > 50:
        capacity_realism -= 0.15
        recommendations.append(f"capacity={profile.capacity} is high — auditor will verify")

    # --- Aggregate ---
    dimension_scores = {
        "completeness":          round(max(0.0, completeness), 2),
        "expertise_credibility": round(max(0.0, expertise), 2),
        "pricing_clarity":       round(max(0.0, pricing_clarity), 2),
        "category_fit":          round(max(0.0, category_fit), 2),
        "capacity_realism":      round(max(0.0, capacity_realism), 2),
    }
    overall = round(sum(dimension_scores.values()) / len(dimension_scores), 3)

    # Auto-decision: above threshold → APPROVED, below → NEEDS_REVIEW
    if overall >= _AUTO_APPROVE_SCORE_THRESHOLD and not issues:
        review_status = "approved"
        passed = True
        # Immediately flip profile to APPROVED
        profile.approval_status = ApprovalStatus.APPROVED
        profile.approved_at = datetime.utcnow()
        reasoning = (
            f"Profile scored {overall:.0%} overall. "
            "All required fields present and credibility threshold met. "
            "Auto-approved."
        )
    else:
        review_status = "needs_review"
        passed = None   # Not yet determined — human auditor required
        reasoning = (
            f"Profile scored {overall:.0%} overall. "
            f"{'Issues found: ' + '; '.join(issues) + '. ' if issues else ''}"
            "Queued for auditor review."
        )

    return SellerOnboardingReview(
        id=str(uuid.uuid4()),
        seller_profile_id=profile.id,
        auditor_id=None,            # Null = system (auto-review); set when human auditor picks up
        review_status=review_status,
        overall_score=overall,
        dimension_scores=dimension_scores,
        passed=passed,
        issues=issues,
        recommendations=recommendations,
        reasoning=reasoning,
        reviewed_at=datetime.utcnow() if review_status == "approved" else None,
    )


# ---------------------------------------------------------------------------
# Agent instantiation
# ---------------------------------------------------------------------------

def _instantiate_agent(profile: SellerProfile) -> Optional[BaseSellerAgent]:
    """
    Instantiate the appropriate seller agent class from a SellerProfile.

    Uses the first specialization_category to select the class.
    Returns None if agent_type != "mock" (external agents not yet wired).

    Future: when agent_type="external_api", return an ExternalApiSellerAgent
    that wraps the external_agent_api_url.
    """
    if profile.agent_type != "mock":
        # External agent adapters are post-MVP
        return None

    cats = profile.specialization_categories
    primary = cats[0] if cats else None
    agent_class = _CATEGORY_TO_AGENT_CLASS.get(str(primary))
    if not agent_class:
        return None

    return agent_class(agent_id=profile.id, profile=profile)


# ---------------------------------------------------------------------------
# Human-readable outputs
# ---------------------------------------------------------------------------

def _build_message(profile: SellerProfile, review: SellerOnboardingReview) -> str:
    cats = ", ".join(str(c).replace("_", " ") for c in profile.specialization_categories)
    status = profile.approval_status
    score_pct = f"{review.overall_score:.0%}" if review.overall_score is not None else "n/a"

    if status == "approved":
        return (
            f"Seller '{profile.display_name}' registered and auto-approved. "
            f"Specializations: {cats}. "
            f"Onboarding score: {score_pct}. "
            f"Profile ID: {profile.id}."
        )
    else:
        return (
            f"Seller '{profile.display_name}' registered and queued for auditor review. "
            f"Specializations: {cats}. "
            f"Onboarding score: {score_pct}. "
            f"Profile ID: {profile.id}. "
            f"Issues: {len(review.issues)}. "
            f"Status will update to APPROVED or REJECTED after review."
        )


def _build_next_steps(profile: SellerProfile, review: SellerOnboardingReview) -> List[str]:
    steps: list[str] = []
    if profile.approval_status == "approved":
        steps.append("You are now active on the marketplace and can accept tasks.")
        steps.append(f"View your profile at GET /seller/agents/{profile.id}")
    else:
        steps.append("Your profile is queued for auditor review.")
        steps.append("An admin or auditor will approve or reject your registration.")
        if review.issues:
            steps.append(
                f"Fix these issues to speed up approval: {'; '.join(review.issues)}"
            )
        if review.recommendations:
            steps.append(
                f"Optional improvements: {'; '.join(review.recommendations)}"
            )
    return steps
