"""
User and agent profile domain models.

These are Pydantic models used for in-memory state, API request/response shapes,
and agent identity during MVP. No ORM layer yet — swap in SQLAlchemy models
when a persistent database is added.

Future: replace with SQLAlchemy Base subclasses and Alembic migrations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .enums import UserRole, TaskCategory, ApprovalStatus, PricingModel


# ---------------------------------------------------------------------------
# Base User
# ---------------------------------------------------------------------------

class User(BaseModel):
    """
    Core identity record for every platform participant.
    Role determines which profile type is attached and which routes are accessible.

    password: plain-text for MVP only. Never expose in API responses.
    Future: replace with hashed_password (bcrypt), add email_verified,
    last_login, OAuth provider fields. Remove password from this model
    and store it in a separate credentials table.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    display_name: str
    role: UserRole
    password: Optional[str] = None  # MVP only — plain text; exclude from responses
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    def safe_dict(self) -> dict:
        """Return user data without the password field. Use this in API responses."""
        d = self.dict()
        d.pop("password", None)
        return d

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Buyer Profile
# ---------------------------------------------------------------------------

class BuyerProfile(BaseModel):
    """
    Extended profile for a buyer agent.

    Populated by the onboarding pipeline (onboarding/enrollment.py).
    Fields with suffix _hint are best-effort extractions from URL content
    or natural-language instruction; treat as informational, not verified.

    Future: add payment_method_id, spending_limit, verified_organization.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str                                    # FK -> User.id

    # Raw onboarding inputs
    context_source_url: Optional[str] = None        # URL provided or extracted during onboarding
    onboarding_raw_prompt: Optional[str] = None     # Original instruction text

    # Extracted profile fields (populated by profile_extractor.py)
    organization: Optional[str] = None              # Company / org name
    display_name_hint: Optional[str] = None         # Buyer's name if extractable
    industry_hint: Optional[str] = None             # e.g. "fintech / finance"
    preferred_categories: List[str] = Field(default_factory=list)  # Task categories buyer likely needs
    use_case_summary: Optional[str] = None          # One-sentence summary of buyer's use case

    # Onboarding metadata
    onboarding_confidence: float = 0.0              # 0.0–1.0; how confident the pipeline was
    onboarding_source: str = "unknown"              # "http" | "mock" | "instruction_only"

    # Usage counters
    task_history_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Seller Profile
# ---------------------------------------------------------------------------

class SellerProfile(BaseModel):
    """
    Full capability and identity declaration for a specialized seller agent.

    This is both the marketplace-facing contract (buyers and routing layer read it)
    and the onboarding record (submitted at registration time).

    The schema is intentionally horizontal — all four service categories share
    this same shape. Category-specific behavior lives in the agent execution layer
    (agents/seller.py), not here.

    Future: add availability_calendar, sla_hours, verified_credentials[],
    external_agent_api_url for connecting to real external agent endpoints.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str                               # FK -> User.id

    # ----- Identity & description -----
    display_name: str
    description: Optional[str] = None          # Free-text: who this seller is and what they do
    website_url: Optional[str] = None          # Optional seller homepage or API docs URL
    contact_email: Optional[str] = None        # Contact for marketplace admin use

    # ----- Specialization (horizontal, category-agnostic schema) -----
    specialization_categories: List[TaskCategory]   # Which of the 4 categories this seller covers
    supported_output_types: List[str]               # OutputType values this seller can produce
    # expertise_claims: freeform sentences describing domain competence,
    # used by the auditor to validate and by buyers to evaluate fit.
    # Format: list of plain-English capability statements.
    # Example: ["10+ years financial modeling", "CFA charterholder", "SEC filing analysis"]
    expertise_claims: List[str] = Field(default_factory=list)

    # benchmark_references: optional pointers to prior work evidence
    # (publications, portfolio items, test task IDs, external links)
    # Format: list of {type, value, description} dicts for extensibility
    benchmark_references: List[dict] = Field(default_factory=list)

    # ----- Pricing -----
    pricing_model: PricingModel
    base_price: Optional[float] = None         # USD; used when pricing_model=FIXED
    # quote_notes: freeform explanation of pricing logic for QUOTED sellers
    quote_notes: Optional[str] = None
    # Future: replace base_price with a quote_logic callable / pricing engine

    # ----- Execution SLA -----
    # estimated_minutes: default ETA per task — flat for MVP
    # Future: replace with per-category or per-complexity ETA model
    estimated_minutes: int = 30

    # ----- Capacity & performance -----
    capacity: int = 10                          # Max concurrent tasks
    confidence_score: float = 0.75             # Self-reported 0.0–1.0; auditor may adjust
    benchmark_score: Optional[float] = None    # Populated after benchmark comparison runs
    reputation_score: float = 0.0              # Aggregate from audit results; 0.0–5.0

    # ----- Platform approval state -----
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    # onboarding_review_id: FK -> SellerOnboardingReview.id once auditor queues it
    onboarding_review_id: Optional[str] = None

    # ----- Agent execution adapter -----
    # agent_type: which execution class to instantiate.
    # Stays "mock" until a real LLM or external API is wired.
    # Future: "openai_function", "anthropic_tool", "external_api"
    agent_type: str = "mock"
    # external_agent_api_url: endpoint for real external agent execution (post-MVP)
    external_agent_api_url: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Generalist Agent Profile
# ---------------------------------------------------------------------------

class GeneralistProfile(BaseModel):
    """
    Profile for the generalist baseline agent.

    The generalist is NOT a marketplace seller — it is a system-level
    benchmark/control that runs on tasks where generalist_comparison_enabled=True.

    Purpose: establish whether specialized sellers produce meaningfully better
    output than a capable general LLM given the same task brief.

    Cost model:
      cost_per_task: estimated USD equivalent for running the generalist
      (e.g., LLM API cost). Used in BenchmarkComparison to compare total cost.

    Future: support multiple generalist variants (GPT-4o, Claude Sonnet, Gemini)
    to compare different general models against the same specialist.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str                              # FK -> User.id (role=GENERALIST)
    display_name: str = "Generalist Baseline"

    # Model configuration
    # model_identifier: the LLM model ID; "mock-generalist-v1" until real LLM wired
    model_identifier: str = "mock-generalist-v1"
    # model_config: freeform dict for provider/model parameters
    # e.g. {"provider": "openai", "model": "gpt-4o", "temperature": 0.2}
    model_config_params: dict = Field(default_factory=lambda: {
        "provider": "mock",
        "model": "mock-generalist-v1",
        "temperature": 0.0,
        "note": "Replace with real LLM config when wiring live provider",
    })

    # Cost baseline: estimated API cost per task execution
    # Used in BenchmarkComparison.generalist_cost
    # Future: compute dynamically from token counts
    cost_per_task: float = 0.02              # USD — placeholder for LLM API cost
    estimated_minutes: int = 5              # Generalist is typically faster (no specialization overhead)
    confidence_baseline: float = 0.65       # Generalist's expected confidence across all categories

    # Performance tracking (updated as comparisons accumulate)
    benchmark_score: Optional[float] = None  # Average quality score across all comparison runs
    tasks_completed: int = 0
    wins: int = 0                            # Tasks where generalist outscored specialist
    losses: int = 0                          # Tasks where specialist outscored generalist
    ties: int = 0

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Auditor Profile
# ---------------------------------------------------------------------------

class AuditorProfile(BaseModel):
    """
    Profile for an auditor agent.

    The auditor evaluates two workflows:
      1. Seller onboarding — validates expertise claims, sets approval recommendation
      2. Task output — scores quality, relevance, completeness, and genericity

    Admin can override any auditor decision.

    Scoring history is tracked here so admin can monitor auditor calibration over time.
    Future: support multiple specialized auditors per category.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str                              # FK -> User.id (role=AUDITOR)
    display_name: str = "Auditor"
    specialization_categories: List[TaskCategory] = []  # Empty = audits all categories

    # --- Workload counters ---
    audits_completed: int = 0                 # Task output audits completed
    onboarding_reviews_completed: int = 0     # Seller onboarding reviews completed
    override_count: int = 0                   # Times admin overrode this auditor's decision

    # --- Scoring history (rolling averages for calibration monitoring) ---
    avg_task_quality_score: Optional[float] = None    # Rolling mean of composite scores given
    avg_genericity_flag_rate: Optional[float] = None  # How often auditor flags "too_generic"
    avg_onboarding_score: Optional[float] = None      # Rolling mean of onboarding overall_scores

    # --- Scoring method preference ---
    # scoring_method: how this auditor scores outputs
    # "mock_heuristic" for MVP; "llm_judge" when a real LLM auditor is wired
    scoring_method: str = "mock_heuristic"

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True
