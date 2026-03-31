"""
Generalist agent — benchmark/control baseline.

The generalist is NOT a marketplace seller. It is a system-level agent that
runs in parallel with the selected specialist to provide a comparison baseline.

Purpose:
  Demonstrate (or disprove) the thesis that specialized seller agents
  produce meaningfully better outputs than a capable general-purpose LLM
  given the same task brief and no domain-specific tools or prompting.

Design principles:
  1. The generalist uses the SAME task input as the specialist.
  2. The generalist does NOT receive domain-specific tools, indexes, or prompts.
  3. Output structure is intentionally less rich than specialist output.
     This reflects real-world LLM behavior: general models reason broadly
     but lack the depth a domain specialist provides.
  4. Confidence is set to 0.65 (below most specialists at 0.75–0.85).

MVP: deterministic mock output. Realistic enough to show clear differentiation
from specialist output when fed to the comparison scoring engine.

Future: wire to a real LLM (GPT-4o, Claude Sonnet) with a simple system prompt:
  "You are a helpful assistant. Answer the following professional services task."
  — No domain-specific instructions, no tools, no retrieval.
"""

from __future__ import annotations

from typing import Any, Dict

from ..models.enums import TaskCategory
from ..models.task import Task
from ..models.user import GeneralistProfile
from .base import AgentResult, BaseAgent

# Generalist confidence is intentionally below specialist baselines
GENERALIST_CONFIDENCE = 0.65


class GeneralistAgent(BaseAgent):
    """
    Baseline generalist agent. Handles all task categories without specialization.

    Critical design rule: do NOT add category-specific domain logic here.
    The absence of specialization is the entire point of this agent.
    Any improvement in quality here dilutes the comparison signal.
    """

    def __init__(self, agent_id: str, profile: GeneralistProfile):
        super().__init__(agent_id=agent_id, name=profile.display_name)
        self.profile = profile

    def run(self, task: Task) -> AgentResult:
        """
        Produce a generalist baseline result for any task category.

        MVP: deterministic mock with category-aware but intentionally non-specialized
        content. Output is structurally simpler than specialist output to reflect
        the real-world generalist disadvantage on structured professional tasks.

        Future: replace with real LLM call using a vanilla system prompt —
        no domain context, no retrieval, no specialist tools.
        """
        content = self._generate_mock_content(task)
        return AgentResult(
            agent_id=self.agent_id,
            task_id=task.id,
            success=True,
            content=content,
            confidence=GENERALIST_CONFIDENCE,
            reasoning=(
                "Generalist agent produced a general-purpose analysis. "
                "No domain-specific tools, indexes, or prompting were used. "
                "This is the baseline comparator output."
            ),
        )

    def _generate_mock_content(self, task: Task) -> Dict[str, Any]:
        """
        Produce mock generalist output.

        Intentional limitations vs. specialist outputs:
          - Shorter summary (less depth)
          - Only key_points list — no domain-specific structured fields
          - No sources list
          - No risk_flags (requires domain knowledge to identify)
          - Generic language markers present (these trigger penalties in comparison scoring)
          - Fewer total keys (reduces quality + completeness scores)

        This structure is calibrated so the comparison engine produces realistic
        deltas where specialists score 10–25% higher across dimensions.

        Future: replace with real LLM call. The output will naturally be richer
        than this mock but still lack specialist-level depth.
        """
        # Category-specific hint for the summary — generic framing, not domain analysis
        category_context: Dict[str, dict] = {
            TaskCategory.FINANCIAL_RESEARCH: {
                "hint": "financial performance and key business metrics",
                "points": [
                    "Revenue trends appear consistent with industry benchmarks; "
                    "further detailed review of financials is recommended.",
                    "Profitability indicators suggest stable operations, "
                    "though specific margin data would require access to internal reports.",
                    "General risk factors include market conditions and competitive pressures — "
                    "specialist validation recommended for investment decisions.",
                ],
            },
            TaskCategory.LEGAL_ANALYSIS: {
                "hint": "legal clauses, terms, and compliance considerations",
                "points": [
                    "Standard commercial terms appear generally present; "
                    "unusual provisions may require specialist review.",
                    "Indemnification and liability terms should be reviewed by qualified counsel "
                    "before signing any binding agreements.",
                    "Regulatory compliance status cannot be confirmed without jurisdiction-specific "
                    "specialist analysis.",
                ],
            },
            TaskCategory.MARKET_INTELLIGENCE: {
                "hint": "market dynamics, competitive positioning, and growth trends",
                "points": [
                    "Market appears competitive with multiple established players; "
                    "differentiation strategy is important for new entrants.",
                    "Growth trends in this space are generally positive based on available "
                    "public information, though specific sizing requires specialist data sources.",
                    "Competitive landscape analysis would benefit from primary research "
                    "and access to proprietary market databases.",
                ],
            },
            TaskCategory.STRATEGY_BUSINESS_RESEARCH: {
                "hint": "strategic options and business positioning",
                "points": [
                    "Multiple strategic pathways appear viable; "
                    "the optimal choice depends on specific organizational constraints.",
                    "Market entry or expansion strategies should be validated with "
                    "detailed competitive and financial modelling.",
                    "Execution risk is a primary concern across all strategic options — "
                    "specialist advisory recommended for implementation planning.",
                ],
            },
        }

        cat = task.category  # type: ignore[assignment]
        ctx = category_context.get(cat, {
            "hint": "the requested topic",
            "points": [
                "General analysis has been conducted based on available context.",
                "Further specialist review is recommended for high-stakes decisions.",
                "Key findings should be validated against domain-specific data sources.",
            ],
        })

        return {
            "category": str(task.category),
            "output_type": str(task.requested_output_type),
            "summary": (
                f"[GENERALIST BASELINE] General analysis for: '{task.title}'. "
                f"Reviewed available context regarding {ctx['hint']}. "
                "Analysis is based on general reasoning without specialized domain tools. "
                "Key findings are plausible but may lack the depth a domain specialist provides. "
                "Further domain-specific verification is recommended before acting on this output."
            ),
            "key_points": ctx["points"],
            "confidence_note": (
                "Generalist output — produced without domain-specific tools, data sources, "
                "or specialized prompting. Confidence: 65%. "
                "Specialist review is recommended for high-stakes decisions."
            ),
            # Note: no risk_flags, no key_metrics, no sources, no domain-specific fields.
            # These absences are intentional and are penalised by the comparison scorer.
            "mock": True,
            "agent_type": "generalist",
        }

    def describe(self) -> Dict[str, Any]:
        base = super().describe()
        base.update({
            "role": "benchmark_baseline",
            "model_identifier": self.profile.model_identifier,
            "cost_per_task": self.profile.cost_per_task,
            "estimated_minutes": self.profile.estimated_minutes,
            "confidence_baseline": self.profile.confidence_baseline,
            "tasks_completed": self.profile.tasks_completed,
            "benchmark_score": self.profile.benchmark_score,
            "record": {
                "wins": self.profile.wins,
                "losses": self.profile.losses,
                "ties": self.profile.ties,
            },
        })
        return base
