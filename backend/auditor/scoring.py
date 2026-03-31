"""
Auditor Scoring Engine — shared dimension scorers for both audit workflows.

Task Output Audit dimensions (each 0.0–1.0):
  quality      — depth, reasoning quality, alignment with task brief
  relevance    — how specifically the output addresses the task description
  completeness — presence of expected elements for this output type and category
  genericity   — INVERTED measure: 1.0 = highly specific, 0.0 = entirely generic

Onboarding Audit dimensions (each 0.0–1.0):
  completeness          — required profile fields present
  expertise_credibility — expertise_claims quality and specificity
  pricing_clarity       — pricing model and price fields consistent
  category_fit          — specialization categories plausible
  capacity_realism      — capacity value within reasonable range

Scoring philosophy:
  - All scorers return float in [0.0, 1.0]
  - All scorers never raise — failures return a default score with a flag
  - Scoring weights are module-level constants for easy adjustment
  - "mock_heuristic" scoring method is honest about its limitations:
    scores are plausible but should not be treated as ground truth

Future: replace each scorer body with an LLM-as-judge call that receives
the task brief + output + a rubric and returns a score + reasoning.
The function signatures stay identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Shared constants — imported by agents/auditor.py and auditor/__init__.py
# ---------------------------------------------------------------------------

# Pass/fail thresholds
QUALITY_THRESHOLD = 0.70                    # Task output audit: below this = FAILED
ONBOARDING_AUTO_APPROVE_THRESHOLD = 0.80    # Onboarding: above this + no issues = auto-approved

# Task output audit weights (must sum to 1.0)
W_QUALITY      = 0.35
W_RELEVANCE    = 0.25
W_COMPLETENESS = 0.25
W_GENERICITY   = 0.15

assert abs(W_QUALITY + W_RELEVANCE + W_COMPLETENESS + W_GENERICITY - 1.0) < 1e-9

# Onboarding audit weights (must sum to 1.0)
W_OB_COMPLETENESS          = 0.25
W_OB_EXPERTISE_CREDIBILITY = 0.30
W_OB_PRICING_CLARITY       = 0.20
W_OB_CATEGORY_FIT          = 0.15
W_OB_CAPACITY_REALISM      = 0.10

assert abs(
    W_OB_COMPLETENESS + W_OB_EXPERTISE_CREDIBILITY + W_OB_PRICING_CLARITY +
    W_OB_CATEGORY_FIT + W_OB_CAPACITY_REALISM - 1.0
) < 1e-9

# Generic language markers — presence lowers specificity/relevance
GENERIC_MARKERS = [
    "without specialized", "general reasoning", "may lack depth",
    "specialist review recommended", "general observation",
    "further verification is recommended", "based on general",
    "plausible but", "specialist validation",
]

# Domain-specific field names that indicate specialist depth
DOMAIN_FIELDS = {
    "key_metrics", "risk_flags", "clauses_reviewed", "compliance_status",
    "market_size_usd_bn", "top_competitors", "strategic_options",
    "recommended_option", "recommended_actions", "sources",
    "growth_drivers", "risk_factors", "key_assumptions",
}


# ---------------------------------------------------------------------------
# Output type — AuditScoringResult
# ---------------------------------------------------------------------------

@dataclass
class TaskAuditScores:
    """Per-dimension scores for a task output audit."""
    quality: float
    relevance: float
    completeness: float
    genericity: float           # Inverted: 1.0 = specific, 0.0 = generic
    composite: float
    flags: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, float]:
        return {
            "quality":      self.quality,
            "relevance":    self.relevance,
            "completeness": self.completeness,
            "genericity":   self.genericity,
        }


@dataclass
class OnboardingAuditScores:
    """Per-dimension scores for a seller onboarding audit."""
    completeness: float
    expertise_credibility: float
    pricing_clarity: float
    category_fit: float
    capacity_realism: float
    composite: float
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, float]:
        return {
            "completeness":          self.completeness,
            "expertise_credibility": self.expertise_credibility,
            "pricing_clarity":       self.pricing_clarity,
            "category_fit":          self.category_fit,
            "capacity_realism":      self.capacity_realism,
        }


# ===========================================================================
# WORKFLOW A — Task Output Audit
# ===========================================================================

def score_task_output(
    result: Dict[str, Any],
    task_description: str,
    task_category: str,
    requested_output_type: str,
    is_specialist: bool = True,
) -> TaskAuditScores:
    """
    Score a task output across four dimensions.

    Args:
        result:               the agent's output content dict
        task_description:     the buyer's original task brief
        task_category:        the task's service category
        requested_output_type: the buyer's requested output format
        is_specialist:        True for seller output, False for generalist

    Returns:
        TaskAuditScores with per-dimension values and composite score.

    Future: replace each dimension with an LLM-as-judge sub-call.
    """
    flags: list[str] = []
    recs: list[str] = []

    q   = _score_output_quality(result, is_specialist, flags, recs)
    rel = _score_output_relevance(result, task_description, task_category, flags, recs)
    com = _score_output_completeness(result, requested_output_type, task_category, flags, recs)
    gen = _score_output_genericity(result, is_specialist, flags, recs)

    composite = round(
        W_QUALITY * q + W_RELEVANCE * rel + W_COMPLETENESS * com + W_GENERICITY * gen, 3
    )

    return TaskAuditScores(
        quality=q,
        relevance=rel,
        completeness=com,
        genericity=gen,
        composite=composite,
        flags=flags,
        recommendations=recs,
    )


def _score_output_quality(
    result: Dict[str, Any],
    is_specialist: bool,
    flags: list,
    recs: list,
) -> float:
    """
    Quality: output depth, reasoning, and task alignment.

    Heuristics:
      - Summary length (proxy for depth)
      - Total key count (proxy for structural richness)
      - Presence of domain reasoning fields
      - mock=True flag penalty
      - Specialist bonus for domain field depth
    """
    score = 0.60

    summary = str(result.get("summary", ""))
    if len(summary) >= 250:
        score += 0.20
    elif len(summary) >= 120:
        score += 0.10
    else:
        flags.append("summary_too_short")
        recs.append("Expand the summary to at least 120 characters for adequate depth.")

    key_count = len(result.keys())
    if key_count >= 7:
        score += 0.15
    elif key_count >= 4:
        score += 0.08
    else:
        flags.append("sparse_result_structure")

    matched_domain = sum(1 for f in DOMAIN_FIELDS if f in result)
    if matched_domain >= 3:
        score += 0.10
    elif matched_domain >= 1:
        score += 0.05

    if result.get("mock"):
        score -= 0.05
        flags.append("mock_output")

    if is_specialist and matched_domain < 2:
        flags.append("expected_more_domain_specific_fields")
        recs.append("Specialist outputs should include domain-specific structured fields.")

    return round(min(max(score, 0.0), 1.0), 3)


def _score_output_relevance(
    result: Dict[str, Any],
    task_description: str,
    task_category: str,
    flags: list,
    recs: list,
) -> float:
    """
    Relevance: how specifically the output addresses the task description.

    Heuristics:
      - Does the summary mention words from the task description?
      - Are there numeric specifics (percentages, amounts)?
      - Category-appropriate fields present?
    """
    score = 0.65

    # Word overlap between task description and output summary
    task_words = set(re.findall(r"\b\w{4,}\b", task_description.lower()))
    summary_text = str(result.get("summary", "")).lower()
    overlap = sum(1 for w in task_words if w in summary_text)
    if len(task_words) > 0:
        overlap_ratio = overlap / len(task_words)
        if overlap_ratio >= 0.3:
            score += 0.15
        elif overlap_ratio >= 0.15:
            score += 0.08
        else:
            flags.append("low_task_description_overlap")
            recs.append("Output summary should directly reference the task subject matter.")

    # Numeric specificity
    numeric_hits = len(re.findall(r"\d+\.?\d*[%$xX]", str(result)))
    if numeric_hits >= 3:
        score += 0.10
    elif numeric_hits >= 1:
        score += 0.05

    # Category-appropriate content signal
    cat_signals = {
        "financial_research":         ["revenue", "margin", "earnings", "ratio", "valuation"],
        "legal_analysis":             ["clause", "indemnif", "liability", "compliance", "contract"],
        "market_intelligence":        ["market", "competitor", "share", "tam", "growth"],
        "strategy_business_research": ["strategy", "option", "gtm", "positioning", "competitive"],
    }
    signals = cat_signals.get(task_category, [])
    result_text = str(result).lower()
    signal_hits = sum(1 for s in signals if s in result_text)
    if signal_hits >= 3:
        score += 0.10
    elif signal_hits >= 1:
        score += 0.05
    else:
        flags.append(f"missing_category_signals_for_{task_category}")

    return round(min(max(score, 0.0), 1.0), 3)


def _score_output_completeness(
    result: Dict[str, Any],
    requested_output_type: str,
    task_category: str,
    flags: list,
    recs: list,
) -> float:
    """
    Completeness: are all expected structural elements present?

    Checks:
      - Summary or equivalent narrative element
      - At least one list or dict value
      - Output-type-specific checks (report → long summary, bullet_list → lists)
      - Presence of sources or references
    """
    if not result:
        flags.append("empty_result")
        return 0.0

    score = 0.55

    has_summary = "summary" in result or any(
        k in result for k in ("key_points", "clauses_reviewed", "strategic_options")
    )
    if has_summary:
        score += 0.15
    else:
        flags.append("missing_summary_or_equivalent")
        recs.append("Include a 'summary' field or equivalent narrative field.")

    has_structured = any(isinstance(v, (list, dict)) for v in result.values())
    if has_structured:
        score += 0.15
    else:
        flags.append("no_structured_fields")
        recs.append("Add at least one list or dict field for structured output.")

    # Output-type specific checks
    if requested_output_type == "report" and len(str(result.get("summary", ""))) < 150:
        flags.append("report_summary_too_short")
        recs.append("Report output type requires a detailed summary (150+ chars).")
        score -= 0.10
    elif requested_output_type == "bullet_list":
        lists = sum(1 for v in result.values() if isinstance(v, list))
        if lists == 0:
            flags.append("bullet_list_missing_list_fields")
            recs.append("Bullet list output should include list-valued fields.")
            score -= 0.10

    if "sources" in result:
        score += 0.10
    else:
        recs.append("Consider adding a 'sources' field for verifiability.")

    return round(min(max(score, 0.0), 1.0), 3)


def _score_output_genericity(
    result: Dict[str, Any],
    is_specialist: bool,
    flags: list,
    recs: list,
) -> float:
    """
    Genericity score (INVERTED): 1.0 = highly specific, 0.0 = entirely generic.

    High genericity (low score here) means the output could apply to any task
    in the category — it lacks the task-specific analysis that justifies
    using a specialist over the generalist.

    This dimension specifically tests the specialist value proposition.

    Heuristics:
      - Generic language marker count
      - agent_type == "generalist" signal
      - Domain field presence (positive signal for specificity)
    """
    score = 0.80 if is_specialist else 0.45  # Specialists start higher

    text = str(result).lower()
    generic_hits = sum(1 for m in GENERIC_MARKERS if m in text)

    if generic_hits >= 3:
        score -= 0.30
        flags.append("highly_generic_output")
        recs.append("Output contains generic language — replace with task-specific analysis.")
    elif generic_hits >= 1:
        score -= 0.15
        flags.append("some_generic_language")

    if result.get("agent_type") == "generalist":
        score -= 0.10  # Explicit generalist marker

    # Domain specificity bonus
    domain_hits = sum(1 for f in DOMAIN_FIELDS if f in result)
    if domain_hits >= 3:
        score += 0.15
    elif domain_hits >= 1:
        score += 0.08

    return round(min(max(score, 0.0), 1.0), 3)


# ===========================================================================
# WORKFLOW B — Seller Onboarding Audit
# ===========================================================================

def score_seller_onboarding(profile_data: Dict[str, Any]) -> OnboardingAuditScores:
    """
    Score a seller's onboarding profile across five dimensions.

    Args:
        profile_data: dict representation of a SellerProfile
                      (use profile.dict() or profile.__dict__)

    Returns:
        OnboardingAuditScores with per-dimension values, composite, issues,
        and recommendations.
    """
    issues: list[str] = []
    recs: list[str] = []

    comp = _score_ob_completeness(profile_data, issues, recs)
    exp  = _score_ob_expertise(profile_data, issues, recs)
    pri  = _score_ob_pricing(profile_data, issues, recs)
    cat  = _score_ob_category_fit(profile_data, issues, recs)
    cap  = _score_ob_capacity(profile_data, issues, recs)

    composite = round(
        W_OB_COMPLETENESS * comp +
        W_OB_EXPERTISE_CREDIBILITY * exp +
        W_OB_PRICING_CLARITY * pri +
        W_OB_CATEGORY_FIT * cat +
        W_OB_CAPACITY_REALISM * cap,
        3
    )

    return OnboardingAuditScores(
        completeness=comp,
        expertise_credibility=exp,
        pricing_clarity=pri,
        category_fit=cat,
        capacity_realism=cap,
        composite=composite,
        issues=issues,
        recommendations=recs,
    )


def _score_ob_completeness(d: Dict[str, Any], issues: list, recs: list) -> float:
    """Required fields present and non-empty."""
    score = 1.0

    name = d.get("display_name", "")
    if not name or len(str(name).strip()) < 3:
        score -= 0.20; issues.append("display_name_too_short")

    desc = d.get("description", "")
    if not desc or len(str(desc).strip()) < 20:
        score -= 0.15; issues.append("missing_description")
        recs.append("Add a description of at least 20 characters explaining your expertise.")

    claims = d.get("expertise_claims", [])
    if not claims:
        score -= 0.20; issues.append("no_expertise_claims")
        recs.append("Add at least one expertise claim with specific credentials or experience.")

    cats = d.get("specialization_categories", [])
    if not cats:
        score -= 0.20; issues.append("no_specialization_categories")

    if not d.get("contact_email"):
        score -= 0.05
        recs.append("Adding a contact email improves trust and admin reachability.")

    return round(max(0.0, score), 3)


def _score_ob_expertise(d: Dict[str, Any], issues: list, recs: list) -> float:
    """Expertise claims quality: length, specificity, quantity."""
    score = 1.0
    claims = d.get("expertise_claims", [])

    if not claims:
        return 0.0

    # Average claim length (proxy for specificity)
    avg_len = sum(len(str(c)) for c in claims) / len(claims)
    if avg_len < 15:
        score -= 0.30; issues.append("expertise_claims_too_brief")
        recs.append("Expand expertise claims with specific credentials, years, or quantified results.")
    elif avg_len < 40:
        score -= 0.10
        recs.append("Aim for more detailed expertise claims (40+ chars each) for stronger credibility.")

    # Quantity: more claims = more credibility signal
    if len(claims) >= 4:
        score += 0.05
    elif len(claims) < 2:
        score -= 0.10; recs.append("Add at least 2 expertise claims.")

    # Keyword indicators of verified credentials
    credential_keywords = [
        "cfa", "jd", "phd", "mba", "cpa", "years", "chartered", "licensed",
        "certified", "bar", "admitted", "published", "managed", "led",
    ]
    claims_text = " ".join(str(c).lower() for c in claims)
    credential_hits = sum(1 for kw in credential_keywords if kw in claims_text)
    if credential_hits >= 2:
        score += 0.10
    elif credential_hits == 0:
        score -= 0.10; recs.append("Include verifiable credentials (certifications, degrees, years of experience).")

    # Self-reported confidence check
    conf = float(d.get("confidence_score", 0.75))
    if conf < 0.1 or conf > 1.0:
        score -= 0.30; issues.append("confidence_score_out_of_range")
    elif conf > 0.95:
        score -= 0.10
        recs.append("Confidence > 0.95 will be scrutinised — back it up with very strong claims.")

    return round(min(max(score, 0.0), 1.0), 3)


def _score_ob_pricing(d: Dict[str, Any], issues: list, recs: list) -> float:
    """Pricing model and price fields consistent."""
    score = 1.0
    model = str(d.get("pricing_model", "")).lower()
    base_price = d.get("base_price")

    if model not in ("fixed", "quoted", "free"):
        score -= 0.30; issues.append("invalid_pricing_model")
        return round(max(0.0, score), 3)

    if model == "fixed":
        if base_price is None:
            score -= 0.35; issues.append("fixed_pricing_missing_base_price")
            recs.append("Fixed pricing requires a base_price value.")
        elif float(base_price) <= 0:
            score -= 0.40; issues.append("invalid_base_price_zero_or_negative")

    if model == "quoted" and not d.get("quote_notes"):
        score -= 0.15
        recs.append("For quoted pricing, add quote_notes explaining how you scope and price work.")

    if base_price and float(base_price) > 10_000:
        recs.append(f"base_price=${base_price} is unusually high — verify this is correct.")

    return round(min(max(score, 0.0), 1.0), 3)


def _score_ob_category_fit(d: Dict[str, Any], issues: list, recs: list) -> float:
    """Specialization categories plausible and not over-claimed."""
    score = 1.0
    valid_cats = {
        "financial_research", "legal_analysis",
        "market_intelligence", "strategy_business_research",
    }
    cats = d.get("specialization_categories", [])

    if not cats:
        score -= 0.50; issues.append("no_specialization_categories")
        return round(max(0.0, score), 3)

    invalid = [c for c in cats if str(c) not in valid_cats]
    if invalid:
        score -= 0.30; issues.append(f"invalid_categories: {invalid}")

    if len(cats) > 3:
        score -= 0.15
        recs.append("Covering 4 categories suggests shallow specialization; consider narrowing to 1–2.")

    return round(min(max(score, 0.0), 1.0), 3)


def _score_ob_capacity(d: Dict[str, Any], issues: list, recs: list) -> float:
    """Capacity and ETA values realistic."""
    score = 1.0
    cap = d.get("capacity", 10)
    eta = d.get("estimated_minutes", 30)

    try:
        cap = int(cap)
        eta = int(eta)
    except (TypeError, ValueError):
        score -= 0.30; issues.append("non_integer_capacity_or_eta")
        return round(max(0.0, score), 3)

    if cap < 1:
        score -= 0.50; issues.append("capacity_below_minimum")
    elif cap > 100:
        score -= 0.20
        recs.append(f"capacity={cap} is unusually high; auditor will verify.")
    elif cap > 50:
        score -= 0.10
        recs.append(f"capacity={cap} — consider whether this is sustainable.")

    if eta < 1:
        score -= 0.40; issues.append("estimated_minutes_below_minimum")
    elif eta > 10_080:
        score -= 0.20; issues.append("estimated_minutes_exceeds_one_week")

    return round(min(max(score, 0.0), 1.0), 3)


# ===========================================================================
# Reasoning builders (shared narrative for both workflows)
# ===========================================================================

def build_task_audit_reasoning(
    scores: TaskAuditScores,
    passed: bool,
    is_specialist: bool,
    has_generalist_comparison: bool,
    benchmark_winner: Optional[str] = None,
) -> str:
    """Build a human-readable audit reasoning paragraph."""
    agent_type = "specialist" if is_specialist else "generalist"
    parts = [
        f"[{agent_type.upper()} OUTPUT AUDIT]",
        f"Composite: {scores.composite:.0%}.",
        f"Dimensions — Quality: {scores.quality:.0%}, "
        f"Relevance: {scores.relevance:.0%}, "
        f"Completeness: {scores.completeness:.0%}, "
        f"Specificity: {scores.genericity:.0%}.",
        f"{'PASSED' if passed else 'FAILED'} (threshold 70%).",
    ]
    if scores.flags:
        parts.append(f"Flags: {', '.join(scores.flags)}.")
    if has_generalist_comparison and benchmark_winner:
        parts.append(f"Generalist comparison: {benchmark_winner} wins.")
    parts.append("[Mock heuristic scoring — replace with LLM-as-judge for production.]")
    return " ".join(parts)


def build_onboarding_reasoning(
    scores: OnboardingAuditScores,
    seller_name: str,
) -> str:
    """Build a human-readable onboarding review reasoning paragraph."""
    parts = [
        f"[ONBOARDING AUDIT] Seller: {seller_name}.",
        f"Composite: {scores.composite:.0%}.",
        f"Dimensions — Completeness: {scores.completeness:.0%}, "
        f"Expertise: {scores.expertise_credibility:.0%}, "
        f"Pricing: {scores.pricing_clarity:.0%}, "
        f"Category fit: {scores.category_fit:.0%}, "
        f"Capacity: {scores.capacity_realism:.0%}.",
    ]
    if scores.issues:
        parts.append(f"Issues: {', '.join(scores.issues)}.")
    else:
        parts.append("No critical issues found.")
    parts.append("[Mock heuristic scoring — replace with LLM-as-judge for production.]")
    return " ".join(parts)
