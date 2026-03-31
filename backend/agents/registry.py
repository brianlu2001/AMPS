"""
Agent registry — central store for all active agent instances.

The registry holds in-memory references to:
  - All registered seller agents (by seller_id)
  - The generalist agent (singleton)
  - The auditor agent (singleton for MVP; extend to pool later)

This is the single lookup point for the routing layer and API routes.
No database required for MVP — registry is seeded at startup with
mock agents.

Future: back the registry with a database so agents persist across restarts.
Future: support dynamic agent registration via the seller onboarding API.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..models.enums import TaskCategory
from ..models.user import (
    AuditorProfile,
    GeneralistProfile,
    SellerProfile,
)
from .auditor import AuditorAgent
from .generalist import GeneralistAgent
from .seller import (
    BaseSellerAgent,
    FinancialResearchSeller,
    LegalAnalysisSeller,
    MarketIntelligenceSeller,
    StrategyResearchSeller,
)


class AgentRegistry:
    """
    Central registry for all agent instances.

    Usage:
        registry = AgentRegistry()
        registry.seed_mock_agents()
        seller = registry.get_seller_for_category(TaskCategory.FINANCIAL_RESEARCH)
    """

    def __init__(self):
        self._sellers: Dict[str, BaseSellerAgent] = {}        # seller_id -> agent
        self._generalist: Optional[GeneralistAgent] = None
        self._auditor: Optional[AuditorAgent] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_seller(self, agent: BaseSellerAgent) -> None:
        self._sellers[agent.profile.id] = agent

    def set_generalist(self, agent: GeneralistAgent) -> None:
        self._generalist = agent

    def set_auditor(self, agent: AuditorAgent) -> None:
        self._auditor = agent

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_seller(self, seller_id: str) -> Optional[BaseSellerAgent]:
        return self._sellers.get(seller_id)

    def get_seller_for_category(self, category: TaskCategory) -> Optional[BaseSellerAgent]:
        """
        Return the first approved seller that handles the given category.

        MVP: returns first match. 
        Future: implement routing strategy (cheapest, fastest, highest-rated,
        auction-based) as a configurable RoutingStrategy class.
        """
        from ..models.enums import ApprovalStatus
        for seller in self._sellers.values():
            if (
                category in seller.profile.specialization_categories
                and seller.profile.approval_status == ApprovalStatus.APPROVED
            ):
                return seller
        return None

    def get_generalist(self) -> Optional[GeneralistAgent]:
        return self._generalist

    def get_auditor(self) -> Optional[AuditorAgent]:
        return self._auditor

    def list_sellers(self) -> List[BaseSellerAgent]:
        return list(self._sellers.values())

    # ------------------------------------------------------------------
    # Mock seed data
    # ------------------------------------------------------------------

    def seed_mock_agents(self) -> None:
        """
        Populate the registry with mock seller agents, generalist, and auditor.

        Uses stable IDs from seed.DEMO_IDS so the registry agent_id keys align
        with the store.sellers dict populated by seed_demo_profiles().

        Seller3 (MarketIntel, NEEDS_REVIEW) is still registered in the execution
        registry so it can run tasks once approved — the approval_status gate
        in get_seller_for_category() prevents auto-routing to unapproved sellers.

        Future: replace with a database query that loads all approved SellerProfiles
        and instantiates their agent class on startup.
        """
        from datetime import datetime
        from ..models.enums import ApprovalStatus, PricingModel
        # Import stable IDs from seed module to keep IDs consistent
        from ..seed import DEMO_IDS

        # --- Sellers — stable IDs aligned with seed.py ---
        seller_configs = [
            (
                FinancialResearchSeller,
                DEMO_IDS["seller1_profile"],
                DEMO_IDS["seller1_user"],
                "FinancialResearch Pro",
                [TaskCategory.FINANCIAL_RESEARCH],
                75.0,
                ApprovalStatus.APPROVED,
            ),
            (
                LegalAnalysisSeller,
                DEMO_IDS["seller2_profile"],
                DEMO_IDS["seller2_user"],
                "LegalAnalysis Pro",
                [TaskCategory.LEGAL_ANALYSIS],
                95.0,
                ApprovalStatus.APPROVED,
            ),
            (
                MarketIntelligenceSeller,
                DEMO_IDS["seller3_profile"],
                DEMO_IDS["seller3_user"],
                "MarketIntel Pro",
                [TaskCategory.MARKET_INTELLIGENCE],
                65.0,
                ApprovalStatus.NEEDS_REVIEW,  # Not yet approved — won't receive routed tasks
            ),
            (
                StrategyResearchSeller,
                DEMO_IDS["seller4_profile"],
                DEMO_IDS["seller4_user"],
                "Strategy Pro",
                [TaskCategory.STRATEGY_BUSINESS_RESEARCH],
                85.0,
                ApprovalStatus.APPROVED,
            ),
        ]

        import uuid as _uuid

        for (AgentClass, profile_id, user_id, display_name,
             categories, base_price, approval_status) in seller_configs:
            sid = profile_id or str(_uuid.uuid4())
            uid = user_id or str(_uuid.uuid4())
            profile = SellerProfile(
                id=sid,
                user_id=uid,
                display_name=display_name,
                specialization_categories=categories,
                supported_output_types=["report", "summary", "structured_json", "bullet_list"],
                pricing_model=PricingModel.FIXED,
                base_price=base_price,
                confidence_score=0.82,
                capacity=10,
                reputation_score=4.2 if approval_status == ApprovalStatus.APPROVED else 0.0,
                approval_status=approval_status,
                approved_at=datetime.utcnow() if approval_status == ApprovalStatus.APPROVED else None,
                estimated_minutes=25,
            )
            self.register_seller(AgentClass(agent_id=sid, profile=profile))

        # --- Generalist ---
        gen_id = str(_uuid.uuid4())
        gen_profile = GeneralistProfile(
            id=gen_id,
            user_id=str(_uuid.uuid4()),
            display_name="Generalist Baseline",
            model_identifier="mock-generalist-v1",
        )
        self.set_generalist(GeneralistAgent(agent_id=gen_id, profile=gen_profile))

        # --- Auditor ---
        aud_id = str(_uuid.uuid4())
        aud_profile = AuditorProfile(
            id=aud_id,
            user_id=str(_uuid.uuid4()),
            display_name="Auditor",
            specialization_categories=[],  # Covers all categories
        )
        self.set_auditor(AuditorAgent(agent_id=aud_id, profile=aud_profile))


# ---------------------------------------------------------------------------
# Singleton registry instance — imported by routes and services
# ---------------------------------------------------------------------------

# Future: replace with dependency injection (FastAPI Depends) for testability.
registry = AgentRegistry()
