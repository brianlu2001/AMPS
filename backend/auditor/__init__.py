"""
AMPS Auditor Engine.

Modules:
  scoring      — reusable dimension scorers shared by both audit workflows
  task_audit   — task output audit workflow
  onboarding   — seller onboarding audit workflow

The auditor engine is separate from agents/auditor.py (the agent class).
The agent class is a thin orchestrator; the engine does the actual scoring.

This separation allows:
  - Scoring logic to be tested independently of the agent lifecycle
  - Real LLM judge to be dropped in by replacing scoring functions
  - Both workflows to share common primitives (flags, thresholds, etc.)
"""

# Quality threshold shared across both workflows
QUALITY_THRESHOLD = 0.70
ONBOARDING_AUTO_APPROVE_THRESHOLD = 0.80
