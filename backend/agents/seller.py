"""
Seller agent base class and four specialized MVP seller implementations.

Architecture:
  - BaseSellerAgent: abstract base with shared quote/capacity logic.
  - One concrete subclass per service category.
  - All sellers share the same run(task) -> AgentResult interface.

MVP: all `run()` implementations produce deterministic mock results.
The mock content is realistic in structure so the auditor and benchmark
comparison layers can process it without changes when real LLMs are added.

Future: replace `_generate_mock_content()` in each class with an LLM call
that passes task.description + task.context_url as the prompt.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.enums import TaskCategory, OutputType
from ..models.task import Task, Quote
from ..models.user import SellerProfile
from .base import AgentResult, BaseAgent


# ---------------------------------------------------------------------------
# Base Seller Agent
# ---------------------------------------------------------------------------

class BaseSellerAgent(BaseAgent):
    """
    Abstract seller agent. All specialized sellers extend this class.

    Provides:
      - generate_quote(): produces a Quote for a given task.
      - has_capacity(): checks if seller can accept more tasks.
      - run(): must be implemented by each subclass.
    """

    def __init__(self, agent_id: str, profile: SellerProfile):
        super().__init__(agent_id=agent_id, name=profile.display_name)
        self.profile = profile

    def generate_quote(self, task: Task) -> Quote:
        """
        Generate a pricing quote for a task.

        MVP: returns fixed base_price from profile. 
        Future: pass task complexity signals to a pricing model.
        """
        price = self.profile.base_price or 50.0  # Default fallback price
        return Quote(
            task_id=task.id,
            seller_id=self.profile.id,
            proposed_price=price,
            estimated_minutes=self.profile.estimated_minutes,
            confidence_score=self.profile.confidence_score,
            notes=f"Standard rate for {task.category} tasks.",
        )

    def has_capacity(self, current_load: int) -> bool:
        """Returns True if seller can accept more tasks."""
        return current_load < self.profile.capacity

    @abstractmethod
    def _generate_mock_content(self, task: Task) -> Dict[str, Any]:
        """
        Produce mock result content for this seller's category.
        Future: replace with real LLM call.
        """
        ...

    def run(self, task: Task) -> AgentResult:
        """
        Execute the seller's work on the task.

        Wraps _generate_mock_content() with standard AgentResult structure.
        Error handling is minimal for MVP — add retry/timeout logic later.
        """
        try:
            content = self._generate_mock_content(task)
            return AgentResult(
                agent_id=self.agent_id,
                task_id=task.id,
                success=True,
                content=content,
                confidence=self.profile.confidence_score,
                reasoning=f"{self.name} completed task using specialized domain knowledge.",
            )
        except Exception as e:
            return AgentResult(
                agent_id=self.agent_id,
                task_id=task.id,
                success=False,
                content={},
                confidence=0.0,
                error=str(e),
            )

    def describe(self) -> Dict[str, Any]:
        base = super().describe()
        base.update({
            "specializations": self.profile.specialization_categories,
            "pricing_model": self.profile.pricing_model,
            "base_price": self.profile.base_price,
            "confidence_score": self.profile.confidence_score,
            "approval_status": self.profile.approval_status,
        })
        return base


# ---------------------------------------------------------------------------
# Specialized Seller: Financial Research
# ---------------------------------------------------------------------------

class FinancialResearchSeller(BaseSellerAgent):
    """
    Specialized seller for financial_research tasks.

    Mock output simulates: company financial summaries, ratio analysis,
    earnings breakdowns, risk flags.

    Future LLM prompt context: SEC filings, earnings transcripts, market data APIs.
    """

    def _generate_mock_content(self, task: Task) -> Dict[str, Any]:
        return {
            "category": TaskCategory.FINANCIAL_RESEARCH,
            "output_type": task.requested_output_type,
            "summary": (
                f"[MOCK] Financial analysis for: '{task.title}'. "
                "Revenue growth of 12% YoY observed. Gross margin stable at 68%. "
                "Key risk: elevated debt-to-equity ratio at 1.8x. "
                "Recommendation: Hold pending Q3 earnings confirmation."
            ),
            "key_metrics": {
                "revenue_growth_yoy": "12%",
                "gross_margin": "68%",
                "debt_to_equity": "1.8x",
                "pe_ratio": "24.5",
            },
            "risk_flags": ["elevated_leverage", "macro_rate_sensitivity"],
            "sources": ["[MOCK] SEC 10-K filing", "[MOCK] Bloomberg terminal"],
            "mock": True,
        }


# ---------------------------------------------------------------------------
# Specialized Seller: Legal Analysis
# ---------------------------------------------------------------------------

class LegalAnalysisSeller(BaseSellerAgent):
    """
    Specialized seller for legal_analysis tasks.

    Mock output simulates: contract clause review, regulatory compliance checks,
    risk exposure summaries.

    Future LLM prompt context: contract text, jurisdiction, regulatory database.
    """

    def _generate_mock_content(self, task: Task) -> Dict[str, Any]:
        return {
            "category": TaskCategory.LEGAL_ANALYSIS,
            "output_type": task.requested_output_type,
            "summary": (
                f"[MOCK] Legal analysis for: '{task.title}'. "
                "Identified 2 non-standard clauses in Section 4.2 (indemnification) "
                "and Section 7 (IP assignment). Recommend counsel review before signing. "
                "No regulatory violations detected under current jurisdiction."
            ),
            "clauses_reviewed": 14,
            "risk_flags": ["broad_indemnification", "ip_assignment_ambiguity"],
            "compliance_status": "tentatively_compliant",
            "recommended_actions": [
                "Clarify IP assignment scope in Section 7",
                "Negotiate indemnification cap in Section 4.2",
            ],
            "sources": ["[MOCK] Contract text", "[MOCK] Jurisdiction regulatory database"],
            "mock": True,
        }


# ---------------------------------------------------------------------------
# Specialized Seller: Market Intelligence
# ---------------------------------------------------------------------------

class MarketIntelligenceSeller(BaseSellerAgent):
    """
    Specialized seller for market_intelligence tasks.

    Mock output simulates: competitor landscape, market sizing, trend analysis.

    Future LLM prompt context: web search results, industry reports, news feeds.
    """

    def _generate_mock_content(self, task: Task) -> Dict[str, Any]:
        return {
            "category": TaskCategory.MARKET_INTELLIGENCE,
            "output_type": task.requested_output_type,
            "summary": (
                f"[MOCK] Market intelligence for: '{task.title}'. "
                "Total addressable market estimated at $4.2B. "
                "Top 3 competitors hold 61% combined market share. "
                "Key trend: AI-enabled workflows growing at 34% CAGR."
            ),
            "market_size_usd_bn": 4.2,
            "top_competitors": [
                {"name": "[MOCK] CompetitorA", "market_share": "28%"},
                {"name": "[MOCK] CompetitorB", "market_share": "21%"},
                {"name": "[MOCK] CompetitorC", "market_share": "12%"},
            ],
            "growth_drivers": ["AI adoption", "regulatory tailwinds", "SMB digitization"],
            "risk_factors": ["market_saturation_in_enterprise", "pricing_pressure"],
            "sources": ["[MOCK] Industry report", "[MOCK] News aggregator"],
            "mock": True,
        }


# ---------------------------------------------------------------------------
# Specialized Seller: Strategy / Business Research
# ---------------------------------------------------------------------------

class StrategyResearchSeller(BaseSellerAgent):
    """
    Specialized seller for strategy_business_research tasks.

    Mock output simulates: strategic options analysis, go-to-market frameworks,
    competitive positioning recommendations.

    Future LLM prompt context: company context, market data, strategic frameworks.
    """

    def _generate_mock_content(self, task: Task) -> Dict[str, Any]:
        return {
            "category": TaskCategory.STRATEGY_BUSINESS_RESEARCH,
            "output_type": task.requested_output_type,
            "summary": (
                f"[MOCK] Strategy analysis for: '{task.title}'. "
                "Recommended approach: land-and-expand GTM targeting mid-market. "
                "Differentiation lever: proprietary data moat and integrations. "
                "Primary risk: execution bandwidth given current team size."
            ),
            "strategic_options": [
                {"option": "Land-and-expand mid-market", "fit_score": 0.85},
                {"option": "Direct enterprise sales", "fit_score": 0.62},
                {"option": "PLG + freemium", "fit_score": 0.71},
            ],
            "recommended_option": "Land-and-expand mid-market",
            "key_assumptions": [
                "ACV > $15K is achievable",
                "Sales cycle < 60 days for mid-market",
            ],
            "risk_flags": ["team_bandwidth", "competitive_commoditization"],
            "sources": ["[MOCK] Internal data", "[MOCK] Market comparables"],
            "mock": True,
        }
