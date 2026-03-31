"""
Buyer API routes.

Access control:
  - POST /buyer/onboard                  — authenticated (any role)
  - POST /buyer/tasks                    — buyer or admin
  - GET  /buyer/tasks                    — buyer (own) or admin (all)
  - GET  /buyer/tasks/{id}               — buyer (own) or admin
  - GET  /buyer/tasks/{id}/quotes        — buyer (own task) or admin
  - GET  /buyer/tasks/{id}/marketplace   — buyer (own task) or admin
  - POST /buyer/tasks/{id}/marketplace   — buyer (own task) or admin (re-run matching)
  - POST /buyer/tasks/{id}/select-seller — buyer (own task) or admin

Marketplace flow (auto-triggered on task creation):
  1. Task created → run_marketplace() called immediately.
  2. Matching engine scores all approved sellers.
  3. Quotes generated for shortlisted sellers.
  4. Buyer views quotes via GET /buyer/tasks/{id}/quotes.
  5. Buyer selects seller via POST /buyer/tasks/{id}/select-seller.
  6. Task status → ASSIGNED.
  7. Seller executes via POST /seller/tasks/{id}/run.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...agents.buyer import BuyerAgent
from ...auth.deps import get_current_user, require_buyer_or_admin
from ...marketplace.workflow import run_marketplace, select_seller
from ...models.enums import OutputType, TaskCategory, UserRole
from ...models.task import Quote, Task
from ...models.user import BuyerProfile, User
from ...onboarding.enrollment import OnboardingValidationError, run_onboarding
from ...store import store

router = APIRouter(prefix="/buyer", tags=["buyer"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class OnboardBuyerRequest(BaseModel):
    instruction: str = "Read this link and enroll me as a buyer agent."
    url: Optional[str] = None


class CreateTaskRequest(BaseModel):
    buyer_id: str
    title: str
    description: str
    category: TaskCategory
    requested_output_type: OutputType = OutputType.REPORT
    context_url: Optional[str] = None
    enable_generalist_comparison: bool = True


class SelectSellerRequest(BaseModel):
    seller_id: str


# ---------------------------------------------------------------------------
# Helper: resolve buyer profile from authenticated user
# ---------------------------------------------------------------------------

def _get_buyer_profile(current_user: User):
    return next(
        (b for b in store.buyers.values() if b.user_id == current_user.id), None
    )


def _assert_task_owned_by_buyer(task: Task, current_user: User):
    """Raise 403 if a buyer tries to access another buyer's task."""
    if str(current_user.role) != UserRole.BUYER:
        return   # Admins pass through
    buyer_profile = _get_buyer_profile(current_user)
    if not buyer_profile or task.buyer_id != buyer_profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: this task belongs to a different buyer",
        )


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

@router.post("/onboard", response_model=Dict[str, Any])
def onboard_buyer(
    req: OnboardBuyerRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Onboard the authenticated user as a buyer agent via natural-language instruction.

    Runs 4-stage pipeline: parse → fetch URL → extract profile → enroll.
    Returns full OnboardingResult with pipeline trace.
    """
    try:
        result = run_onboarding(
            instruction=req.instruction,
            url=req.url,
            user_id=current_user.id,
            store=store,
        )
    except OnboardingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Onboarding pipeline error: {exc}")
    return result.to_dict()


# ---------------------------------------------------------------------------
# Task creation (triggers marketplace automatically)
# ---------------------------------------------------------------------------

@router.post("/tasks", response_model=Dict[str, Any])
def create_task(
    req: CreateTaskRequest,
    current_user: User = Depends(require_buyer_or_admin),
):
    """
    Submit a new task. Immediately runs marketplace matching and generates quotes.

    Role check: buyer or admin only.
    Buyers can only create tasks under their own buyer_id.

    Returns:
        {
          "task": Task,
          "marketplace": MarketplaceResult (shortlisted sellers + quotes)
        }
    """
    buyer_profile = store.buyers.get(req.buyer_id)
    if not buyer_profile:
        raise HTTPException(status_code=404, detail=f"Buyer {req.buyer_id} not found")

    if str(current_user.role) == UserRole.BUYER and buyer_profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Buyers can only create tasks under their own buyer profile",
        )

    # Build task
    agent = BuyerAgent(agent_id=buyer_profile.user_id, profile=buyer_profile)
    task = agent.create_task(
        title=req.title,
        description=req.description,
        category=req.category,
        requested_output_type=req.requested_output_type,
        context_url=req.context_url,
        enable_generalist_comparison=req.enable_generalist_comparison,
    )
    store.tasks[task.id] = task

    store.log(
        event_type="task.submitted",
        entity_type="task",
        entity_id=task.id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=f"Task submitted: '{task.title}' [{task.category}]",
        metadata={
            "category": str(task.category),
            "output_type": str(task.requested_output_type),
        },
    )

    # Run marketplace matching immediately
    marketplace_result = run_marketplace(task=task, store=store)

    _log_marketplace_events(task, marketplace_result, store)

    return {
        "task": task.dict(),
        "marketplace": marketplace_result.to_dict(),
    }


# ---------------------------------------------------------------------------
# Task retrieval
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}", response_model=Task)
def get_task(
    task_id: str,
    current_user: User = Depends(require_buyer_or_admin),
):
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_task_owned_by_buyer(task, current_user)
    return task


@router.get("/tasks", response_model=List[Task])
def list_tasks(
    buyer_id: Optional[str] = None,
    current_user: User = Depends(require_buyer_or_admin),
):
    """
    List tasks. Buyer sees only their own; admin sees all or filters by buyer_id.
    """
    if str(current_user.role) == UserRole.BUYER:
        buyer_profile = _get_buyer_profile(current_user)
        if not buyer_profile:
            return []
        return store.get_tasks_for_buyer(buyer_profile.id)
    if buyer_id:
        return store.get_tasks_for_buyer(buyer_id)
    return list(store.tasks.values())


# ---------------------------------------------------------------------------
# Marketplace quotes
# ---------------------------------------------------------------------------

@router.get("/tasks/{task_id}/quotes", response_model=List[Quote])
def get_task_quotes(
    task_id: str,
    current_user: User = Depends(require_buyer_or_admin),
):
    """
    Return all quotes for a task, ordered by match_score descending (best first).
    Each quote includes match_score, fit_explanation, and score_breakdown.
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_task_owned_by_buyer(task, current_user)
    return store.get_quotes_for_task(task_id)


@router.get("/tasks/{task_id}/marketplace", response_model=Dict[str, Any])
def get_marketplace_state(
    task_id: str,
    current_user: User = Depends(require_buyer_or_admin),
):
    """
    Full marketplace state for a task: quotes, shortlisted sellers, selection status.
    Useful as the primary data source for the buyer's task-detail view.
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_task_owned_by_buyer(task, current_user)

    quotes = store.get_quotes_for_task(task_id)

    return {
        "task_id": task_id,
        "task_status": task.status,
        "marketplace_run_at": task.marketplace_run_at.isoformat() if task.marketplace_run_at else None,
        "shortlisted_seller_ids": task.shortlisted_seller_ids,
        "selected_seller_id": task.selected_seller_id,
        "selected_quote_id": task.selected_quote_id,
        "quotes": [q.dict() for q in quotes],
        "quote_count": len(quotes),
    }


@router.post("/tasks/{task_id}/marketplace", response_model=Dict[str, Any])
def refresh_marketplace(
    task_id: str,
    current_user: User = Depends(require_buyer_or_admin),
):
    """
    Re-run marketplace matching for a task.

    Useful when:
      - New sellers registered since task was created.
      - Task was submitted before any sellers existed.
      - Buyer wants fresh quotes with updated seller scores.

    Only allowed on PENDING tasks (not yet assigned).
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_task_owned_by_buyer(task, current_user)

    if str(task.status) not in ("pending",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refresh marketplace for a task in status '{task.status}'. "
                   "Only PENDING tasks can be re-matched.",
        )

    result = run_marketplace(task=task, store=store)
    _log_marketplace_events(task, result, store)
    store.log(
        event_type="marketplace.refreshed",
        entity_type="task",
        entity_id=task_id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=f"Marketplace re-run for task '{task.title}'. {result.message}",
    )
    return result.to_dict()


# ---------------------------------------------------------------------------
# Seller selection
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/select-seller", response_model=Dict[str, Any])
def select_seller_for_task(
    task_id: str,
    req: SelectSellerRequest,
    current_user: User = Depends(require_buyer_or_admin),
):
    """
    Accept a quote and assign a seller to a task.

    Validates that:
      - Task is PENDING.
      - Seller was shortlisted for this task.
      - A quote from that seller exists.

    Sets task status → ASSIGNED.
    The next step is POST /seller/tasks/{task_id}/run to execute the task.
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    _assert_task_owned_by_buyer(task, current_user)

    result = select_seller(
        task_id=task_id,
        seller_id=req.seller_id,
        store=store,
    )

    if not result.success:
        status_code = {
            "task_not_found": 404,
            "task_not_pending": 409,
            "seller_not_shortlisted": 400,
            "quote_not_found": 404,
        }.get(result.error or "", 400)
        raise HTTPException(status_code=status_code, detail=result.message)

    store.log(
        event_type="seller.selected",
        entity_type="task",
        entity_id=task_id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=result.message,
        metadata={
            "seller_id": req.seller_id,
            "quote_id": result.quote.id if result.quote else None,
            "price": result.quote.proposed_price if result.quote else None,
            "eta_minutes": result.quote.estimated_minutes if result.quote else None,
        },
    )

    return {
        "success": True,
        "message": result.message,
        "task": result.task.dict() if result.task else None,
        "accepted_quote": result.quote.dict() if result.quote else None,
    }


# ---------------------------------------------------------------------------
# Internal log helper
# ---------------------------------------------------------------------------

def _log_marketplace_events(task: Task, result: Any, store: Any) -> None:
    """Emit structured activity log entries for each marketplace stage."""
    if not result.success:
        store.log(
            event_type="marketplace.no_matches",
            entity_type="task",
            entity_id=task.id,
            actor_role="system",
            message=f"No sellers matched for task '{task.title}': {result.error}",
        )
        return

    # Shortlisting event
    seller_names = [s["seller_name"] for s in result.shortlisted_sellers]
    store.log(
        event_type="marketplace.shortlisted",
        entity_type="task",
        entity_id=task.id,
        actor_role="system",
        message=(
            f"Sellers shortlisted for '{task.title}': "
            f"{', '.join(seller_names)}"
        ),
        metadata={
            "shortlisted_count": result.shortlisted_count,
            "seller_scores": {
                s["seller_name"]: s["match_score"]
                for s in result.shortlisted_sellers
            },
        },
    )

    # Per-quote event
    for quote in result.quotes:
        store.log(
            event_type="quote.generated",
            entity_type="quote",
            entity_id=quote.id,
            actor_role="system",
            message=(
                f"Quote from '{quote.seller_display_name}' for '{task.title}': "
                f"${quote.proposed_price:.2f}, {quote.estimated_minutes}min, "
                f"match {quote.match_score:.0%}"
            ),
            metadata={
                "seller_id": quote.seller_id,
                "price": quote.proposed_price,
                "eta_minutes": quote.estimated_minutes,
                "match_score": quote.match_score,
                "score_breakdown": quote.score_breakdown,
            },
        )
