"""
Demo seed data for AMPS MVP.

Populates the in-memory store with a complete set of demo participants
so the system is immediately usable after startup without any manual setup.

Demo users:
  Role       | Email                   | Password   | Display name
  -----------|-------------------------|------------|--------------------
  buyer      | buyer@amps.dev          | buyer123   | Alice Buyer
  seller     | seller1@amps.dev        | seller123  | FinancialResearch Pro
  seller     | seller2@amps.dev        | seller123  | LegalAnalysis Pro
  seller     | seller3@amps.dev        | seller123  | MarketIntel Pro
  generalist | generalist@amps.dev     | gen123     | Generalist Baseline
  auditor    | auditor@amps.dev        | audit123   | Auditor
  admin      | admin@amps.dev          | admin123   | Admin

Seeded seller specializations:
  seller1 — financial_research      (approved, $75/task)
  seller2 — legal_analysis          (approved, $95/task)
  seller3 — market_intelligence     (needs_review — demo of review flow)

Future: move to a database migration + fixtures file.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict

from .models.enums import (
    ApprovalStatus,
    OutputType,
    PricingModel,
    TaskCategory,
    TaskStatus,
    UserRole,
)
from .models.task import SellerOnboardingReview, Task
from .models.user import BuyerProfile, SellerProfile, User
from .store import store


# ---------------------------------------------------------------------------
# Stable demo IDs — fixed so logs/links survive restarts during dev
# ---------------------------------------------------------------------------

DEMO_IDS: Dict[str, str] = {
    # Users
    "buyer_user":        "00000001-0000-0000-0000-000000000001",
    "seller1_user":      "00000001-0000-0000-0000-000000000002",
    "seller2_user":      "00000001-0000-0000-0000-000000000003",
    "seller3_user":      "00000001-0000-0000-0000-000000000007",
    "seller4_user":      "00000001-0000-0000-0000-000000000008",  # strategy
    "generalist_user":   "00000001-0000-0000-0000-000000000004",
    "auditor_user":      "00000001-0000-0000-0000-000000000005",
    "admin_user":        "00000001-0000-0000-0000-000000000006",
    # Profiles
    "buyer_profile":     "00000002-0000-0000-0000-000000000001",
    "seller1_profile":   "00000002-0000-0000-0000-000000000002",
    "seller2_profile":   "00000002-0000-0000-0000-000000000003",
    "seller3_profile":   "00000002-0000-0000-0000-000000000007",
    "seller4_profile":   "00000002-0000-0000-0000-000000000008",  # strategy
    # Onboarding reviews
    "review_seller1":    "00000004-0000-0000-0000-000000000001",
    "review_seller2":    "00000004-0000-0000-0000-000000000002",
    "review_seller3":    "00000004-0000-0000-0000-000000000003",
    "review_seller4":    "00000004-0000-0000-0000-000000000004",
    # Demo tasks
    "task_finance":      "00000003-0000-0000-0000-000000000001",
    "task_legal":        "00000003-0000-0000-0000-000000000002",
    "task_market":       "00000003-0000-0000-0000-000000000003",
    "task_completed":    "00000003-0000-0000-0000-000000000004",  # pre-completed demo task
    # Demo quotes (for the completed task)
    "quote_completed":   "00000005-0000-0000-0000-000000000001",
    # Demo audit result (for the completed task)
    "audit_completed":   "00000006-0000-0000-0000-000000000001",
    # Demo benchmark (for the completed task)
    "benchmark_completed": "00000007-0000-0000-0000-000000000001",
}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def seed_demo_users() -> None:
    """
    Create and register all demo User records in the store.
    Idempotent: skips users that already exist (by email).
    """
    demo_users = [
        User(
            id=DEMO_IDS["buyer_user"],
            email="buyer@amps.dev",
            display_name="Alice Buyer",
            role=UserRole.BUYER,
            password="buyer123",
        ),
        User(
            id=DEMO_IDS["seller1_user"],
            email="seller1@amps.dev",
            display_name="FinancialResearch Pro",
            role=UserRole.SELLER,
            password="seller123",
        ),
        User(
            id=DEMO_IDS["seller2_user"],
            email="seller2@amps.dev",
            display_name="LegalAnalysis Pro",
            role=UserRole.SELLER,
            password="seller123",
        ),
        User(
            id=DEMO_IDS["seller3_user"],
            email="seller3@amps.dev",
            display_name="MarketIntel Pro",
            role=UserRole.SELLER,
            password="seller123",
        ),
        User(
            id=DEMO_IDS["seller4_user"],
            email="seller4@amps.dev",
            display_name="Strategy Pro",
            role=UserRole.SELLER,
            password="seller123",
        ),
        User(
            id=DEMO_IDS["generalist_user"],
            email="generalist@amps.dev",
            display_name="Generalist Baseline",
            role=UserRole.GENERALIST,
            password="gen123",
        ),
        User(
            id=DEMO_IDS["auditor_user"],
            email="auditor@amps.dev",
            display_name="Auditor",
            role=UserRole.AUDITOR,
            password="audit123",
        ),
        User(
            id=DEMO_IDS["admin_user"],
            email="admin@amps.dev",
            display_name="Admin",
            role=UserRole.ADMIN,
            password="admin123",
        ),
    ]
    for user in demo_users:
        if not store.get_user_by_email(user.email):
            store.add_user(user)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def seed_demo_profiles() -> None:
    """
    Create BuyerProfile and SellerProfile records for the demo users.

    All three seller profiles now include the full rich onboarding fields
    (description, expertise_claims, benchmark_references, etc.) so they
    demonstrate the complete seller schema.

    seller3 (market-intel) is left in NEEDS_REVIEW to demo the review flow.
    """
    # --- Buyer ---
    if DEMO_IDS["buyer_profile"] not in store.buyers:
        store.buyers[DEMO_IDS["buyer_profile"]] = BuyerProfile(
            id=DEMO_IDS["buyer_profile"],
            user_id=DEMO_IDS["buyer_user"],
            organization="AMPS Demo Corp",
            display_name_hint="Alice Buyer",
            industry_hint="consulting",
            preferred_categories=["financial_research", "legal_analysis", "market_intelligence"],
            use_case_summary=(
                "AMPS Demo Corp — consulting — "
                "seeking financial research, legal analysis, market intelligence."
            ),
            onboarding_raw_prompt="Enrolled via demo seed data",
            onboarding_confidence=0.95,
            onboarding_source="seed",
            task_history_count=0,
        )

    # --- Seller 1: Financial Research (APPROVED) ---
    if DEMO_IDS["seller1_profile"] not in store.sellers:
        store.sellers[DEMO_IDS["seller1_profile"]] = SellerProfile(
            id=DEMO_IDS["seller1_profile"],
            user_id=DEMO_IDS["seller1_user"],
            display_name="FinancialResearch Pro",
            description=(
                "Specialized in equity research, earnings analysis, and financial due diligence. "
                "Covers public market companies across US, EU, and APAC. "
                "Delivers structured reports, key metrics summaries, and risk flag briefs."
            ),
            website_url="https://example.com/financialresearch-pro",
            contact_email="seller1@amps.dev",
            specialization_categories=[TaskCategory.FINANCIAL_RESEARCH],
            supported_output_types=["report", "summary", "structured_json", "bullet_list"],
            expertise_claims=[
                "CFA charterholder with 8 years in buy-side equity research",
                "Specializes in SEC 10-K/10-Q analysis and earnings call transcript review",
                "Covered TMT and healthcare sectors at top-tier investment bank",
                "Proficient in Bloomberg Terminal, FactSet, and Capital IQ data pulls",
            ],
            benchmark_references=[
                {"type": "task_sample", "description": "Q3 earnings brief — Fortune 500 retailer",
                 "value": "internal_sample_001"},
                {"type": "credential", "description": "CFA Institute membership",
                 "value": "https://cfainstitute.org"},
            ],
            pricing_model=PricingModel.FIXED,
            base_price=75.0,
            estimated_minutes=25,
            capacity=10,
            confidence_score=0.82,
            reputation_score=4.2,
            approval_status=ApprovalStatus.APPROVED,
            approved_at=datetime.utcnow(),
            onboarding_review_id=DEMO_IDS["review_seller1"],
            agent_type="mock",
        )

    # --- Seller 2: Legal Analysis (APPROVED) ---
    if DEMO_IDS["seller2_profile"] not in store.sellers:
        store.sellers[DEMO_IDS["seller2_profile"]] = SellerProfile(
            id=DEMO_IDS["seller2_profile"],
            user_id=DEMO_IDS["seller2_user"],
            display_name="LegalAnalysis Pro",
            description=(
                "Expert in commercial contract review, SaaS agreement analysis, and "
                "regulatory compliance checks across US and EU jurisdictions. "
                "Flags non-standard clauses, IP risks, and indemnification exposure."
            ),
            website_url="https://example.com/legal-pro",
            contact_email="seller2@amps.dev",
            specialization_categories=[TaskCategory.LEGAL_ANALYSIS],
            supported_output_types=["report", "summary", "bullet_list"],
            expertise_claims=[
                "JD from top-10 law school, 6 years corporate transactional practice",
                "Specializes in SaaS, IP licensing, and vendor contract negotiation",
                "Reviewed 200+ enterprise software agreements for Fortune 1000 clients",
                "Familiar with GDPR, CCPA, and SOC 2 compliance clauses",
            ],
            benchmark_references=[
                {"type": "task_sample", "description": "SaaS MSA clause review summary",
                 "value": "internal_sample_002"},
                {"type": "credential", "description": "Bar admission — New York State",
                 "value": "https://nysba.org"},
            ],
            pricing_model=PricingModel.FIXED,
            base_price=95.0,
            estimated_minutes=30,
            capacity=8,
            confidence_score=0.85,
            reputation_score=4.1,
            approval_status=ApprovalStatus.APPROVED,
            approved_at=datetime.utcnow(),
            onboarding_review_id=DEMO_IDS["review_seller2"],
            agent_type="mock",
        )

    # --- Seller 3: Market Intelligence (NEEDS_REVIEW — demos review flow) ---
    if DEMO_IDS["seller3_profile"] not in store.sellers:
        store.sellers[DEMO_IDS["seller3_profile"]] = SellerProfile(
            id=DEMO_IDS["seller3_profile"],
            user_id=DEMO_IDS["seller3_user"],
            display_name="MarketIntel Pro",
            description=(
                "Specializes in competitive landscape analysis, TAM/SAM sizing, "
                "and go-to-market intelligence for B2B SaaS and fintech verticals. "
                "Delivers market maps, competitor profiles, and growth trend summaries."
            ),
            website_url="https://example.com/marketintel-pro",
            contact_email="seller3@amps.dev",
            specialization_categories=[TaskCategory.MARKET_INTELLIGENCE],
            supported_output_types=["report", "summary", "structured_json"],
            expertise_claims=[
                "5 years market research at leading strategy consulting firm",
                "Built TAM models for Series A–C companies in fintech and SaaS",
                "Proficient in Crunchbase Pro, CB Insights, and PitchBook data",
            ],
            benchmark_references=[
                {"type": "task_sample", "description": "Fintech TAM analysis — 2024",
                 "value": "internal_sample_003"},
            ],
            pricing_model=PricingModel.FIXED,
            base_price=65.0,
            estimated_minutes=30,
            capacity=12,
            confidence_score=0.78,
            reputation_score=0.0,            # New seller — no reputation yet
            approval_status=ApprovalStatus.NEEDS_REVIEW,  # Demo: pending auditor review
            onboarding_review_id=DEMO_IDS["review_seller3"],
            agent_type="mock",
        )

    # --- Seller 4: Strategy / Business Research (APPROVED) ---
    if DEMO_IDS["seller4_profile"] not in store.sellers:
        store.sellers[DEMO_IDS["seller4_profile"]] = SellerProfile(
            id=DEMO_IDS["seller4_profile"],
            user_id=DEMO_IDS["seller4_user"],
            display_name="Strategy Pro",
            description=(
                "Expert in go-to-market strategy, competitive positioning, and business research "
                "for B2B SaaS, fintech, and professional services. Delivers strategic options "
                "analyses, GTM playbooks, and competitive positioning frameworks."
            ),
            website_url="https://example.com/strategy-pro",
            contact_email="seller4@amps.dev",
            specialization_categories=[TaskCategory.STRATEGY_BUSINESS_RESEARCH],
            supported_output_types=["report", "summary", "structured_json", "bullet_list"],
            expertise_claims=[
                "MBA (top-5 school), 7 years strategy consulting at McKinsey and BCG",
                "Led GTM strategy for 12 Series B+ SaaS companies",
                "Expert in Porter's Five Forces, Jobs-to-be-Done, and OKR frameworks",
                "Proficient in competitive intelligence platforms and primary research design",
            ],
            benchmark_references=[
                {"type": "task_sample", "description": "GTM strategy for SaaS startup — 2024",
                 "value": "internal_sample_004"},
                {"type": "credential", "description": "MBA — Wharton School",
                 "value": "https://wharton.upenn.edu"},
            ],
            pricing_model=PricingModel.FIXED,
            base_price=85.0,
            estimated_minutes=35,
            capacity=8,
            confidence_score=0.83,
            reputation_score=4.0,
            approval_status=ApprovalStatus.APPROVED,
            approved_at=datetime.utcnow(),
            onboarding_review_id=DEMO_IDS["review_seller4"],
            agent_type="mock",
        )


# ---------------------------------------------------------------------------
# Onboarding reviews
# ---------------------------------------------------------------------------

def seed_onboarding_reviews() -> None:
    """
    Create SellerOnboardingReview records for all four seeded sellers.

    seller1 + seller2 + seller4: approved (high scores, no issues)
    seller3: needs_review (demo of the queued review state)
    """
    now = datetime.utcnow()

    if DEMO_IDS["review_seller1"] not in store.seller_onboarding_reviews:
        store.seller_onboarding_reviews[DEMO_IDS["review_seller1"]] = SellerOnboardingReview(
            id=DEMO_IDS["review_seller1"],
            seller_profile_id=DEMO_IDS["seller1_profile"],
            auditor_id=DEMO_IDS["auditor_user"],
            review_status="approved",
            overall_score=0.91,
            dimension_scores={
                "completeness":          0.95,
                "expertise_credibility": 0.90,
                "pricing_clarity":       0.95,
                "category_fit":          0.90,
                "capacity_realism":      0.85,
            },
            passed=True,
            issues=[],
            recommendations=["Consider adding more benchmark references for higher trust score."],
            reasoning=(
                "Profile is complete and credible. Expertise claims are specific and verifiable. "
                "Pricing is clear. Approved for marketplace."
            ),
            reviewed_at=now,
        )

    if DEMO_IDS["review_seller2"] not in store.seller_onboarding_reviews:
        store.seller_onboarding_reviews[DEMO_IDS["review_seller2"]] = SellerOnboardingReview(
            id=DEMO_IDS["review_seller2"],
            seller_profile_id=DEMO_IDS["seller2_profile"],
            auditor_id=DEMO_IDS["auditor_user"],
            review_status="approved",
            overall_score=0.88,
            dimension_scores={
                "completeness":          0.90,
                "expertise_credibility": 0.90,
                "pricing_clarity":       0.90,
                "category_fit":          0.85,
                "capacity_realism":      0.85,
            },
            passed=True,
            issues=[],
            recommendations=["Structured_json output type not listed — consider adding."],
            reasoning=(
                "Profile is complete with strong legal credentials. "
                "Expertise claims are specific and include verifiable credential. "
                "Approved for marketplace."
            ),
            reviewed_at=now,
        )

    if DEMO_IDS["review_seller3"] not in store.seller_onboarding_reviews:
        store.seller_onboarding_reviews[DEMO_IDS["review_seller3"]] = SellerOnboardingReview(
            id=DEMO_IDS["review_seller3"],
            seller_profile_id=DEMO_IDS["seller3_profile"],
            auditor_id=None,    # Not yet assigned to a human auditor
            review_status="needs_review",
            overall_score=0.74,
            dimension_scores={
                "completeness":          0.80,
                "expertise_credibility": 0.70,
                "pricing_clarity":       0.85,
                "category_fit":          0.70,
                "capacity_realism":      0.65,
            },
            passed=None,        # Awaiting human auditor decision
            issues=["Only 3 expertise claims — borderline for approval threshold"],
            recommendations=[
                "Add a 4th expertise claim with a specific project outcome",
                "Add structured_json to supported_output_types",
                "Consider reducing capacity from 12 to a more defensible number",
            ],
            reasoning=(
                "Profile is mostly complete. Score of 74% is below the 80% auto-approve threshold. "
                "Queued for human auditor review."
            ),
            reviewed_at=None,   # Not yet reviewed
        )
        store.log(
            event_type="seller.onboarding_queued",
            entity_type="seller",
            entity_id=DEMO_IDS["seller3_profile"],
            actor_role="system",
            message=(
                "[DEMO] MarketIntel Pro registration queued for auditor review. "
                "Score: 74% — below auto-approve threshold."
            ),
        )

    if DEMO_IDS["review_seller4"] not in store.seller_onboarding_reviews:
        store.seller_onboarding_reviews[DEMO_IDS["review_seller4"]] = SellerOnboardingReview(
            id=DEMO_IDS["review_seller4"],
            seller_profile_id=DEMO_IDS["seller4_profile"],
            auditor_id=DEMO_IDS["auditor_user"],
            review_status="approved",
            overall_score=0.89,
            dimension_scores={
                "completeness":          0.92,
                "expertise_credibility": 0.92,
                "pricing_clarity":       0.90,
                "category_fit":          0.88,
                "capacity_realism":      0.85,
            },
            passed=True,
            issues=[],
            recommendations=["Consider adding a sample deliverable to benchmark_references."],
            reasoning=(
                "Strong strategy profile with verifiable credentials. "
                "Expertise claims are specific, quantified, and credible. Approved."
            ),
            reviewed_at=now,
        )


# ---------------------------------------------------------------------------
# Demo tasks
# ---------------------------------------------------------------------------

def seed_demo_tasks() -> None:
    """
    Create demo tasks: three in PENDING state and one pre-completed with
    seller result, generalist result, benchmark, and audit result already set.

    The completed task lets the admin/buyer dashboards show real data on
    first load without requiring any manual API calls.
    """
    if DEMO_IDS["task_finance"] not in store.tasks:
        store.tasks[DEMO_IDS["task_finance"]] = Task(
            id=DEMO_IDS["task_finance"],
            buyer_id=DEMO_IDS["buyer_profile"],
            title="Q3 Earnings Analysis — ACME Corp",
            description=(
                "Provide a financial analysis of ACME Corp's Q3 earnings. "
                "Focus on revenue trends, margin changes, and any risk flags."
            ),
            category=TaskCategory.FINANCIAL_RESEARCH,
            requested_output_type=OutputType.REPORT,
            status=TaskStatus.PENDING,
            generalist_comparison_enabled=True,
        )
        store.log(
            event_type="task.created",
            entity_type="task",
            entity_id=DEMO_IDS["task_finance"],
            actor_id=DEMO_IDS["buyer_user"],
            actor_role="buyer",
            message="[DEMO] Task created: 'Q3 Earnings Analysis — ACME Corp' [financial_research]",
        )

    if DEMO_IDS["task_legal"] not in store.tasks:
        store.tasks[DEMO_IDS["task_legal"]] = Task(
            id=DEMO_IDS["task_legal"],
            buyer_id=DEMO_IDS["buyer_profile"],
            title="SaaS Vendor Contract Review",
            description=(
                "Review a standard SaaS vendor agreement. "
                "Flag any non-standard IP, indemnification, or termination clauses."
            ),
            category=TaskCategory.LEGAL_ANALYSIS,
            requested_output_type=OutputType.BULLET_LIST,
            status=TaskStatus.PENDING,
            generalist_comparison_enabled=True,
        )
        store.log(
            event_type="task.created",
            entity_type="task",
            entity_id=DEMO_IDS["task_legal"],
            actor_id=DEMO_IDS["buyer_user"],
            actor_role="buyer",
            message="[DEMO] Task created: 'SaaS Vendor Contract Review' [legal_analysis]",
        )

    if DEMO_IDS["task_market"] not in store.tasks:
        store.tasks[DEMO_IDS["task_market"]] = Task(
            id=DEMO_IDS["task_market"],
            buyer_id=DEMO_IDS["buyer_profile"],
            title="B2B Fintech Competitor Landscape — 2024",
            description=(
                "Map the top 10 competitors in the B2B fintech payments space. "
                "Include market share estimates, differentiators, and recent funding rounds."
            ),
            category=TaskCategory.MARKET_INTELLIGENCE,
            requested_output_type=OutputType.STRUCTURED_JSON,
            status=TaskStatus.PENDING,
            generalist_comparison_enabled=True,
        )
        store.log(
            event_type="task.created",
            entity_type="task",
            entity_id=DEMO_IDS["task_market"],
            actor_id=DEMO_IDS["buyer_user"],
            actor_role="buyer",
            message=(
                "[DEMO] Task created: 'B2B Fintech Competitor Landscape — 2024' "
                "[market_intelligence]"
            ),
        )


def seed_completed_demo_task() -> None:
    """
    Seed one pre-completed task that demonstrates the full workflow:
      task → quote → seller assigned → specialist result → generalist result
      → benchmark comparison → audit result (PASSED)

    This gives every dashboard real data to display on first load without
    requiring manual API calls.
    """
    from .models.task import AuditResult, BenchmarkComparison, Quote

    task_id = DEMO_IDS["task_completed"]
    if task_id in store.tasks:
        return  # Idempotent

    now = datetime.utcnow()

    # --- Accepted quote ---
    quote = Quote(
        id=DEMO_IDS["quote_completed"],
        task_id=task_id,
        seller_id=DEMO_IDS["seller1_profile"],
        proposed_price=75.0,
        estimated_minutes=25,
        confidence_score=0.82,
        notes="Fixed-rate pricing: $75.00/task. Primary specialization in financial research; strong benchmark score (82%); high reputation (4.2/5); $75.00/task; ETA 25min; high confidence (82%). Match score 76%.",
        match_score=0.76,
        fit_explanation="Match score 76%. Primary specialization in financial research; strong benchmark score (82%); high reputation (4.2/5); $75.00/task; ETA 25min; high confidence (82%).",
        score_breakdown={
            "category_relevance": 1.0,
            "benchmark":          0.5,
            "reputation":         0.84,
            "price":              0.39,
            "confidence":         0.82,
            "capacity":           1.0,
        },
        seller_display_name="FinancialResearch Pro",
        accepted=True,
    )
    store.quotes[quote.id] = quote

    # Seller result (mirrors FinancialResearchSeller mock output)
    seller_result = {
        "category": "financial_research",
        "output_type": "report",
        "summary": (
            "[DEMO] Financial analysis of ACME Corp Q3 earnings. "
            "Revenue grew 14% YoY, reaching $182M. Gross margin improved to 71% (+3pp). "
            "EBITDA margin at 22%, driven by operating leverage. "
            "Key risk: elevated debt-to-equity at 1.9x, above sector median of 1.3x. "
            "Recommendation: Hold — Q4 guidance reaffirmed but macro headwinds persist."
        ),
        "key_metrics": {
            "revenue_yoy_growth":  "14%",
            "gross_margin":        "71%",
            "ebitda_margin":       "22%",
            "debt_to_equity":      "1.9x",
            "sector_median_dte":   "1.3x",
        },
        "risk_flags": ["elevated_leverage", "macro_rate_sensitivity", "supply_chain_exposure"],
        "sources": ["[DEMO] ACME Corp 10-Q Q3", "[DEMO] Bloomberg earnings transcript"],
        "mock": True,
    }

    # Generalist result (mirrors GeneralistAgent mock output)
    generalist_result = {
        "category": "financial_research",
        "output_type": "report",
        "summary": (
            "[GENERALIST BASELINE] General analysis for: 'Q3 Earnings Analysis — ACME Corp'. "
            "Reviewed available context regarding financial performance and key business metrics. "
            "Analysis is based on general reasoning without specialized domain tools. "
            "Key findings are plausible but may lack the depth a domain specialist provides. "
            "Further domain-specific verification is recommended before acting on this output."
        ),
        "key_points": [
            "Revenue trends appear consistent with industry benchmarks; "
            "further detailed review of financials is recommended.",
            "Profitability indicators suggest stable operations, "
            "though specific margin data would require access to internal reports.",
            "General risk factors include market conditions and competitive pressures — "
            "specialist validation recommended for investment decisions.",
        ],
        "confidence_note": "Generalist output — produced without domain-specific tools. Confidence: 65%.",
        "mock": True,
        "agent_type": "generalist",
    }

    # Benchmark comparison
    benchmark = BenchmarkComparison(
        id=DEMO_IDS["benchmark_completed"],
        task_id=task_id,
        task_category="financial_research",
        seller_id=DEMO_IDS["seller1_profile"],
        seller_display_name="FinancialResearch Pro",
        generalist_id="demo-generalist",
        generalist_model="mock-generalist-v1",
        seller_score=0.812,
        generalist_score=0.648,
        seller_dimension_scores={"quality": 0.82, "relevance": 0.84, "completeness": 0.80, "genericity": 0.80},
        generalist_dimension_scores={"quality": 0.65, "relevance": 0.66, "completeness": 0.65, "genericity": 0.60},
        specialist_cost=75.0,
        generalist_cost=0.02,
        specialist_eta_minutes=25,
        generalist_eta_minutes=5,
        winner="seller",
        delta=0.164,
        recommendation="use_specialist",
        summary=(
            "Specialist scored 81% vs. generalist 65%. "
            "Winner: specialist (FinancialResearch Pro) (delta +0.164). "
            "Specialist strongest on 'relevance' (+18% over generalist). "
            "Cost: specialist $75.00 vs. generalist $0.02. "
            "Recommendation: use the specialist. "
            "[Mock heuristic scoring — replace with LLM-as-judge for production.]"
        ),
        scoring_method="mock_heuristic",
        mock=True,
    )
    store.benchmark_comparisons[benchmark.id] = benchmark

    # Audit result
    audit = AuditResult(
        id=DEMO_IDS["audit_completed"],
        task_id=task_id,
        auditor_id="demo-auditor",
        composite_score=0.812,
        quality_score=0.812,
        passed=True,
        dimension_scores={"quality": 0.82, "relevance": 0.84, "completeness": 0.80, "genericity": 0.80},
        reasoning=(
            "[SPECIALIST OUTPUT AUDIT] Composite: 81%. "
            "Dimensions — Quality: 82%, Relevance: 84%, Completeness: 80%, Specificity: 80%. "
            "PASSED (threshold 70%). "
            "Generalist comparison: seller wins. "
            "[Mock heuristic scoring — replace with LLM-as-judge for production.]"
        ),
        flags=[],
        recommendations=["Consider adding more source citations for higher completeness score."],
        has_benchmark=True,
        benchmark_comparison_id=DEMO_IDS["benchmark_completed"],
        benchmark_winner="seller",
        benchmark_delta=0.164,
        scoring_method="mock_heuristic",
    )
    store.audit_results[audit.id] = audit

    # The completed task itself
    from .models.enums import AuditStatus
    task = Task(
        id=task_id,
        buyer_id=DEMO_IDS["buyer_profile"],
        title="Q3 Earnings Analysis — ACME Corp (Completed)",
        description=(
            "Provide a financial analysis of ACME Corp's Q3 earnings. "
            "Focus on revenue trends, margin changes, and any risk flags."
        ),
        category=TaskCategory.FINANCIAL_RESEARCH,
        requested_output_type=OutputType.REPORT,
        status=TaskStatus.COMPLETED,
        generalist_comparison_enabled=True,
        shortlisted_seller_ids=[DEMO_IDS["seller1_profile"]],
        selected_seller_id=DEMO_IDS["seller1_profile"],
        selected_quote_id=DEMO_IDS["quote_completed"],
        quote_ids=[DEMO_IDS["quote_completed"]],
        seller_result=seller_result,
        generalist_result=generalist_result,
        benchmark_comparison_id=DEMO_IDS["benchmark_completed"],
        audit_status=AuditStatus.PASSED,
        audit_result_id=DEMO_IDS["audit_completed"],
        completed_at=now,
    )
    store.tasks[task_id] = task

    # Activity log entries for the completed task
    for evt, msg in [
        ("task.submitted",          "[DEMO] Task submitted: 'Q3 Earnings Analysis — ACME Corp (Completed)' [financial_research]"),
        ("marketplace.shortlisted", "[DEMO] Sellers shortlisted: FinancialResearch Pro (match 76%)"),
        ("quote.generated",         "[DEMO] Quote from 'FinancialResearch Pro': $75.00, 25min, match 76%"),
        ("seller.selected",         "[DEMO] Seller 'FinancialResearch Pro' selected. Price: $75.00, ETA: 25min."),
        ("seller.execution_completed", "[DEMO] Specialist 'FinancialResearch Pro' completed task. Confidence: 82%."),
        ("generalist.completed",    "[DEMO] Generalist baseline completed. Confidence: 65%."),
        ("benchmark.completed",     "[DEMO] Benchmark: specialist 81% vs generalist 65% (delta +16%). Winner: seller. use_specialist."),
        ("audit.task_completed",    "[DEMO] Task audit PASSED. Score: 81%. Flags: none."),
    ]:
        store.log(
            event_type=evt,
            entity_type="task",
            entity_id=task_id,
            actor_id=DEMO_IDS["buyer_user"] if "task" in evt or "seller.selected" in evt else None,
            actor_role="buyer" if "task" in evt or "seller.selected" in evt else "system",
            message=msg,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def seed_marketplace_for_pending_tasks() -> None:
    """
    Run marketplace matching on PENDING tasks that have no quotes yet.

    This gives the buyer dashboard real quotes to display on first load —
    the buyer can immediately see ranked sellers and select one.

    Deferred until after registry.seed_mock_agents() runs, which is why
    this is called from main.py:on_startup() after both seed_all() and
    registry.seed_mock_agents() complete.
    """
    from .marketplace.workflow import run_marketplace

    for task in store.tasks.values():
        if str(task.status) == "pending" and not task.quote_ids:
            try:
                run_marketplace(task=task, store=store)
            except Exception as e:
                # Non-fatal — log and continue
                store.log(
                    event_type="seed.marketplace_error",
                    entity_type="task",
                    entity_id=task.id,
                    actor_role="system",
                    message=f"[SEED] Marketplace matching failed for '{task.title}': {e}",
                )


def seed_all() -> None:
    """
    Run all seed steps in dependency order.
    Called once at application startup from main.py.

    Order matters:
      1. Users must exist before profiles
      2. Profiles must exist before tasks and reviews
      3. Tasks must exist before the completed workflow demo
      4. Marketplace matching runs AFTER the registry is populated
         (called separately from main.py:on_startup after seed_mock_agents)
    """
    seed_demo_users()
    seed_demo_profiles()
    seed_onboarding_reviews()
    seed_demo_tasks()
    seed_completed_demo_task()  # Pre-completed task for immediate demo visibility
