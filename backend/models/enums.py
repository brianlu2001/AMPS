"""
Shared enumerations for the AMPS domain.

All status fields, category fields, and role fields use these enums.
Adding new values here propagates automatically across all models and routes.
"""

from enum import Enum


class UserRole(str, Enum):
    """
    Platform-level roles. Controls access to routes and console views.
    Future: extend with SELLER_PREMIUM, AUDITOR_SENIOR, etc.
    """
    BUYER = "buyer"
    SELLER = "seller"
    GENERALIST = "generalist"
    AUDITOR = "auditor"
    ADMIN = "admin"


class TaskCategory(str, Enum):
    """
    The four MVP service categories. All share a single task schema.
    Future: add new categories here without changing task model shape.
    """
    FINANCIAL_RESEARCH = "financial_research"
    LEGAL_ANALYSIS = "legal_analysis"
    MARKET_INTELLIGENCE = "market_intelligence"
    STRATEGY_BUSINESS_RESEARCH = "strategy_business_research"


class TaskStatus(str, Enum):
    """
    Lifecycle of a task from creation to resolution.
    Future: add BIDDING, ESCROWED, APPEALED as marketplace mechanics evolve.
    """
    PENDING = "pending"           # Created, not yet assigned
    ASSIGNED = "assigned"         # Seller selected / accepted
    IN_PROGRESS = "in_progress"   # Seller actively working
    COMPLETED = "completed"       # Seller submitted result
    FAILED = "failed"             # Execution error or timeout
    DISPUTED = "disputed"         # Buyer or auditor flagged result


class AuditStatus(str, Enum):
    """
    State of the auditor review for a given task.
    Future: add APPEALED, ESCALATED_TO_ADMIN.
    """
    NOT_STARTED = "not_started"
    IN_REVIEW = "in_review"
    PASSED = "passed"
    FAILED = "failed"
    OVERRIDDEN = "overridden"     # Admin manually overrode auditor decision


class ApprovalStatus(str, Enum):
    """
    Whether a seller or generalist agent has been approved to operate on the platform.

    State machine:
      PENDING → NEEDS_REVIEW  (auto-triggered after onboarding submission)
      NEEDS_REVIEW → APPROVED | REJECTED  (auditor or admin action)
      APPROVED → SUSPENDED  (future — admin action for policy violations)
    """
    PENDING      = "pending"       # Just registered, not yet reviewed
    NEEDS_REVIEW = "needs_review"  # Queued for auditor review
    APPROVED     = "approved"      # Active on marketplace
    REJECTED     = "rejected"      # Rejected during review
    SUSPENDED    = "suspended"     # Future: temporarily removed from marketplace


class PricingModel(str, Enum):
    """
    How a seller agent prices its services.
    Future: add AUCTION, SUBSCRIPTION, TIERED.
    """
    FIXED = "fixed"         # Set price per task
    QUOTED = "quoted"       # Seller generates a quote per task
    FREE = "free"           # Used for generalist baseline (no cost)


class OutputType(str, Enum):
    """
    The format the buyer expects as the task deliverable.
    Future: add SPREADSHEET, PRESENTATION, CODE, API_RESPONSE.
    """
    REPORT = "report"               # Long-form written analysis
    SUMMARY = "summary"             # Short structured summary
    STRUCTURED_JSON = "structured_json"  # Machine-readable structured output
    BULLET_LIST = "bullet_list"     # Concise bullet-point output
