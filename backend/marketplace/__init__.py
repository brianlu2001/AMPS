"""
AMPS Marketplace Engine.

Modules:
  matching  — weighted seller scoring and shortlisting
  quoting   — quote generation from match results
  workflow  — orchestrator (submit → match → quote → select → execute)

Entry point: workflow.run_marketplace(task, store, registry) -> MarketplaceResult
"""
