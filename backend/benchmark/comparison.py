"""
Benchmark Comparison Scoring Engine.

Scores both specialist and generalist outputs independently against the task
brief using deterministic heuristics, then builds a full BenchmarkComparison
record with dimension breakdowns, cost comparison, ETA comparison, and
a recommendation.

Scoring dimensions (each 0.0–1.0):
  quality       — output depth, reasoning, and relevance to task description
  structure     — format match to requested_output_type
  specificity   — domain-specific content vs. generic statements
  completeness  — presence of all expected output elements

How specialist and generalist are differentiated:
  Specialists receive bonuses for:
    - Having domain-specific key fields (risk_flags, key_metrics, clauses_reviewed, etc.)
    - Structured output with rich nested data
    - Category alignment signal

  Generalists are penalised for:
    - Generic language markers ("general reasoning", "without specialized tools")
    - Missing domain-specific fields
    - Lower structural richness

This asymmetry reflects the real-world expectation that LLM specialists with
domain tools outperform vanilla general models on structured professional tasks.

MVP: all scoring is heuristic (no LLM judge). Values are realistic enough to
demonstrate the comparison concept and drive the admin/buyer dashboards.

Future: replace score_output() with an LLM-as-judge call where the judge
receives the task brief + both outputs + a rubric, and returns dimension scores.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from ..models.task import BenchmarkComparison, Task
from ..models.user import GeneralistProfile, SellerProfile

# Win threshold: delta must exceed this to declare a clear winner
WINNER_THRESHOLD = 0.05


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

def _score_quality(result: Dict[str, Any], is_specialist: bool) -> float:
    """
    Quality score: depth, reasoning, task relevance.

    Heuristics:
      - Summary length (proxy for depth): up to +0.20
      - Number of top-level keys (proxy for richness): up to +0.20
      - Presence of reasoning or analysis keys: +0.10
      - mock=True penalty: -0.05
      - Specialist bonus for domain-specific reasoning keys: +0.10
    """
    score = 0.60  # Base

    summary = str(result.get("summary", ""))
    if len(summary) >= 200:
        score += 0.20
    elif len(summary) >= 100:
        score += 0.10

    key_count = len(result.keys())
    if key_count >= 6:
        score += 0.20
    elif key_count >= 4:
        score += 0.10

    # Domain reasoning indicators
    reasoning_keys = {"risk_flags", "key_metrics", "clauses_reviewed",
                      "recommended_actions", "strategic_options", "top_competitors"}
    if any(k in result for k in reasoning_keys):
        score += 0.10

    if result.get("mock"):
        score -= 0.05

    if is_specialist:
        # Specialist bonus: structured domain output expected
        if any(k in result for k in reasoning_keys):
            score += 0.10
    else:
        # Generalist penalty: generic markers reduce quality score
        text_blob = str(result).lower()
        if "without specialized" in text_blob or "general reasoning" in text_blob:
            score -= 0.10
        if result.get("agent_type") == "generalist":
            score -= 0.05  # Small penalty for being non-specialist

    return round(min(max(score, 0.0), 1.0), 3)


def _score_structure(result: Dict[str, Any], requested_output_type: str) -> float:
    """
    Structure score: how well the output format matches the requested type.

    Heuristics by output_type:
      report          → expects 'summary' key + length
      summary         → expects short 'summary' key
      structured_json → expects multiple typed fields (dict-in-dict)
      bullet_list     → expects list-valued fields
    """
    score = 0.70  # Base

    if requested_output_type == "report":
        if "summary" in result and len(str(result.get("summary", ""))) >= 150:
            score += 0.20
    elif requested_output_type == "summary":
        if "summary" in result and len(str(result.get("summary", ""))) < 300:
            score += 0.20
    elif requested_output_type == "structured_json":
        nested = sum(1 for v in result.values() if isinstance(v, dict))
        if nested >= 1:
            score += 0.15
        if len(result.keys()) >= 5:
            score += 0.10
    elif requested_output_type == "bullet_list":
        lists = sum(1 for v in result.values() if isinstance(v, list))
        if lists >= 1:
            score += 0.20

    return round(min(max(score, 0.0), 1.0), 3)


def _score_specificity(result: Dict[str, Any], is_specialist: bool) -> float:
    """
    Specificity score: domain-specific content vs. generic statements.

    Specialists should score higher here by design — this dimension
    captures the core thesis: specialized knowledge > generic reasoning.

    Heuristics:
      - Numeric data (percentages, amounts, counts): +0.15
      - Named entities (capitalized multi-word phrases): proxy via text length
      - Generic hedge phrases: -0.15
      - Domain-specific structural fields: +0.15
    """
    score = 0.55 if is_specialist else 0.45  # Asymmetric base

    text = str(result)

    # Numeric specificity: percentages, dollar amounts, ratios
    import re
    numeric_hits = len(re.findall(r"\d+\.?\d*[%$xX]", text))
    if numeric_hits >= 3:
        score += 0.15
    elif numeric_hits >= 1:
        score += 0.08

    # Domain structural fields
    domain_fields = {
        "key_metrics", "risk_flags", "clauses_reviewed", "compliance_status",
        "market_size_usd_bn", "top_competitors", "strategic_options",
        "recommended_option", "recommended_actions",
    }
    matched = sum(1 for f in domain_fields if f in result)
    if matched >= 3:
        score += 0.15
    elif matched >= 1:
        score += 0.08

    # Generic hedge penalty
    generic_phrases = [
        "without specialized", "general reasoning", "may lack depth",
        "specialist review recommended", "general observation",
    ]
    if any(p in text.lower() for p in generic_phrases):
        score -= 0.15

    return round(min(max(score, 0.0), 1.0), 3)


def _score_completeness(result: Dict[str, Any], is_specialist: bool) -> float:
    """
    Completeness score: are all expected elements present?

    Universal expected elements:
      - summary or equivalent
      - at least one list or dict value (structured content)
      - no empty result

    Specialist expected elements (bonus if present):
      - sources list
      - risk_flags or similar risk indicator
    """
    if not result:
        return 0.0

    score = 0.60  # Base

    has_summary = "summary" in result or any(
        k in result for k in ("key_points", "clauses_reviewed", "strategic_options")
    )
    if has_summary:
        score += 0.15

    has_structured = any(isinstance(v, (list, dict)) for v in result.values())
    if has_structured:
        score += 0.15

    if is_specialist:
        if "sources" in result:
            score += 0.05
        if any(k in result for k in ("risk_flags", "compliance_status", "recommended_actions")):
            score += 0.05

    return round(min(max(score, 0.0), 1.0), 3)


# ---------------------------------------------------------------------------
# Output scorer (combines all dimensions)
# ---------------------------------------------------------------------------

def score_output(
    result: Dict[str, Any],
    task: Task,
    is_specialist: bool,
) -> Tuple[float, Dict[str, float]]:
    """
    Score an agent's output across four dimensions.

    Returns:
        (composite_score, dimension_scores)
    """
    output_type = str(task.requested_output_type)

    dimensions = {
        "quality":      _score_quality(result, is_specialist),
        "structure":    _score_structure(result, output_type),
        "specificity":  _score_specificity(result, is_specialist),
        "completeness": _score_completeness(result, is_specialist),
    }

    # Equal weights across four dimensions
    composite = round(sum(dimensions.values()) / len(dimensions), 3)
    return composite, dimensions


# ---------------------------------------------------------------------------
# Main comparison builder
# ---------------------------------------------------------------------------

def build_comparison(
    task: Task,
    seller_profile: SellerProfile,
    generalist_profile: GeneralistProfile,
    seller_result: Dict[str, Any],
    generalist_result: Dict[str, Any],
    specialist_cost: float = 0.0,
) -> BenchmarkComparison:
    """
    Build a complete BenchmarkComparison from both outputs.

    Args:
        task:               the task both agents ran on
        seller_profile:     the specialist seller
        generalist_profile: the generalist baseline
        seller_result:      content from seller AgentResult
        generalist_result:  content from generalist AgentResult
        specialist_cost:    USD from the accepted Quote.proposed_price

    Returns:
        BenchmarkComparison with all fields populated.
    """
    # Score both outputs
    seller_score, seller_dims = score_output(seller_result, task, is_specialist=True)
    gen_score, gen_dims = score_output(generalist_result, task, is_specialist=False)

    delta = round(seller_score - gen_score, 3)

    # Determine winner
    if delta > WINNER_THRESHOLD:
        winner = "seller"
    elif delta < -WINNER_THRESHOLD:
        winner = "generalist"
    else:
        winner = "tie"

    # Recommendation
    recommendation = _build_recommendation(
        winner=winner,
        delta=delta,
        specialist_cost=specialist_cost,
        generalist_cost=generalist_profile.cost_per_task,
        specialist_eta=seller_profile.estimated_minutes,
        generalist_eta=generalist_profile.estimated_minutes,
    )

    summary = _build_summary(
        seller_name=seller_profile.display_name,
        seller_score=seller_score,
        gen_score=gen_score,
        winner=winner,
        delta=delta,
        recommendation=recommendation,
        seller_dims=seller_dims,
        gen_dims=gen_dims,
        specialist_cost=specialist_cost,
        generalist_cost=generalist_profile.cost_per_task,
    )

    return BenchmarkComparison(
        id=str(uuid.uuid4()),
        task_id=task.id,
        task_category=str(task.category),
        seller_id=seller_profile.id,
        seller_display_name=seller_profile.display_name,
        generalist_id=generalist_profile.id,
        generalist_model=generalist_profile.model_identifier,
        seller_score=seller_score,
        generalist_score=gen_score,
        seller_dimension_scores=seller_dims,
        generalist_dimension_scores=gen_dims,
        specialist_cost=specialist_cost,
        generalist_cost=generalist_profile.cost_per_task,
        specialist_eta_minutes=seller_profile.estimated_minutes,
        generalist_eta_minutes=generalist_profile.estimated_minutes,
        winner=winner,
        delta=delta,
        recommendation=recommendation,
        summary=summary,
        scoring_method="mock_heuristic",
        mock=True,
        created_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Recommendation + summary builders
# ---------------------------------------------------------------------------

def _build_recommendation(
    winner: str,
    delta: float,
    specialist_cost: float,
    generalist_cost: float,
    specialist_eta: int,
    generalist_eta: int,
) -> str:
    """
    Produce a human-readable recommendation label.

    Logic:
      - Clear specialist win (delta > 0.10): "use_specialist"
      - Marginal specialist win but significantly cheaper generalist: "consider_generalist"
      - Generalist win: "use_generalist"
      - Tie: "tie"
    """
    cost_delta = specialist_cost - generalist_cost  # Positive = specialist is more expensive

    if winner == "seller":
        if delta >= 0.15:
            return "use_specialist"       # Strong specialist advantage
        elif cost_delta > 50.0:
            return "consider_generalist"  # Specialist only marginally better but much pricier
        else:
            return "use_specialist"
    elif winner == "generalist":
        return "use_generalist"
    else:
        # Tie — recommend generalist if significantly cheaper
        if cost_delta > 30.0:
            return "use_generalist"       # Equal quality, specialist much more expensive
        return "tie"


def _build_summary(
    seller_name: str,
    seller_score: float,
    gen_score: float,
    winner: str,
    delta: float,
    recommendation: str,
    seller_dims: Dict[str, float],
    gen_dims: Dict[str, float],
    specialist_cost: float,
    generalist_cost: float,
) -> str:
    """Build a plain-English summary paragraph for the admin/buyer console."""
    winner_label = {
        "seller": f"specialist ({seller_name})",
        "generalist": "generalist baseline",
        "tie": "neither (tie)",
    }.get(winner, winner)

    rec_label = {
        "use_specialist":      "Recommendation: use the specialist.",
        "use_generalist":      "Recommendation: use the generalist (cost-competitive).",
        "consider_generalist": "Recommendation: consider generalist — cost savings outweigh marginal quality delta.",
        "tie":                 "Recommendation: either is acceptable for this task.",
        "insufficient_data":   "Recommendation: insufficient data for a confident recommendation.",
    }.get(recommendation, recommendation)

    strongest_specialist_dim = max(seller_dims, key=lambda k: seller_dims[k] - gen_dims.get(k, 0))
    biggest_gap = seller_dims[strongest_specialist_dim] - gen_dims.get(strongest_specialist_dim, 0)

    lines = [
        f"Specialist scored {seller_score:.0%} vs. generalist {gen_score:.0%}.",
        f"Winner: {winner_label} (delta {delta:+.3f}).",
        f"Specialist strongest on '{strongest_specialist_dim}' "
        f"(+{biggest_gap:.0%} over generalist).",
        f"Cost: specialist ${specialist_cost:.2f} vs. generalist ${generalist_cost:.2f}.",
        rec_label,
        "[Mock heuristic scoring — replace with LLM-as-judge for production.]",
    ]
    return " ".join(lines)
