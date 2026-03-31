"""
Base agent interface for AMPS.

Every agent type (buyer, seller, generalist, auditor) inherits from BaseAgent.
The single required method is `run(task) -> AgentResult`.

This interface is intentionally minimal so that:
  1. Mock implementations are trivial to write.
  2. Real LLM-backed implementations only need to satisfy this contract.
  3. The routing and audit layers never need to know how an agent is implemented.

Future: add async support via `async def run(...)` when adding real LLM calls.
Future: add `capabilities() -> AgentCapabilities` for dynamic capability discovery.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..models.task import Task


# ---------------------------------------------------------------------------
# AgentResult — universal output wrapper
# ---------------------------------------------------------------------------

class AgentResult(BaseModel):
    """
    The standard output produced by any agent's run() call.

    Every agent — buyer, seller, generalist, auditor — returns this shape.
    The `content` field holds the agent-specific payload (report text,
    structured JSON, audit scores, etc.).

    Future: add token_usage, latency_ms, model_id once real LLM calls are wired.
    """
    agent_id: str
    task_id: str
    success: bool
    content: Dict[str, Any]               # Agent-specific result payload
    confidence: float = 0.0               # 0.0–1.0; agent's self-reported confidence
    reasoning: Optional[str] = None       # Optional chain-of-thought / explanation
    error: Optional[str] = None           # Populated if success=False
    produced_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# BaseAgent — abstract base class
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """
    Abstract base class all AMPS agents must implement.

    agent_id: stable identifier for this agent instance (maps to User.id).
    name: display name used in logs and the observability console.
    """

    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name

    @abstractmethod
    def run(self, task: Task) -> AgentResult:
        """
        Execute this agent against the given task and return a result.

        Implementations must:
          - Always return an AgentResult (never raise unless truly unrecoverable).
          - Set success=False and populate error if execution fails.
          - Populate content with whatever structured output this agent produces.

        Future: signature will gain `context: AgentContext` for session state,
        conversation history, and tool access.
        """
        ...

    def describe(self) -> Dict[str, Any]:
        """
        Returns a human-readable description of this agent for the console.
        Subclasses should override to add capability details.
        """
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "type": self.__class__.__name__,
        }
