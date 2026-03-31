"""
Marketplace Workflow Orchestrator.

This module coordinates the full task lifecycle from submission through
seller selection. It is the single entry point for all marketplace logic.

Workflow stages:

  Stage 1 — SUBMIT
    Task is stored with status=PENDING.
    Marketplace matching is triggered immediately.

  Stage 2 — MATCH
    run_matching() scores all sellers and returns a ranked shortlist.
    shortlisted_seller_ids and marketplace_run_at are written to the task.

  Stage 3 — QUOTE
    A Quote is generated for each shortlisted seller.
    Quotes are persisted in store.quotes.
    Task.quote_ids is populated.
    Task status → PENDING (stays pending until buyer selects).

  Stage 4 — SELECT
    Buyer calls select_seller(task_id, seller_id).
    The matching quote is marked accepted=True.
    Task.selected_seller_id and Task.selected_quote_id are set.
    Task status → ASSIGNED.

  (Stage 5 — EXECUTE is handled by seller routes POST /seller/tasks/{id}/run)

All intermediate state is preserved and returned in MarketplaceResult
so the observability console can display the full trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.enums import ApprovalStatus, TaskStatus
from ..models.task import Quote, Task
from ..models.user import SellerProfile
from .matching import MatchingResult, run_matching
from .quoting import generate_quotes_for_shortlist


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class MarketplaceResult:
    """
    Complete record of a marketplace matching + quoting run.
    Returned by run_marketplace() and used in API responses.
    """
    task_id: str
    success: bool
    message: str

    # Matching output
    matching: Optional[MatchingResult] = None
    shortlisted_count: int = 0
    shortlisted_sellers: List[Dict[str, Any]] = field(default_factory=list)

    # Generated quotes (one per shortlisted seller)
    quotes: List[Quote] = field(default_factory=list)

    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "message": self.message,
            "shortlisted_count": self.shortlisted_count,
            "shortlisted_sellers": self.shortlisted_sellers,
            "quotes": [q.dict() for q in self.quotes],
            "matching_notes": self.matching.notes if self.matching else [],
            "warnings": self.warnings,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Stage 2+3: Run marketplace matching and generate quotes
# ---------------------------------------------------------------------------

def run_marketplace(
    task: Task,
    store: Any,               # InMemoryStore — avoid circular import
    max_shortlist: int = 3,
) -> MarketplaceResult:
    """
    Run the marketplace matching + quoting pipeline for a task.

    Called automatically when a task is created (stage 1), and can be
    re-triggered via POST /buyer/tasks/{id}/marketplace to refresh quotes.

    Args:
        task:          the Task to match and quote for
        store:         the InMemoryStore singleton
        max_shortlist: maximum number of sellers to shortlist

    Returns:
        MarketplaceResult with matching trace and quotes.
    """
    warnings: list[str] = []

    # --- Build inputs ---
    all_seller_profiles: List[SellerProfile] = list(store.sellers.values())
    if not all_seller_profiles:
        # Fall back to registry sellers if store.sellers is empty
        # (happens when registry is seeded but seed_demo_profiles hasn't run)
        from ..agents.registry import registry
        all_seller_profiles = [a.profile for a in registry.list_sellers()]

    if not all_seller_profiles:
        return MarketplaceResult(
            task_id=task.id,
            success=False,
            message="No seller profiles available for matching.",
            error="no_sellers",
        )

    # Compute current task loads: {seller_id: count of IN_PROGRESS tasks}
    task_loads: Dict[str, int] = {}
    for t in store.tasks.values():
        if t.selected_seller_id and str(t.status) == TaskStatus.IN_PROGRESS:
            task_loads[t.selected_seller_id] = task_loads.get(t.selected_seller_id, 0) + 1

    # --- Stage 2: Run matching ---
    matching = run_matching(
        task=task,
        sellers=all_seller_profiles,
        task_loads=task_loads,
        max_shortlist=max_shortlist,
    )
    warnings.extend(matching.notes)

    if not matching.shortlisted:
        return MarketplaceResult(
            task_id=task.id,
            success=False,
            message=(
                f"No eligible sellers found for category '{task.category}'. "
                "No quotes generated."
            ),
            matching=matching,
            warnings=warnings,
            error="no_eligible_sellers",
        )

    # --- Stage 3: Generate quotes ---
    profiles_by_id = {p.id: p for p in all_seller_profiles}
    quotes = generate_quotes_for_shortlist(
        task=task,
        profiles_by_id=profiles_by_id,
        matches=matching.shortlisted,
    )

    # --- Persist quotes and update task ---
    for quote in quotes:
        store.quotes[quote.id] = quote
        if quote.id not in task.quote_ids:
            task.quote_ids.append(quote.id)

    task.shortlisted_seller_ids = [m.seller_id for m in matching.shortlisted]
    task.marketplace_run_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    store.tasks[task.id] = task

    # --- Structured shortlist for API response ---
    shortlisted_sellers = [
        {
            "seller_id": m.seller_id,
            "seller_name": m.seller_name,
            "match_score": m.match_score,
            "score_breakdown": m.score_breakdown,
            "weighted_breakdown": m.weighted_breakdown,
            "fit_explanation": m.fit_explanation,
        }
        for m in matching.shortlisted
    ]

    message = (
        f"Marketplace matched {len(quotes)} seller(s) for task '{task.title}'. "
        f"Best match: {matching.shortlisted[0].seller_name} "
        f"(score {matching.shortlisted[0].match_score:.0%})."
    )

    return MarketplaceResult(
        task_id=task.id,
        success=True,
        message=message,
        matching=matching,
        shortlisted_count=len(quotes),
        shortlisted_sellers=shortlisted_sellers,
        quotes=quotes,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Stage 4: Seller selection
# ---------------------------------------------------------------------------

@dataclass
class SelectionResult:
    success: bool
    task: Optional[Task]
    quote: Optional[Quote]
    message: str
    error: Optional[str] = None


def select_seller(
    task_id: str,
    seller_id: str,
    store: Any,
) -> SelectionResult:
    """
    Select a seller for a task by accepting their quote.

    Rules:
      - Task must be in PENDING state (not already assigned).
      - seller_id must be in task.shortlisted_seller_ids.
      - A quote from that seller must exist for this task.

    Actions:
      - Marks the quote accepted=True.
      - Sets task.selected_seller_id and task.selected_quote_id.
      - Advances task.status to ASSIGNED.
      - Emits log events.

    Returns SelectionResult.
    """
    task = store.tasks.get(task_id)
    if not task:
        return SelectionResult(
            success=False, task=None, quote=None,
            message=f"Task {task_id} not found.", error="task_not_found",
        )

    if str(task.status) not in (TaskStatus.PENDING, "pending"):
        return SelectionResult(
            success=False, task=task, quote=None,
            message=(
                f"Task is already in status '{task.status}' and cannot be re-assigned. "
                "Only PENDING tasks can have a seller selected."
            ),
            error="task_not_pending",
        )

    if task.shortlisted_seller_ids and seller_id not in task.shortlisted_seller_ids:
        return SelectionResult(
            success=False, task=task, quote=None,
            message=(
                f"Seller {seller_id} was not shortlisted for this task. "
                f"Shortlisted sellers: {task.shortlisted_seller_ids}"
            ),
            error="seller_not_shortlisted",
        )

    # Find the quote from this seller for this task
    quote = next(
        (
            store.quotes[qid]
            for qid in task.quote_ids
            if qid in store.quotes and store.quotes[qid].seller_id == seller_id
        ),
        None,
    )
    if not quote:
        return SelectionResult(
            success=False, task=task, quote=None,
            message=f"No quote found from seller {seller_id} for task {task_id}.",
            error="quote_not_found",
        )

    # Mark quote accepted, reject others
    for qid in task.quote_ids:
        if qid in store.quotes:
            store.quotes[qid].accepted = (qid == quote.id)

    # Update task
    task.selected_seller_id = seller_id
    task.selected_quote_id = quote.id
    task.status = TaskStatus.ASSIGNED
    task.updated_at = datetime.utcnow()
    store.tasks[task.id] = task

    seller_name = quote.seller_display_name or seller_id
    return SelectionResult(
        success=True,
        task=task,
        quote=quote,
        message=(
            f"Seller '{seller_name}' selected for task '{task.title}'. "
            f"Price: ${quote.proposed_price:.2f}, ETA: {quote.estimated_minutes}min. "
            f"Task status → ASSIGNED."
        ),
    )
