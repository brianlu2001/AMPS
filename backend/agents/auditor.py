"""
Auditor agent — governance and evaluation layer.

The auditor is NOT a marketplace seller. It is a governance-level agent
that validates the quality of:
  1. Seller onboarding submissions (expertise + profile completeness)
  2. Task output quality (specialist + optional generalist comparison)

Two workflow entry points:
  audit_task(task)                    → AuditResult   (task output audit)
  audit_seller_onboarding(profile, store) → SellerOnboardingReview  (onboarding audit)

Admin override is supported for both workflows via admin API routes.

Design:
  The agent is a thin orchestrator over auditor/scoring.py.
  All scoring logic lives in the scoring module — the agent handles:
    - Calling the right scorer
    - Building the result models
    - Updating profile counters
    - Returning typed results (not raw dicts)

Future: replace scoring.py heuristics with LLM-as-judge calls.
The agent interface (audit_task, audit_seller_onboarding) stays identical.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..auditor.scoring import (
    QUALITY_THRESHOLD,
    ONBOARDING_AUTO_APPROVE_THRESHOLD,
    build_onboarding_reasoning,
    build_task_audit_reasoning,
    score_seller_onboarding,
    score_task_output,
)
from ..models.enums import ApprovalStatus, TaskCategory
from ..models.task import AuditResult, BenchmarkComparison, SellerOnboardingReview, Task
from ..models.user import AuditorProfile, SellerProfile
from .base import AgentResult, BaseAgent


class AuditorAgent(BaseAgent):
    """
    Auditor agent. Thin orchestrator over the scoring engine.

    One auditor instance covers all categories by default.
    AuditorProfile.specialization_categories can restrict scope.
    """

    def __init__(self, agent_id: str, profile: AuditorProfile):
        super().__init__(agent_id=agent_id, name=profile.display_name)
        self.profile = profile

    # ------------------------------------------------------------------
    # BaseAgent.run() — satisfies interface; orchestrates both workflows
    # ------------------------------------------------------------------

    def run(self, task: Task) -> AgentResult:
        """
        Run a full task output audit. Optionally compare with generalist result.

        Called by the audit route (POST /audit/tasks/{id}).
        Returns an AgentResult wrapping both AuditResult and BenchmarkComparison.
        """
        audit = self.audit_task(task)
        benchmark = None
        if task.generalist_result and task.seller_result:
            benchmark = self.compare_results(task)

        return AgentResult(
            agent_id=self.agent_id,
            task_id=task.id,
            success=True,
            content={
                "audit_result": audit.dict(),
                "benchmark_comparison": benchmark.dict() if benchmark else None,
            },
            confidence=0.85,
            reasoning=(
                f"Auditor completed task output audit. "
                f"Score: {audit.composite_score:.0%}. "
                f"Passed: {audit.passed}."
            ),
        )

    # ------------------------------------------------------------------
    # Workflow A: Task output audit
    # ------------------------------------------------------------------

    def audit_task(self, task: Task) -> AuditResult:
        """
        Score a completed task's seller output across four dimensions:
          quality, relevance, completeness, genericity (specificity).

        Also records benchmark context if generalist comparison exists.

        MVP: deterministic heuristic scoring via auditor/scoring.py.
        Future: replace score_task_output() with LLM-as-judge call.
        """
        if not task.seller_result:
            return AuditResult(
                id=str(uuid.uuid4()),
                task_id=task.id,
                auditor_id=self.profile.id,
                composite_score=0.0,
                quality_score=0.0,
                passed=False,
                dimension_scores={},
                reasoning="No seller result found to audit.",
                flags=["missing_seller_result"],
                scoring_method=self.profile.scoring_method,
                audited_at=datetime.utcnow(),
            )

        scores = score_task_output(
            result=task.seller_result,
            task_description=task.description,
            task_category=str(task.category),
            requested_output_type=str(task.requested_output_type),
            is_specialist=True,
        )

        passed = scores.composite >= QUALITY_THRESHOLD

        # Benchmark context (if comparison already run by the benchmark runner)
        benchmark_winner: Optional[str] = None
        benchmark_id: Optional[str] = None
        benchmark_delta: Optional[float] = None
        has_benchmark = bool(task.benchmark_comparison_id)
        if task.benchmark_comparison_id:
            benchmark_id = task.benchmark_comparison_id
            # Retrieve benchmark data from store to enrich reasoning
            try:
                from ..store import store as _store
                bc = _store.benchmark_comparisons.get(task.benchmark_comparison_id)
                if bc:
                    benchmark_winner = bc.winner
                    benchmark_delta = bc.delta
            except Exception:
                pass

        reasoning = build_task_audit_reasoning(
            scores=scores,
            passed=passed,
            is_specialist=True,
            has_generalist_comparison=has_benchmark,
            benchmark_winner=benchmark_winner,
        )

        # Update auditor profile counters
        self.profile.audits_completed += 1
        n = self.profile.audits_completed
        prev = self.profile.avg_task_quality_score or 0.0
        self.profile.avg_task_quality_score = round(
            (prev * (n - 1) + scores.composite) / n, 3
        )
        generic_flag = 1 if "highly_generic_output" in scores.flags else 0
        prev_rate = self.profile.avg_genericity_flag_rate or 0.0
        self.profile.avg_genericity_flag_rate = round(
            (prev_rate * (n - 1) + generic_flag) / n, 3
        )

        return AuditResult(
            id=str(uuid.uuid4()),
            task_id=task.id,
            auditor_id=self.profile.id,
            composite_score=scores.composite,
            quality_score=scores.composite,   # Alias for backwards compat
            passed=passed,
            dimension_scores=scores.to_dict(),
            reasoning=reasoning,
            flags=scores.flags,
            recommendations=scores.recommendations,
            has_benchmark=has_benchmark,
            benchmark_comparison_id=benchmark_id,
            benchmark_winner=benchmark_winner,
            benchmark_delta=benchmark_delta,
            scoring_method=self.profile.scoring_method,
            audited_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Workflow B: Seller onboarding audit
    # ------------------------------------------------------------------

    def audit_seller_onboarding(
        self,
        profile: SellerProfile,
        store: Any = None,  # InMemoryStore; optional for legacy callers
    ) -> SellerOnboardingReview:
        """
        Evaluate a seller's onboarding profile and return a SellerOnboardingReview.

        If a review record already exists in the store for this seller
        (created at registration time), update it rather than creating a new one.
        Otherwise, create and return a new review.

        If store is provided, the review is persisted and the seller's
        approval_status is updated accordingly.

        MVP: deterministic heuristic scoring via auditor/scoring.py.
        Future: replace score_seller_onboarding() with LLM-as-judge.
        """
        scores = score_seller_onboarding(profile.dict())
        passed = scores.composite >= ONBOARDING_AUTO_APPROVE_THRESHOLD and not scores.issues

        if passed:
            review_status = "approved"
            recommendation = "approve"
        elif scores.composite < 0.50 or len(scores.issues) >= 3:
            review_status = "rejected"
            recommendation = "reject"
        elif scores.issues:
            review_status = "needs_review"
            recommendation = "needs_more_info"
        else:
            review_status = "approved"
            recommendation = "approve"

        reasoning = build_onboarding_reasoning(scores, profile.display_name)
        now = datetime.utcnow()

        # Check for existing review in store
        existing_review: Optional[SellerOnboardingReview] = None
        if store:
            existing_review = store.get_onboarding_review_for_seller(profile.id)

        review_id = (existing_review.id if existing_review
                     else (profile.onboarding_review_id or str(uuid.uuid4())))

        review = SellerOnboardingReview(
            id=review_id,
            seller_profile_id=profile.id,
            auditor_id=self.profile.id,
            review_status=review_status,
            overall_score=scores.composite,
            dimension_scores=scores.to_dict(),
            passed=passed,
            issues=scores.issues,
            recommendations=scores.recommendations,
            reasoning=reasoning,
            auditor_comment=None,
            reviewed_at=now,
            created_at=existing_review.created_at if existing_review else now,
        )

        # Update approval status if store is provided
        if store:
            store.seller_onboarding_reviews[review.id] = review
            if review_status == "approved":
                profile.approval_status = ApprovalStatus.APPROVED
                profile.approved_at = now
            elif review_status == "rejected":
                profile.approval_status = ApprovalStatus.REJECTED
                profile.rejected_at = now
            else:
                profile.approval_status = ApprovalStatus.NEEDS_REVIEW
            profile.onboarding_review_id = review.id
            store.sellers[profile.id] = profile

            store.log(
                event_type="seller.onboarding_audited",
                entity_type="seller",
                entity_id=profile.id,
                actor_id=self.agent_id,
                actor_role="auditor",
                message=(
                    f"Onboarding audit {'PASSED' if passed else 'FAILED/QUEUED'} "
                    f"for '{profile.display_name}'. "
                    f"Score: {scores.composite:.0%}. "
                    f"Recommendation: {recommendation}."
                ),
                metadata={
                    "review_id": review.id,
                    "overall_score": scores.composite,
                    "recommendation": recommendation,
                    "issues": scores.issues,
                },
            )

        # Update auditor profile onboarding counters
        self.profile.onboarding_reviews_completed += 1
        n = self.profile.onboarding_reviews_completed
        prev = self.profile.avg_onboarding_score or 0.0
        self.profile.avg_onboarding_score = round(
            (prev * (n - 1) + scores.composite) / n, 3
        )

        return review

    # ------------------------------------------------------------------
    # Benchmark comparison (delegates to benchmark/comparison.py)
    # ------------------------------------------------------------------

    def compare_results(self, task: Task) -> BenchmarkComparison:
        """
        Compare seller vs. generalist results. Delegates to benchmark engine.
        Called after both seller_result and generalist_result are set on a task.
        """
        from ..benchmark.comparison import build_comparison
        from ..agents.registry import registry

        if not task.seller_result or not task.generalist_result:
            return BenchmarkComparison(
                id=str(uuid.uuid4()),
                task_id=task.id,
                seller_id=task.selected_seller_id or "unknown",
                generalist_id="unknown",
                seller_score=0.0,
                generalist_score=0.0,
                winner="tie",
                delta=0.0,
                recommendation="insufficient_data",
                summary="Comparison skipped: one or both results are missing.",
                scoring_method="skipped",
                mock=True,
                created_at=datetime.utcnow(),
            )

        generalist_agent = registry.get_generalist()
        generalist_profile = generalist_agent.profile if generalist_agent else None

        from ..store import store as _store
        seller_id = task.selected_seller_id
        seller_profile = (
            (_store.sellers.get(seller_id) if seller_id else None)
            or (registry.get_seller(seller_id).profile
                if seller_id and registry.get_seller(seller_id)
                else None)
        )

        if not seller_profile or not generalist_profile:
            seller_score, gen_score = 0.78, 0.63
            delta = round(seller_score - gen_score, 3)
            return BenchmarkComparison(
                id=str(uuid.uuid4()),
                task_id=task.id,
                seller_id=seller_id or "unknown",
                generalist_id=generalist_profile.id if generalist_profile else "unknown",
                seller_score=seller_score,
                generalist_score=gen_score,
                winner="seller",
                delta=delta,
                recommendation="use_specialist",
                summary=(
                    f"[FALLBACK] Profiles not resolved. "
                    f"Estimated specialist {seller_score:.0%} vs generalist {gen_score:.0%}."
                ),
                scoring_method="fallback_estimate",
                mock=True,
                created_at=datetime.utcnow(),
            )

        specialist_cost = float(seller_profile.base_price or 0.0)
        if task.selected_quote_id and task.selected_quote_id in _store.quotes:
            specialist_cost = _store.quotes[task.selected_quote_id].proposed_price

        return build_comparison(
            task=task,
            seller_profile=seller_profile,
            generalist_profile=generalist_profile,
            seller_result=task.seller_result,
            generalist_result=task.generalist_result,
            specialist_cost=specialist_cost,
        )

    def describe(self) -> Dict[str, Any]:
        base = super().describe()
        base.update({
            "specialization_categories": self.profile.specialization_categories,
            "audits_completed":           self.profile.audits_completed,
            "onboarding_reviews_completed": self.profile.onboarding_reviews_completed,
            "override_count":             self.profile.override_count,
            "scoring_method":             self.profile.scoring_method,
            "avg_task_quality_score":     self.profile.avg_task_quality_score,
            "avg_onboarding_score":       self.profile.avg_onboarding_score,
        })
        return base
