"""
Seller API routes.

Access control:
  - POST /seller/register          — authenticated user (any role can register as seller)
  - GET  /seller/register/status   — seller (own status) or admin
  - GET  /seller/agents            — any authenticated user (marketplace discovery)
  - GET  /seller/agents/{id}       — any authenticated user
  - GET  /seller/tasks             — seller (own) or admin
  - POST /seller/tasks/{id}/quote  — seller (own profile) or admin
  - POST /seller/tasks/{id}/run    — seller (own profile) or admin

Seller onboarding:
  POST /seller/register runs the registration pipeline:
    1. Validates all fields
    2. Builds a SellerProfile
    3. Triggers auditor review scoring (auto-approve if score >= threshold)
    4. Persists profile and registers agent in the execution registry
    5. Returns RegistrationResult with pipeline trace
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...agents.registry import registry
from ...auth.deps import get_current_user, require_seller_or_admin
from ...benchmark.runner import run_generalist_comparison
from ...models.enums import ApprovalStatus, TaskStatus, UserRole
from ...models.task import Quote, Task
from ...models.user import User
from ...seller_onboarding.registration import run_seller_registration
from ...store import store

router = APIRouter(prefix="/seller", tags=["seller"])


# ---------------------------------------------------------------------------
# Registration request schema
# ---------------------------------------------------------------------------

class SellerRegistrationRequest(BaseModel):
    """
    Seller registration payload. All fields map directly to SellerProfile fields.
    Validation is performed in seller_onboarding/validation.py.
    """
    display_name: str
    description: str
    specialization_categories: List[str]   # e.g. ["financial_research", "legal_analysis"]
    supported_output_types: List[str]       # e.g. ["report", "summary"]
    pricing_model: str                      # "fixed" | "quoted"
    base_price: Optional[float] = None      # Required for pricing_model="fixed"
    quote_notes: Optional[str] = None       # Optional for pricing_model="quoted"
    estimated_minutes: int = 30
    capacity: int = 10
    confidence_score: float = 0.75
    expertise_claims: List[str] = []        # Freeform capability statements
    benchmark_references: List[dict] = []   # Optional evidence of prior work
    website_url: Optional[str] = None
    contact_email: Optional[str] = None
    agent_type: str = "mock"                # "mock" | "external_api" (future)
    external_agent_api_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Registration endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=Dict[str, Any])
def register_seller(
    req: SellerRegistrationRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Register as a specialized seller agent.

    Runs the full seller onboarding pipeline:
      1. Field validation
      2. SellerProfile creation
      3. Auditor review scoring (auto-approve if score ≥ 80%)
      4. Agent registration in execution registry
      5. Activity log entry

    Returns a RegistrationResult with the profile, review scores, and next steps.

    Any authenticated user may register as a seller.
    Existing sellers cannot re-register (returns 409 with existing profile).
    """
    result = run_seller_registration(
        request=req.dict(),
        user_id=current_user.id,
        store=store,
        registry=registry,
    )
    # Return 409 on duplicate rather than 200 with success=False
    if not result.success and result.error == "duplicate_registration":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.message,
        )
    return result.to_dict()


@router.get("/register/status", response_model=Dict[str, Any])
def get_registration_status(
    current_user: User = Depends(require_seller_or_admin),
):
    """
    Get the current seller's registration and review status.

    Seller: sees their own profile and review record.
    Admin: must pass ?seller_id= query param (see /admin/sellers endpoint).
    """
    if str(current_user.role) == UserRole.SELLER:
        profile = next(
            (s for s in store.sellers.values() if s.user_id == current_user.id), None
        )
        if not profile:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No seller profile found for your account. "
                    "Register first via POST /seller/register"
                ),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins should use GET /admin/sellers for seller status.",
        )

    review = store.get_onboarding_review_for_seller(profile.id)
    return {
        "seller_profile": profile.dict(),
        "onboarding_review": review.dict() if review else None,
        "approval_status": profile.approval_status,
        "is_active": profile.approval_status == ApprovalStatus.APPROVED,
    }


@router.get("/agents", response_model=List[Dict[str, Any]])
def list_sellers(current_user: User = Depends(get_current_user)):
    """
    List all registered seller agents and their capability profiles.
    Any authenticated user can browse the seller marketplace.
    """
    return [agent.describe() for agent in registry.list_sellers()]


@router.get("/agents/{seller_id}", response_model=Dict[str, Any])
def get_seller(seller_id: str, current_user: User = Depends(get_current_user)):
    """Get a specific seller agent's profile. Any authenticated user."""
    agent = registry.get_seller(seller_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Seller {seller_id} not found")
    return agent.describe()


@router.get("/tasks", response_model=List[Dict[str, Any]])
def list_seller_tasks(
    seller_id: Optional[str] = None,
    current_user: User = Depends(require_seller_or_admin),
):
    """
    List tasks for a seller.

    - Seller: sees only their own assigned tasks (seller_id param ignored).
    - Admin: sees all assigned tasks, or filtered by seller_id.
    """
    if str(current_user.role) == UserRole.SELLER:
        # Resolve seller profile from current user
        seller_profile = next(
            (s for s in store.sellers.values() if s.user_id == current_user.id), None
        )
        if not seller_profile:
            return []
        return [t.dict() for t in store.get_tasks_for_seller(seller_profile.id)]

    # Admin path
    if seller_id:
        return [t.dict() for t in store.get_tasks_for_seller(seller_id)]
    return [t.dict() for t in store.tasks.values() if t.selected_seller_id]


@router.post("/tasks/{task_id}/quote", response_model=Quote)
def generate_quote(
    task_id: str,
    seller_id: str,
    current_user: User = Depends(require_seller_or_admin),
):
    """
    Generate a pricing quote from a seller for a specific task.

    Sellers can only generate quotes under their own seller_id.
    Admins can generate quotes for any seller.

    Future: trigger quote generation automatically during task routing.
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    seller = registry.get_seller(seller_id)
    if not seller:
        raise HTTPException(status_code=404, detail=f"Seller {seller_id} not found")

    # Sellers can only quote for their own profile
    if str(current_user.role) == UserRole.SELLER:
        seller_profile = next(
            (s for s in store.sellers.values() if s.user_id == current_user.id), None
        )
        if not seller_profile or seller_profile.id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sellers can only generate quotes under their own seller profile",
            )

    quote = seller.generate_quote(task)
    store.quotes[quote.id] = quote
    store.log(
        event_type="quote.generated",
        entity_type="quote",
        entity_id=quote.id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=f"Quote generated by {seller.name} for task '{task.title}': ${quote.proposed_price}",
    )
    return quote


@router.post("/tasks/{task_id}/run", response_model=Task)
def run_seller_on_task(
    task_id: str,
    seller_id: str,
    current_user: User = Depends(require_seller_or_admin),
):
    """
    Trigger seller agent execution on a task.

    Assigns the seller to the task, runs the agent, stores the result,
    and updates task status to COMPLETED. Also runs generalist if enabled.

    Sellers can only run under their own seller_id.
    Admins can trigger execution for any seller.

    Future: make this async and queue-backed for production loads.
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    seller = registry.get_seller(seller_id)
    if not seller:
        raise HTTPException(status_code=404, detail=f"Seller {seller_id} not found")

    # Sellers can only execute as themselves
    if str(current_user.role) == UserRole.SELLER:
        seller_profile = next(
            (s for s in store.sellers.values() if s.user_id == current_user.id), None
        )
        if not seller_profile or seller_profile.id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sellers can only run tasks under their own seller profile",
            )

    # Assign seller
    task.selected_seller_id = seller_id
    task.status = TaskStatus.IN_PROGRESS
    task.updated_at = datetime.utcnow()
    store.log(
        event_type="seller.assigned",
        entity_type="task",
        entity_id=task.id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=f"Seller '{seller.name}' assigned to task '{task.title}'",
    )

    # Run specialist seller
    store.log(
        event_type="seller.execution_started",
        entity_type="task",
        entity_id=task.id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=f"Specialist '{seller.name}' executing task '{task.title}'",
    )
    seller_result = seller.run(task)
    task.seller_result = seller_result.content
    task.updated_at = datetime.utcnow()
    store.tasks[task.id] = task

    store.log(
        event_type="seller.execution_completed",
        entity_type="task",
        entity_id=task.id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=(
            f"Specialist '{seller.name}' completed task '{task.title}'. "
            f"Confidence: {seller_result.confidence:.0%}."
        ),
        metadata={"confidence": seller_result.confidence, "success": seller_result.success},
    )

    # Run generalist comparison if enabled — delegate entirely to benchmark runner
    comparison_result = None
    if task.generalist_comparison_enabled:
        comparison_run = run_generalist_comparison(
            task=task,
            seller_profile=seller.profile,
            store=store,
            registry=registry,
        )
        if comparison_run.ran and comparison_run.comparison:
            comparison_result = comparison_run.comparison

    # Mark task complete
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    store.tasks[task.id] = task

    store.log(
        event_type="task.completed",
        entity_type="task",
        entity_id=task.id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=(
            f"Task '{task.title}' completed by '{seller.name}'. "
            + (
                f"Benchmark: {comparison_result.winner} wins "
                f"({comparison_result.seller_score:.0%} vs {comparison_result.generalist_score:.0%})."
                if comparison_result else "No benchmark comparison."
            )
        ),
        metadata={
            "has_benchmark": comparison_result is not None,
            "benchmark_winner": comparison_result.winner if comparison_result else None,
            "benchmark_recommendation": comparison_result.recommendation if comparison_result else None,
        },
    )
    return task
