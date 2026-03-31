"""
Benchmark Runner.

Orchestrates parallel execution of the generalist alongside the specialist
and calls the comparison engine to produce a BenchmarkComparison record.

Entry point: run_generalist_comparison(task, store, registry) -> ComparisonRunResult

Called from the seller execution route (POST /seller/tasks/{id}/run) after
the specialist completes, when task.generalist_comparison_enabled=True.

Design:
  The runner is a clean boundary between the execution layer (seller routes)
  and the comparison logic. The seller route only needs to call one function
  and handle the result — it doesn't know about scoring dimensions or the
  generalist internals.

State changes made:
  - task.generalist_result  populated from generalist AgentResult
  - BenchmarkComparison     created + stored in store.benchmark_comparisons
  - task.benchmark_comparison_id  set
  - GeneralistProfile.tasks_completed, wins, losses, ties updated

Logging:
  Every step emits a structured ActivityLog entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from ..benchmark.comparison import build_comparison
from ..models.task import BenchmarkComparison, Task
from ..models.user import GeneralistProfile, SellerProfile


@dataclass
class ComparisonRunResult:
    """Outcome of a single generalist comparison run."""
    ran: bool                                    # False if generalist was not run
    comparison: Optional[BenchmarkComparison]    # None if ran=False or error
    generalist_result: Optional[dict]            # Raw generalist output content
    message: str
    error: Optional[str] = None


def run_generalist_comparison(
    task: Task,
    seller_profile: SellerProfile,
    store: Any,             # InMemoryStore — avoid circular import
    registry: Any,          # AgentRegistry — avoid circular import
) -> ComparisonRunResult:
    """
    Run the generalist agent on a task and build a BenchmarkComparison.

    Should be called after specialist execution has populated task.seller_result.

    Args:
        task:           the completed task (seller_result must be set)
        seller_profile: the specialist seller who just ran the task
        store:          InMemoryStore singleton
        registry:       AgentRegistry singleton

    Returns:
        ComparisonRunResult with comparison record (or error if skipped).
    """
    # Guard: skip if not enabled
    if not task.generalist_comparison_enabled:
        return ComparisonRunResult(
            ran=False,
            comparison=None,
            generalist_result=None,
            message="Generalist comparison disabled for this task.",
        )

    # Guard: specialist result must be present
    if not task.seller_result:
        return ComparisonRunResult(
            ran=False,
            comparison=None,
            generalist_result=None,
            message="Specialist result not yet available — cannot run comparison.",
            error="missing_seller_result",
        )

    generalist_agent = registry.get_generalist()
    if not generalist_agent:
        return ComparisonRunResult(
            ran=False,
            comparison=None,
            generalist_result=None,
            message="Generalist agent not registered in registry.",
            error="generalist_not_found",
        )

    generalist_profile: GeneralistProfile = generalist_agent.profile

    # --- Run generalist ---
    store.log(
        event_type="generalist.started",
        entity_type="task",
        entity_id=task.id,
        actor_role="system",
        message=(
            f"Generalist baseline '{generalist_profile.display_name}' "
            f"({generalist_profile.model_identifier}) running on task '{task.title}'"
        ),
        metadata={
            "generalist_id": generalist_profile.id,
            "model": generalist_profile.model_identifier,
            "task_category": str(task.category),
        },
    )

    try:
        gen_agent_result = generalist_agent.run(task)
    except Exception as exc:
        store.log(
            event_type="generalist.error",
            entity_type="task",
            entity_id=task.id,
            actor_role="system",
            message=f"Generalist execution failed for task '{task.title}': {exc}",
        )
        return ComparisonRunResult(
            ran=False,
            comparison=None,
            generalist_result=None,
            message=f"Generalist execution failed: {exc}",
            error=str(exc),
        )

    task.generalist_result = gen_agent_result.content
    task.updated_at = datetime.utcnow()
    store.tasks[task.id] = task

    store.log(
        event_type="generalist.completed",
        entity_type="task",
        entity_id=task.id,
        actor_role="system",
        message=(
            f"Generalist baseline completed for task '{task.title}'. "
            f"Confidence: {gen_agent_result.confidence:.0%}."
        ),
        metadata={
            "generalist_id": generalist_profile.id,
            "confidence": gen_agent_result.confidence,
        },
    )

    # --- Determine specialist cost (from accepted quote if available) ---
    specialist_cost = 0.0
    if task.selected_quote_id and task.selected_quote_id in store.quotes:
        specialist_cost = store.quotes[task.selected_quote_id].proposed_price
    elif seller_profile.base_price:
        specialist_cost = float(seller_profile.base_price)

    # --- Build comparison ---
    store.log(
        event_type="benchmark.scoring_started",
        entity_type="task",
        entity_id=task.id,
        actor_role="system",
        message=f"Scoring specialist vs. generalist for task '{task.title}'",
    )

    comparison = build_comparison(
        task=task,
        seller_profile=seller_profile,
        generalist_profile=generalist_profile,
        seller_result=task.seller_result,
        generalist_result=task.generalist_result,
        specialist_cost=specialist_cost,
    )

    # Persist comparison + update task
    store.benchmark_comparisons[comparison.id] = comparison
    task.benchmark_comparison_id = comparison.id
    task.updated_at = datetime.utcnow()
    store.tasks[task.id] = task

    # Update generalist profile stats
    generalist_profile.tasks_completed += 1
    if comparison.winner == "generalist":
        generalist_profile.wins += 1
    elif comparison.winner == "seller":
        generalist_profile.losses += 1
    else:
        generalist_profile.ties += 1

    # Update generalist rolling benchmark_score (running mean)
    if generalist_profile.benchmark_score is None:
        generalist_profile.benchmark_score = comparison.generalist_score
    else:
        n = generalist_profile.tasks_completed
        generalist_profile.benchmark_score = round(
            (generalist_profile.benchmark_score * (n - 1) + comparison.generalist_score) / n, 3
        )

    store.log(
        event_type="benchmark.completed",
        entity_type="task",
        entity_id=task.id,
        actor_role="system",
        message=(
            f"Benchmark comparison complete for '{task.title}'. "
            f"Winner: {comparison.winner}. "
            f"Specialist {comparison.seller_score:.0%} vs. "
            f"Generalist {comparison.generalist_score:.0%} "
            f"(delta {comparison.delta:+.3f}). "
            f"{comparison.recommendation}."
        ),
        metadata={
            "comparison_id": comparison.id,
            "winner": comparison.winner,
            "seller_score": comparison.seller_score,
            "generalist_score": comparison.generalist_score,
            "delta": comparison.delta,
            "recommendation": comparison.recommendation,
            "specialist_cost": comparison.specialist_cost,
            "generalist_cost": comparison.generalist_cost,
        },
    )

    return ComparisonRunResult(
        ran=True,
        comparison=comparison,
        generalist_result=task.generalist_result,
        message=(
            f"Benchmark complete. Winner: {comparison.winner}. "
            f"Specialist {comparison.seller_score:.0%} vs. Generalist {comparison.generalist_score:.0%}."
        ),
    )
