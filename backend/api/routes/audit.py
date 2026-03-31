"""
Auditor API routes.

Two audit workflows exposed here:

  Workflow A — Task Output Audit:
    POST /audit/tasks/{id}         — run audit on completed task (auditor/admin)
    GET  /audit/tasks/{id}         — retrieve audit result (buyer/seller/auditor/admin)
    GET  /audit/benchmark/{id}     — retrieve benchmark comparison (same access)

  Workflow B — Seller Onboarding Audit:
    POST /audit/sellers/{id}       — run onboarding audit (auditor/admin)
    GET  /audit/sellers/{id}       — retrieve onboarding review (seller=own/auditor/admin)
    GET  /audit/sellers/pending    — list sellers awaiting review (auditor/admin)

Access control summary:
  Auditor/Admin:  full write + read access to all audit endpoints
  Buyer:          read own task audit results and benchmark
  Seller:         read audit results for own tasks + own onboarding review
  Public:         none
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from ...agents.registry import registry
from ...auth.deps import get_current_user, require_auditor_or_admin
from ...models.enums import AuditStatus, ApprovalStatus, UserRole
from ...models.user import User
from ...store import store

router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Shared access checker
# ---------------------------------------------------------------------------

def _assert_task_readable(task_id: str, current_user: User) -> None:
    """
    Raise 403 if current_user cannot read this task's audit.
    Auditors and admins are unrestricted.
    Buyers see own tasks only; sellers see tasks assigned to them only.
    """
    role = str(current_user.role)
    if role in (UserRole.AUDITOR, UserRole.ADMIN):
        return

    task = store.tasks.get(task_id)
    if not task:
        return  # 404 raised by caller

    if role == UserRole.BUYER:
        buyer_profile = next(
            (b for b in store.buyers.values() if b.user_id == current_user.id), None
        )
        if not buyer_profile or task.buyer_id != buyer_profile.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: this audit belongs to a different buyer's task",
            )
    elif role == UserRole.SELLER:
        seller_profile = next(
            (s for s in store.sellers.values() if s.user_id == current_user.id), None
        )
        if not seller_profile or task.selected_seller_id != seller_profile.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: this audit is not for a task assigned to you",
            )


# ===========================================================================
# WORKFLOW A — Task Output Audit
# ===========================================================================

@router.post("/tasks/{task_id}", response_model=Dict[str, Any])
def audit_task(
    task_id: str,
    current_user: User = Depends(require_auditor_or_admin),
):
    """
    Run the auditor on a completed task.

    Produces an AuditResult with four dimension scores:
      quality, relevance, completeness, genericity (specificity).

    If a BenchmarkComparison already exists for this task (from execution),
    it is linked to the AuditResult and enriches the reasoning.

    If both seller_result and generalist_result are present and no
    BenchmarkComparison exists yet, one is created here.

    Role: auditor or admin only.
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if not task.seller_result:
        raise HTTPException(
            status_code=400,
            detail="Task has no seller result yet. Run seller execution first.",
        )

    auditor = registry.get_auditor()
    if not auditor:
        raise HTTPException(status_code=503, detail="Auditor agent not available")

    # Workflow A: task output audit
    audit_result = auditor.audit_task(task)
    store.audit_results[audit_result.id] = audit_result
    task.audit_result_id = audit_result.id
    task.audit_status = AuditStatus.PASSED if audit_result.passed else AuditStatus.FAILED

    # If generalist result exists but no comparison yet, create one now
    benchmark = None
    if task.generalist_result and not task.benchmark_comparison_id:
        benchmark = auditor.compare_results(task)
        store.benchmark_comparisons[benchmark.id] = benchmark
        task.benchmark_comparison_id = benchmark.id
    elif task.benchmark_comparison_id:
        benchmark = store.benchmark_comparisons.get(task.benchmark_comparison_id)

    store.tasks[task.id] = task

    store.log(
        event_type="audit.task_completed",
        entity_type="task",
        entity_id=task.id,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        message=(
            f"Task audit {'PASSED' if audit_result.passed else 'FAILED'} "
            f"for '{task.title}'. "
            f"Score: {audit_result.composite_score:.0%}. "
            f"Flags: {audit_result.flags or 'none'}."
        ),
        metadata={
            "audit_id": audit_result.id,
            "composite_score": audit_result.composite_score,
            "passed": audit_result.passed,
            "flags": audit_result.flags,
            "has_benchmark": bool(task.benchmark_comparison_id),
        },
    )

    return {
        "audit_result": audit_result.dict(),
        "benchmark_comparison": benchmark.dict() if benchmark else None,
    }


@router.get("/tasks/{task_id}", response_model=Dict[str, Any])
def get_task_audit(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the audit result for a task.
    Readable by: task's buyer, assigned seller, auditors, admins.
    """
    task = store.tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    _assert_task_readable(task_id, current_user)

    if not task.audit_result_id:
        raise HTTPException(status_code=404, detail="No audit result yet for this task.")

    audit = store.audit_results.get(task.audit_result_id)
    benchmark = (
        store.benchmark_comparisons.get(task.benchmark_comparison_id)
        if task.benchmark_comparison_id else None
    )
    return {
        "audit_result": audit.dict() if audit else None,
        "benchmark_comparison": benchmark.dict() if benchmark else None,
        "task_status": task.status,
        "audit_status": task.audit_status,
    }


@router.get("/benchmark/{task_id}", response_model=Dict[str, Any])
def get_benchmark(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the benchmark comparison for a task.
    Readable by: task's buyer, assigned seller, auditors, admins.
    """
    _assert_task_readable(task_id, current_user)
    task = store.tasks.get(task_id)
    if not task or not task.benchmark_comparison_id:
        raise HTTPException(status_code=404, detail="No benchmark comparison for this task.")
    benchmark = store.benchmark_comparisons.get(task.benchmark_comparison_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark record not found.")
    return benchmark.dict()


# ===========================================================================
# WORKFLOW B — Seller Onboarding Audit
# ===========================================================================

@router.post("/sellers/{seller_id}", response_model=Dict[str, Any])
def audit_seller_onboarding(
    seller_id: str,
    current_user: User = Depends(require_auditor_or_admin),
):
    """
    Run the auditor on a seller's onboarding profile.

    Scores five dimensions: completeness, expertise_credibility,
    pricing_clarity, category_fit, capacity_realism.

    Persists a SellerOnboardingReview and updates the seller's
    approval_status accordingly (approved / needs_review / rejected).

    Role: auditor or admin only.
    """
    seller_agent = registry.get_seller(seller_id)
    if not seller_agent:
        raise HTTPException(status_code=404, detail=f"Seller {seller_id} not found")

    auditor = registry.get_auditor()
    if not auditor:
        raise HTTPException(status_code=503, detail="Auditor agent not available")

    review = auditor.audit_seller_onboarding(
        profile=seller_agent.profile,
        store=store,
    )

    return {
        "review": review.dict(),
        "seller_id": seller_id,
        "seller_name": seller_agent.name,
        "approval_status": seller_agent.profile.approval_status,
    }


@router.get("/sellers/{seller_id}", response_model=Dict[str, Any])
def get_seller_onboarding_review(
    seller_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the onboarding review for a seller.

    Access:
      - Seller: own review only
      - Auditor / Admin: any review
    """
    role = str(current_user.role)

    # Seller can only read own review
    if role == UserRole.SELLER:
        seller_profile = next(
            (s for s in store.sellers.values() if s.user_id == current_user.id), None
        )
        if not seller_profile or seller_profile.id != seller_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sellers can only view their own onboarding review.",
            )

    seller_agent = registry.get_seller(seller_id)
    seller_profile_from_store = store.sellers.get(seller_id)
    if not seller_agent and not seller_profile_from_store:
        raise HTTPException(status_code=404, detail=f"Seller {seller_id} not found")

    review = store.get_onboarding_review_for_seller(seller_id)
    if not review:
        raise HTTPException(
            status_code=404,
            detail="No onboarding review found for this seller.",
        )

    profile = seller_agent.profile if seller_agent else seller_profile_from_store
    return {
        "review": review.dict(),
        "seller_id": seller_id,
        "seller_name": profile.display_name if profile else seller_id,
        "approval_status": profile.approval_status if profile else None,
    }


@router.get("/sellers", response_model=List[Dict[str, Any]])
def list_seller_reviews(
    review_status: Optional[str] = None,
    current_user: User = Depends(require_auditor_or_admin),
):
    """
    List seller onboarding reviews, optionally filtered by review_status.

    review_status values: queued | needs_review | in_review | approved | rejected

    Typical auditor workflow:
      GET /audit/sellers?review_status=needs_review
      → shows sellers waiting for human review
      POST /audit/sellers/{id}
      → runs auditor scoring and updates status
      POST /admin/sellers/{id}/approve|reject
      → admin final decision

    Role: auditor or admin only.
    """
    reviews = list(store.seller_onboarding_reviews.values())
    if review_status:
        reviews = [r for r in reviews if r.review_status == review_status]

    result = []
    for review in reviews:
        seller = store.sellers.get(review.seller_profile_id)
        result.append({
            "review": review.dict(),
            "seller_name": seller.display_name if seller else review.seller_profile_id,
            "approval_status": seller.approval_status if seller else "unknown",
        })
    return result
