"""
Marketplace Matching Engine.

Scores and ranks all eligible sellers against a given task using a
transparent, weighted formula. Every intermediate value is preserved
so the result is fully explainable in the observability console.

Matching formula (weighted composite score 0.0–1.0):

  match_score = (
      w_category   * category_relevance   +   # Is this seller's primary specialty?
      w_benchmark  * benchmark_norm       +   # Historical quality vs. competitors
      w_reputation * reputation_norm      +   # Peer-rated reliability (0–5 → 0–1)
      w_price      * price_score          +   # Lower price = higher score (inverted)
      w_confidence * confidence_score     +   # Seller's self-reported confidence
      w_capacity   * capacity_score           # Current availability headroom
  )

Weights sum to 1.0. They are exposed as module-level constants so any
team member can read, debate, and adjust them without touching logic.

Eligibility gates (hard filters applied before scoring):
  1. Seller must be APPROVED.
  2. Seller must cover the task's category.
  3. Seller must support the task's requested output type.
  4. Seller must have remaining capacity.

Future: expose weights as config (env vars or DB settings).
Future: add buyer preference signals (preferred price range, max ETA).
Future: A/B test different weight vectors and measure outcome quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models.enums import ApprovalStatus
from ..models.task import Task
from ..models.user import SellerProfile

# ---------------------------------------------------------------------------
# Scoring weights — must sum to 1.0
# ---------------------------------------------------------------------------

W_CATEGORY   = 0.30   # Highest: category match is the primary qualification gate
W_BENCHMARK  = 0.20   # Historical task quality score
W_REPUTATION = 0.20   # Community reputation (audit-derived)
W_PRICE      = 0.15   # Price competitiveness (inverted — cheaper scores higher)
W_CONFIDENCE = 0.10   # Seller's self-reported confidence for this type of work
W_CAPACITY   = 0.05   # Availability headroom (lowest — all sellers start full)

assert abs(W_CATEGORY + W_BENCHMARK + W_REPUTATION + W_PRICE + W_CONFIDENCE + W_CAPACITY - 1.0) < 1e-9, \
    "Matching weights must sum to 1.0"

# Price normalisation reference: tasks above this are considered "expensive"
# Future: derive from live market data or task category benchmarks
MAX_REFERENCE_PRICE = 200.0   # USD


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SellerMatchScore:
    """
    Complete scoring record for one seller against one task.
    Preserved in full so every number shown in the UI has a clear source.
    """
    seller_id: str
    seller_name: str
    match_score: float                          # Final composite 0.0–1.0
    score_breakdown: Dict[str, float]           # Per-dimension raw scores (pre-weight)
    weighted_breakdown: Dict[str, float]        # Per-dimension weighted contributions
    is_eligible: bool                           # False if any hard gate failed
    ineligibility_reason: Optional[str] = None
    fit_explanation: str = ""                   # Human-readable summary for buyer


@dataclass
class MatchingResult:
    """
    Output of the matching engine for a given task.
    shortlisted: ordered list of eligible sellers, best first.
    all_scores: full scoring details for every seller considered (for transparency).
    """
    task_id: str
    shortlisted: List[SellerMatchScore]         # Eligible sellers ranked by match_score
    all_scores: List[SellerMatchScore]          # Every seller considered (incl. ineligible)
    shortlist_count: int = 0
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Eligibility check
# ---------------------------------------------------------------------------

def _check_eligibility(
    profile: SellerProfile,
    task: Task,
    current_task_load: int,
) -> tuple[bool, Optional[str]]:
    """
    Hard gates: return (True, None) if seller is eligible, else (False, reason).
    Any failing gate immediately disqualifies the seller from the shortlist.
    """
    if str(profile.approval_status) != ApprovalStatus.APPROVED:
        return False, f"Not approved (status={profile.approval_status})"

    task_category = str(task.category)
    seller_categories = [str(c) for c in profile.specialization_categories]
    if task_category not in seller_categories:
        return False, f"Category mismatch: seller covers {seller_categories}, task is {task_category}"

    task_output = str(task.requested_output_type)
    if task_output not in profile.supported_output_types:
        return False, (
            f"Output type mismatch: seller supports {profile.supported_output_types}, "
            f"task requests {task_output}"
        )

    if current_task_load >= profile.capacity:
        return False, f"At capacity ({current_task_load}/{profile.capacity})"

    return True, None


# ---------------------------------------------------------------------------
# Individual dimension scorers
# ---------------------------------------------------------------------------

def _score_category(profile: SellerProfile, task: Task) -> float:
    """
    1.0  if task category is the seller's *primary* specialization (first listed).
    0.75 if task category is a secondary specialization.
    0.0  if no match (should not reach here after eligibility check).
    """
    cats = [str(c) for c in profile.specialization_categories]
    task_cat = str(task.category)
    if not cats:
        return 0.0
    if cats[0] == task_cat:
        return 1.0
    if task_cat in cats:
        return 0.75
    return 0.0


def _score_benchmark(profile: SellerProfile) -> float:
    """
    Normalise benchmark_score to 0.0–1.0.
    If not yet set (new seller), use a neutral default of 0.5.
    """
    if profile.benchmark_score is None:
        return 0.5   # Neutral prior for new sellers with no history
    return float(max(0.0, min(1.0, profile.benchmark_score)))


def _score_reputation(profile: SellerProfile) -> float:
    """
    Normalise reputation_score (0.0–5.0 stars) to 0.0–1.0.
    New sellers (0.0 stars) score 0.5 neutral rather than 0.0
    to avoid unfairly penalising them in early marketplace.
    """
    raw = float(profile.reputation_score)
    if raw == 0.0:
        return 0.5   # Neutral prior for new sellers
    return max(0.0, min(raw / 5.0, 1.0))


def _score_price(profile: SellerProfile, reference_price: float = MAX_REFERENCE_PRICE) -> float:
    """
    Inverted price score: lower price → higher score.
    Price = 0 → 1.0; price = reference_price → 0.0; price above → clipped to 0.0.

    Uses square-root curve for gentler penalisation of mid-range prices.
    Future: normalise against the actual price distribution of competing quotes.
    """
    price = float(profile.base_price or 50.0)
    if price <= 0:
        return 1.0
    ratio = price / reference_price
    if ratio >= 1.0:
        return 0.0
    # 1 - sqrt(ratio) gives a curve that's more generous to mid-range sellers
    import math
    return round(1.0 - math.sqrt(ratio), 4)


def _score_confidence(profile: SellerProfile) -> float:
    """Pass through seller's self-reported confidence (already 0.0–1.0)."""
    return float(max(0.0, min(1.0, profile.confidence_score)))


def _score_capacity(profile: SellerProfile, current_load: int) -> float:
    """
    Headroom score: (capacity - current_load) / capacity.
    Seller at 0% utilisation → 1.0; seller at 90% → 0.1.
    """
    if profile.capacity <= 0:
        return 0.0
    headroom = max(0, profile.capacity - current_load)
    return round(headroom / profile.capacity, 4)


# ---------------------------------------------------------------------------
# Fit explanation builder
# ---------------------------------------------------------------------------

def _build_fit_explanation(
    profile: SellerProfile,
    score: float,
    breakdown: Dict[str, float],
    task: Task,
) -> str:
    """
    Build a one-paragraph plain-English explanation of why this seller
    was matched to this task. Shown directly in the buyer console.
    """
    parts = []

    # Category
    cats = [str(c) for c in profile.specialization_categories]
    if cats and cats[0] == str(task.category):
        parts.append(f"Primary specialization in {task.category.replace('_', ' ')}")
    else:
        parts.append(f"Covers {task.category.replace('_', ' ')}")

    # Quality signals
    if profile.benchmark_score is not None and profile.benchmark_score >= 0.8:
        parts.append(f"strong benchmark score ({profile.benchmark_score:.0%})")
    if profile.reputation_score >= 4.0:
        parts.append(f"high reputation ({profile.reputation_score:.1f}/5)")
    elif profile.reputation_score == 0.0:
        parts.append("new to marketplace (no prior reviews)")

    # Price
    price = profile.base_price or 50.0
    if price < 60:
        parts.append(f"competitive pricing (${price:.0f}/task)")
    else:
        parts.append(f"${price:.0f}/task")

    # ETA
    parts.append(f"ETA {profile.estimated_minutes}min")

    # Confidence
    if profile.confidence_score >= 0.85:
        parts.append(f"high confidence ({profile.confidence_score:.0%})")

    joined = "; ".join(parts)
    return f"Match score {score:.0%}. {joined}."


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_seller(
    profile: SellerProfile,
    task: Task,
    current_task_load: int = 0,
) -> SellerMatchScore:
    """
    Compute a complete SellerMatchScore for one seller against one task.
    Always returns a score — ineligible sellers get match_score=0.0 with reason.
    """
    eligible, reason = _check_eligibility(profile, task, current_task_load)

    if not eligible:
        return SellerMatchScore(
            seller_id=profile.id,
            seller_name=profile.display_name,
            match_score=0.0,
            score_breakdown={},
            weighted_breakdown={},
            is_eligible=False,
            ineligibility_reason=reason,
            fit_explanation=f"Ineligible: {reason}",
        )

    # Raw dimension scores
    raw = {
        "category_relevance": _score_category(profile, task),
        "benchmark":          _score_benchmark(profile),
        "reputation":         _score_reputation(profile),
        "price":              _score_price(profile),
        "confidence":         _score_confidence(profile),
        "capacity":           _score_capacity(profile, current_task_load),
    }

    # Weighted contributions
    weights = {
        "category_relevance": W_CATEGORY,
        "benchmark":          W_BENCHMARK,
        "reputation":         W_REPUTATION,
        "price":              W_PRICE,
        "confidence":         W_CONFIDENCE,
        "capacity":           W_CAPACITY,
    }
    weighted = {k: round(raw[k] * weights[k], 4) for k in raw}
    composite = round(sum(weighted.values()), 4)

    explanation = _build_fit_explanation(profile, composite, raw, task)

    return SellerMatchScore(
        seller_id=profile.id,
        seller_name=profile.display_name,
        match_score=composite,
        score_breakdown=raw,
        weighted_breakdown=weighted,
        is_eligible=True,
        fit_explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Matching engine entry point
# ---------------------------------------------------------------------------

def run_matching(
    task: Task,
    sellers: List[SellerProfile],
    task_loads: Optional[Dict[str, int]] = None,
    max_shortlist: int = 3,
) -> MatchingResult:
    """
    Score all sellers against the task and return a ranked shortlist.

    Args:
        task:          the task to match sellers for
        sellers:       all SellerProfile records from the store
        task_loads:    {seller_id: current_active_task_count} — for capacity scoring
                       If None, assumes 0 load for all sellers.
        max_shortlist: maximum number of sellers to include in the shortlist

    Returns:
        MatchingResult with ranked shortlist and full scoring trace.
    """
    loads = task_loads or {}
    all_scores: List[SellerMatchScore] = []
    notes: List[str] = []

    for profile in sellers:
        load = loads.get(profile.id, 0)
        score = score_seller(profile, task, current_task_load=load)
        all_scores.append(score)

    # Sort eligible sellers by match_score descending
    eligible = [s for s in all_scores if s.is_eligible]
    ineligible = [s for s in all_scores if not s.is_eligible]
    eligible.sort(key=lambda s: s.match_score, reverse=True)

    shortlisted = eligible[:max_shortlist]

    if not eligible:
        notes.append(
            f"No eligible sellers found for category '{task.category}'. "
            "Check that approved sellers exist for this category."
        )
    elif len(eligible) < max_shortlist:
        notes.append(
            f"Only {len(eligible)} eligible seller(s) found "
            f"(requested up to {max_shortlist})."
        )

    if ineligible:
        reasons = {s.seller_name: s.ineligibility_reason for s in ineligible}
        notes.append(f"Ineligible sellers excluded: {reasons}")

    return MatchingResult(
        task_id=task.id,
        shortlisted=shortlisted,
        all_scores=all_scores,
        shortlist_count=len(shortlisted),
        notes=notes,
    )
