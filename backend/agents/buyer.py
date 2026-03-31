"""
Buyer agent implementation.

The buyer agent represents a human buyer's automated counterpart on the platform.
Its primary responsibilities:
  1. Onboarding  — delegate to the onboarding pipeline (onboarding/enrollment.py)
  2. Task acknowledgement — confirm receipt of a task submission
  3. Task creation — construct a well-formed Task from buyer intent

The agent is now a thin adapter over the onboarding pipeline.
All parsing, ingestion, and extraction logic lives in backend/onboarding/.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from ..models.enums import TaskCategory, OutputType, TaskStatus
from ..models.task import Task
from ..models.user import BuyerProfile
from .base import AgentResult, BaseAgent


class BuyerAgent(BaseAgent):
    """
    Agent representing a buyer participant.

    Each buyer has one BuyerAgent instance linked to their BuyerProfile.
    """

    def __init__(self, agent_id: str, profile: BuyerProfile):
        super().__init__(agent_id=agent_id, name=f"BuyerAgent:{profile.id}")
        self.profile = profile

    # ------------------------------------------------------------------
    # Onboarding — delegates to pipeline
    # ------------------------------------------------------------------

    @staticmethod
    def onboard(url: Optional[str], raw_prompt: str) -> BuyerProfile:
        """
        Legacy static adapter kept for backwards compatibility.

        New callers should use run_onboarding() from onboarding/enrollment.py
        directly, which returns the full OnboardingResult with pipeline trace.

        This method is still used by the seed data path (seed.py) where
        no store context is needed.
        """
        # Minimal deterministic profile for the seed path only.
        # The real pipeline is invoked from the /buyer/onboard route.
        organization: Optional[str] = None
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "").split(".")[0]
                organization = domain.capitalize() if domain else None
            except Exception:
                pass

        return BuyerProfile(
            id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            context_source_url=url,
            onboarding_raw_prompt=raw_prompt,
            organization=organization,
            onboarding_source="seed",
            onboarding_confidence=0.3,
        )

    # ------------------------------------------------------------------
    # Task execution (run interface — acknowledgement only)
    # ------------------------------------------------------------------

    def run(self, task: Task) -> AgentResult:
        """
        Buyer agent run() validates and acknowledges a task submission.

        Does not produce a deliverable — that is the seller's job.
        Future: add intent clarification loop before routing.
        """
        return AgentResult(
            agent_id=self.agent_id,
            task_id=task.id,
            success=True,
            content={
                "acknowledged": True,
                "buyer_id": self.profile.id,
                "task_title": task.title,
                "category": task.category,
                "requested_output_type": task.requested_output_type,
            },
            confidence=1.0,
            reasoning="Buyer agent acknowledged task submission.",
        )

    # ------------------------------------------------------------------
    # Task factory helper
    # ------------------------------------------------------------------

    def create_task(
        self,
        title: str,
        description: str,
        category: TaskCategory,
        requested_output_type: OutputType = OutputType.REPORT,
        context_url: Optional[str] = None,
        enable_generalist_comparison: bool = True,
    ) -> Task:
        """
        Construct a Task on behalf of this buyer.

        Future: add task validation (description length, category match,
        content policy check) before creating.
        """
        return Task(
            id=str(uuid.uuid4()),
            buyer_id=self.profile.id,
            title=title,
            description=description,
            category=category,
            requested_output_type=requested_output_type,
            status=TaskStatus.PENDING,
            context_url=context_url,
            generalist_comparison_enabled=enable_generalist_comparison,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
