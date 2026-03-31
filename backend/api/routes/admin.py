"""
Admin API routes.

Admin has read access to everything and override authority over auditor decisions.
All routes in this file require the ADMIN role.

Endpoints:
  GET  /admin/tasks                     — List all tasks across all buyers
  GET  /admin/logs                      — View full activity log (observability)
  GET  /admin/users                     — List all users (identity + role overview)
  POST /admin/audit/{audit_id}/override — Override an auditor decision
  GET  /admin/sellers                   — View all seller profiles and approval status
  POST /admin/sellers/{seller_id}/approve  — Approve a seller
  POST /admin/sellers/{seller_id}/reject   — Reject a seller
  GET  /admin/benchmark/summary         — Aggregate specialist vs. generalist statistics
  GET  /admin/benchmark/{task_id}        — Full benchmark comparison for a specific task
  GET  /admin/generalist                — Generalist agent profile + running performance record
  GET  /admin/marketplace               — Full marketplace analytics snapshot
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...agents.registry import registry
from ...auth.deps import require_admin
from ...models.enums import AuditStatus, ApprovalStatus
from ...models.user import User
from ...store import store

router = APIRouter(prefix="/admin", tags=["admin"])


class OverrideRequest(BaseModel):
    reason: str
    new_passed: bool


class OnboardingOverrideRequest(BaseModel):
    """Request body for overriding a seller onboarding review decision."""
    reason: str
    new_status: str   # "approved" | "rejected" | "needs_review"
    comment: Optional[str] = None


# ---------------------------------------------------------------------------
# User / identity overview
# ---------------------------------------------------------------------------

@router.get("/users", response_model=List[Dict[str, Any]])
def list_all_users(current_user: User = Depends(require_admin)):
    """
    List all registered users with their roles.
    Passwords are never included in responses (safe_dict()).
    """
    return [u.safe_dict() for u in store.users.values()]


# ---------------------------------------------------------------------------
# Task visibility (admin sees all)
# ---------------------------------------------------------------------------

@router.get("/tasks", response_model=List[Dict[str, Any]])
def list_all_tasks(current_user: User = Depends(require_admin)):
    """Full task list across all buyers. Admin view."""
    return [t.dict() for t in store.tasks.values()]


# ---------------------------------------------------------------------------
# Activity log — primary observability console data source
# ---------------------------------------------------------------------------

@router.get("/logs", response_model=List[Dict[str, Any]])
def get_activity_logs(
    limit: int = 100,
    entity_id: Optional[str] = None,
    current_user: User = Depends(require_admin),
):
    """
    Return recent activity log entries. Admin full view.

    Future: add cursor-based pagination and filter by event_type, actor_role.
    """
    logs = store.get_logs(limit=limit, entity_id=entity_id)
    return [l.dict() for l in logs]


# ---------------------------------------------------------------------------
# Scoped log endpoints for non-admin roles
# ---------------------------------------------------------------------------

@router.get("/logs/me", response_model=List[Dict[str, Any]])
def get_my_logs(
    limit: int = 50,
    current_user: User = Depends(require_admin),  # Admin only for now; extend later
):
    """Placeholder for per-user log scoping. Admin preview only for MVP."""
    logs = store.get_logs(limit=limit)
    return [l.dict() for l in logs if l.actor_id == current_user.id]


# ---------------------------------------------------------------------------
# Audit override
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Audit queue overview
# ---------------------------------------------------------------------------

@router.get("/audit/queue", response_model=Dict[str, Any])
def get_audit_queue(current_user: User = Depends(require_admin)):
    """
    Summary of the current audit workload.

    Returns:
      - completed tasks awaiting audit
      - counts by audit_status
      - seller onboarding reviews by review_status
    """
    return store.get_audit_queue_summary()


@router.get("/audit/pending-tasks", response_model=List[Dict[str, Any]])
def list_pending_tasks(current_user: User = Depends(require_admin)):
    """List completed tasks that have not yet been audited."""
    tasks = store.get_tasks_pending_audit()
    return [t.dict() for t in tasks]


# ---------------------------------------------------------------------------
# Task audit override
# ---------------------------------------------------------------------------

@router.post("/audit/{audit_id}/override", response_model=Dict[str, Any])
def override_audit(
    audit_id: str,
    req: OverrideRequest,
    current_user: User = Depends(require_admin),
):
    """
    Admin override of a task output audit decision.

    Use this when the auditor's automated score is incorrect —
    for example, if a mock output should be treated as passed
    for demo purposes, or if a real output was incorrectly flagged.

    Records:
      - admin_override = True
      - admin_override_reason = reason
      - overridden_at = now
      - overridden_by_user_id = current admin user
      - passed flipped to req.new_passed
      - parent task audit_status → OVERRIDDEN
    """
    audit = store.audit_results.get(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit result {audit_id} not found")

    now = datetime.utcnow()
    audit.admin_override = True
    audit.admin_override_reason = req.reason
    audit.passed = req.new_passed
    audit.overridden_at = now
    audit.overridden_by_user_id = current_user.id
    store.audit_results[audit_id] = audit

    # Update task audit_status
    for task in store.tasks.values():
        if task.audit_result_id == audit_id:
            task.audit_status = AuditStatus.OVERRIDDEN
            task.updated_at = now
            store.tasks[task.id] = task
            break

    # Update auditor override counter
    auditor = registry.get_auditor()
    if auditor:
        auditor.profile.override_count += 1

    store.log(
        event_type="audit.admin_override",
        entity_type="audit_result",
        entity_id=audit_id,
        actor_id=current_user.id,
        actor_role="admin",
        message=(
            f"Admin overrode task audit {audit_id}. "
            f"New passed: {req.new_passed}. "
            f"Reason: {req.reason}"
        ),
        metadata={
            "audit_id": audit_id,
            "new_passed": req.new_passed,
            "reason": req.reason,
        },
    )
    return audit.dict()


# ---------------------------------------------------------------------------
# Seller approval + onboarding review override
# ---------------------------------------------------------------------------

@router.get("/sellers", response_model=List[Dict[str, Any]])
def list_all_sellers(current_user: User = Depends(require_admin)):
    """
    List all sellers with approval status and onboarding review summary.
    Admin view — includes sellers from registry + store.
    """
    result = []
    for agent in registry.list_sellers():
        desc = agent.describe()
        review = store.get_onboarding_review_for_seller(agent.profile.id)
        desc["onboarding_review"] = {
            "review_status": review.review_status if review else "no_review",
            "overall_score": review.overall_score if review else None,
            "issues_count": len(review.issues) if review else 0,
        }
        result.append(desc)
    return result


@router.post("/sellers/{seller_id}/approve", response_model=Dict[str, Any])
def approve_seller(
    seller_id: str,
    current_user: User = Depends(require_admin),
):
    """
    Manually approve a seller.

    Updates:
      - SellerProfile.approval_status → APPROVED
      - SellerOnboardingReview.review_status → approved (if review exists)
      - SellerOnboardingReview.admin_override = True
    """
    seller = registry.get_seller(seller_id)
    seller_profile = store.sellers.get(seller_id)
    if not seller and not seller_profile:
        raise HTTPException(status_code=404, detail=f"Seller {seller_id} not found")

    # Resolve to a concrete profile — one of the two must be non-None after the guard above
    profile = (seller.profile if seller else seller_profile)
    assert profile is not None  # guaranteed by guard above; satisfies type checker
    now = datetime.utcnow()
    profile.approval_status = ApprovalStatus.APPROVED
    profile.approved_at = now
    store.sellers[seller_id] = profile

    # Update onboarding review if exists
    review = store.get_onboarding_review_for_seller(seller_id)
    if review:
        review.review_status = "approved"
        review.passed = True
        review.admin_override = True
        review.admin_override_reason = "Manually approved by admin"
        review.overridden_at = now
        review.overridden_by_user_id = current_user.id
        store.seller_onboarding_reviews[review.id] = review

    # Update auditor override counter
    auditor = registry.get_auditor()
    if auditor:
        auditor.profile.override_count += 1

    store.log(
        event_type="seller.admin_approved",
        entity_type="seller",
        entity_id=seller_id,
        actor_id=current_user.id,
        actor_role="admin",
        message=f"Admin manually approved seller: {profile.display_name}",
        metadata={"seller_id": seller_id},
    )
    return {
        "seller_id": seller_id,
        "display_name": profile.display_name,
        "approval_status": profile.approval_status,
        "approved_at": profile.approved_at.isoformat() if profile.approved_at else None,
    }


@router.post("/sellers/{seller_id}/reject", response_model=Dict[str, Any])
def reject_seller(
    seller_id: str,
    req: OverrideRequest,
    current_user: User = Depends(require_admin),
):
    """
    Manually reject a seller with a required reason.

    Updates:
      - SellerProfile.approval_status → REJECTED
      - SellerProfile.rejection_reason = req.reason
      - SellerOnboardingReview.review_status → rejected (if review exists)
    """
    seller = registry.get_seller(seller_id)
    seller_profile = store.sellers.get(seller_id)
    if not seller and not seller_profile:
        raise HTTPException(status_code=404, detail=f"Seller {seller_id} not found")

    profile = seller.profile if seller else seller_profile
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Seller profile {seller_id} not found")
    now = datetime.utcnow()
    profile.approval_status = ApprovalStatus.REJECTED
    profile.rejected_at = now
    profile.rejection_reason = req.reason
    store.sellers[seller_id] = profile

    review = store.get_onboarding_review_for_seller(seller_id)
    if review:
        review.review_status = "rejected"
        review.passed = False
        review.admin_override = True
        review.admin_override_reason = req.reason
        review.overridden_at = now
        review.overridden_by_user_id = current_user.id
        store.seller_onboarding_reviews[review.id] = review

    auditor = registry.get_auditor()
    if auditor:
        auditor.profile.override_count += 1

    store.log(
        event_type="seller.admin_rejected",
        entity_type="seller",
        entity_id=seller_id,
        actor_id=current_user.id,
        actor_role="admin",
        message=f"Admin rejected seller: {profile.display_name}. Reason: {req.reason}",
        metadata={"seller_id": seller_id, "reason": req.reason},
    )
    return {
        "seller_id": seller_id,
        "display_name": profile.display_name,
        "approval_status": profile.approval_status,
        "rejection_reason": profile.rejection_reason,
    }


@router.post("/sellers/{seller_id}/review/override", response_model=Dict[str, Any])
def override_onboarding_review(
    seller_id: str,
    req: OnboardingOverrideRequest,
    current_user: User = Depends(require_admin),
):
    """
    Override a seller's onboarding review status without running the full auditor.

    Useful when:
      - Auditor score is close to threshold and admin wants to manually tip it
      - A seller provided additional credentials out-of-band
      - A needs_review seller should be moved directly to approved/rejected

    new_status must be one of: "approved" | "rejected" | "needs_review"
    """
    valid_statuses = {"approved", "rejected", "needs_review"}
    if req.new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"new_status must be one of {valid_statuses}",
        )

    review = store.get_onboarding_review_for_seller(seller_id)
    if not review:
        raise HTTPException(
            status_code=404,
            detail=f"No onboarding review found for seller {seller_id}",
        )

    seller_profile = store.sellers.get(seller_id)
    if not seller_profile:
        seller_agent = registry.get_seller(seller_id)
        seller_profile = seller_agent.profile if seller_agent else None

    now = datetime.utcnow()
    review.review_status = req.new_status
    review.passed = (req.new_status == "approved")
    review.admin_override = True
    review.admin_override_reason = req.reason
    review.auditor_comment = req.comment
    review.overridden_at = now
    review.overridden_by_user_id = current_user.id
    store.seller_onboarding_reviews[review.id] = review

    if seller_profile:
        if req.new_status == "approved":
            seller_profile.approval_status = ApprovalStatus.APPROVED
            seller_profile.approved_at = now
        elif req.new_status == "rejected":
            seller_profile.approval_status = ApprovalStatus.REJECTED
            seller_profile.rejected_at = now
            seller_profile.rejection_reason = req.reason
        else:
            seller_profile.approval_status = ApprovalStatus.NEEDS_REVIEW
        store.sellers[seller_id] = seller_profile

    auditor = registry.get_auditor()
    if auditor:
        auditor.profile.override_count += 1

    store.log(
        event_type="seller.review_overridden",
        entity_type="seller",
        entity_id=seller_id,
        actor_id=current_user.id,
        actor_role="admin",
        message=(
            f"Admin overrode onboarding review for seller {seller_id}. "
            f"New status: {req.new_status}. Reason: {req.reason}"
        ),
        metadata={
            "review_id": review.id,
            "new_status": req.new_status,
            "reason": req.reason,
        },
    )
    return {
        "review": review.dict(),
        "seller_id": seller_id,
        "new_approval_status": seller_profile.approval_status if seller_profile else None,
    }


# ---------------------------------------------------------------------------
# Benchmark / generalist comparison admin views
# ---------------------------------------------------------------------------

@router.get("/benchmark/summary", response_model=Dict[str, Any])
def get_benchmark_summary(current_user: User = Depends(require_admin)):
    """
    Aggregate benchmark statistics across all completed comparisons.

    Shows the overall specialist vs. generalist picture:
      - total comparisons run
      - specialist win rate
      - average quality delta (specialist - generalist)
      - breakdown by category and recommendation type

    This is the primary evidence view for the thesis that specialized sellers
    outperform generalists on structured professional tasks.
    """
    return store.get_benchmark_comparisons_summary()


@router.get("/benchmark/{task_id}", response_model=Dict[str, Any])
def get_task_benchmark(
    task_id: str,
    current_user: User = Depends(require_admin),
):
    """
    Full benchmark comparison for a specific task.

    Shows dimension-by-dimension scoring, cost comparison, ETA comparison,
    and the recommendation outcome.
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if not task.benchmark_comparison_id:
        raise HTTPException(
            status_code=404,
            detail=(
                "No benchmark comparison for this task. "
                "Run seller execution with generalist_comparison_enabled=True first."
            ),
        )

    comparison = store.benchmark_comparisons.get(task.benchmark_comparison_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="Benchmark record not found in store.")

    return {
        "task": {
            "id": task.id,
            "title": task.title,
            "category": task.category,
            "status": task.status,
        },
        "comparison": comparison.dict(),
    }


@router.get("/generalist", response_model=Dict[str, Any])
def get_generalist_profile(current_user: User = Depends(require_admin)):
    """
    Generalist agent profile and running performance record.

    Shows: model config, cost_per_task, estimated_minutes, win/loss/tie record,
    rolling benchmark_score, and tasks_completed.

    Use this to monitor whether the generalist is improving or declining
    relative to specialists over time.
    """
    generalist = registry.get_generalist()
    if not generalist:
        raise HTTPException(status_code=503, detail="Generalist agent not registered.")
    return generalist.describe()


# ---------------------------------------------------------------------------
# Marketplace analytics
# ---------------------------------------------------------------------------

@router.get("/marketplace", response_model=Dict[str, Any])
def get_marketplace_analytics(
    lookback_hours: int = 24,
    current_user: User = Depends(require_admin),
):
    """
    Full marketplace analytics snapshot.

    Sections returned:
      participants       — active/total buyers, sellers by category, pending reviews
      tasks              — volume, status distribution, category breakdown, fill rate
      pricing            — avg/range/trend per category, avg ETA per category
      supply_demand      — demand (tasks in window) vs. supply (available capacity),
                           ratio and health signal per category
      seller_utilization — per-seller load, capacity, utilization %, busy/available
      specialist_vs_generalist — win rate, avg quality delta

    lookback_hours (default 24):
      Window used to compute demand_by_category.
      Pass ?lookback_hours=168 for a 7-day demand view.
    """
    return store.get_marketplace_analytics(lookback_hours=lookback_hours)
