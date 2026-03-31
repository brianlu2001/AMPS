"""
Marketplace Quote Generator.

Takes match scores from the matching engine and produces Quote records
for each shortlisted seller. Quotes are persisted in the store and
referenced from the Task.

Quote price logic:
  - FIXED sellers: use base_price directly from SellerProfile.
  - QUOTED sellers: use base_price as the initial estimate
    (real dynamic pricing deferred to post-MVP).

ETA logic:
  - Use estimated_minutes from SellerProfile (flat for MVP).
  - Future: adjust by current_task_load (queue depth effect).

Quote confidence:
  - Seller's self-reported confidence_score from SellerProfile.

All quotes include:
  - match_score and score_breakdown from the matching engine.
  - fit_explanation: human-readable reasoning for the buyer.
  - seller_display_name: denormalised for display without extra lookup.

Future: add quote expiry, counter-offer, and negotiation round support.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List

from ..models.task import Quote, Task
from ..models.user import SellerProfile
from .matching import SellerMatchScore


def generate_quote_for_match(
    task: Task,
    profile: SellerProfile,
    match: SellerMatchScore,
) -> Quote:
    """
    Generate one Quote from a seller match result.

    Args:
        task:    the task being quoted for
        profile: the matched seller's profile
        match:   the scoring result from the matching engine

    Returns:
        A Quote with all marketplace fields populated.
    """
    price = _calculate_price(profile, task, match)
    eta = _calculate_eta(profile, task)

    # Build quote notes: combine pricing model context with fit explanation
    pricing_note = _pricing_note(profile, price)
    notes = f"{pricing_note} {match.fit_explanation}"

    return Quote(
        id=str(uuid.uuid4()),
        task_id=task.id,
        seller_id=profile.id,
        proposed_price=price,
        estimated_minutes=eta,
        confidence_score=float(profile.confidence_score),
        notes=notes,
        match_score=match.match_score,
        fit_explanation=match.fit_explanation,
        score_breakdown=match.score_breakdown,
        seller_display_name=profile.display_name,
        accepted=False,
        created_at=datetime.utcnow(),
    )


def generate_quotes_for_shortlist(
    task: Task,
    profiles_by_id: dict,         # {seller_id: SellerProfile}
    matches: List[SellerMatchScore],
) -> List[Quote]:
    """
    Generate a Quote for every seller in the shortlist.

    Args:
        task:           the task being quoted
        profiles_by_id: lookup dict {seller_id: SellerProfile}
        matches:        shortlisted SellerMatchScore list (eligible only)

    Returns:
        List of Quote objects in the same order as matches (best first).
    """
    quotes: List[Quote] = []
    for match in matches:
        profile = profiles_by_id.get(match.seller_id)
        if not profile:
            continue   # Safety: skip if profile disappeared from store
        quote = generate_quote_for_match(task, profile, match)
        quotes.append(quote)
    return quotes


# ---------------------------------------------------------------------------
# Price calculation
# ---------------------------------------------------------------------------

def _calculate_price(
    profile: SellerProfile,
    task: Task,
    match: SellerMatchScore,
) -> float:
    """
    Determine the quoted price for a task.

    MVP rules:
      - FIXED:  base_price from profile (no adjustment)
      - QUOTED: base_price as placeholder (real quoting deferred)
      - FREE:   0.0 (generalist baseline only)

    Future: for QUOTED sellers, pass task complexity signals
    (description length, context_url presence, output_type) to a
    pricing model to produce a tailored estimate.
    """
    model = str(profile.pricing_model)
    base = float(profile.base_price or 50.0)

    if model == "free":
        return 0.0
    # Both "fixed" and "quoted" use base_price for MVP
    return round(base, 2)


def _calculate_eta(profile: SellerProfile, task: Task) -> int:
    """
    Estimate delivery time in minutes.

    MVP: use estimated_minutes from the seller profile (flat).
    Future: adjust based on:
      - task complexity (description length, output type)
      - current_task_load (queue depth)
      - time-of-day or SLA tier
    """
    return int(profile.estimated_minutes)


def _pricing_note(profile: SellerProfile, price: float) -> str:
    """Build a short pricing context sentence for the quote notes."""
    model = str(profile.pricing_model)
    if model == "fixed":
        return f"Fixed-rate pricing: ${price:.2f}/task."
    elif model == "quoted":
        return f"Estimated quote: ${price:.2f} (final price may vary by task complexity)."
    elif model == "free":
        return "No charge (baseline comparison service)."
    return f"Price: ${price:.2f}."
