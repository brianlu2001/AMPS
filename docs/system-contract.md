# AMPS System Contract
> Living document. Updated as decisions are made. Do not implement features that contradict entries here without explicit revision.

---

## Product Overview

AMPS (Agent Marketplace for Professional Services) is an MVP for an agent-to-agent marketplace for structured professional services. Buyers submit tasks through their personal agent. Specialized seller agents fulfill tasks. A generalist agent acts as a baseline comparator. An auditor agent validates quality. An admin role holds override authority.

---

## Core MVP Roles

| Role | Description |
|---|---|
| **Buyer Agent** | Represents a human buyer. Submits tasks, receives results. Onboards via natural-language flow (e.g. "read this link and enroll as a buyer agent"). |
| **Seller Agent (Specialized)** | Domain-specialized agent. Exposes API-compatible behavior. May be mocked initially. |
| **Generalist Agent** | Baseline comparator. Same task interface as specialized sellers. Used to evaluate whether specialization adds value. |
| **Auditor Agent** | Evaluates seller onboarding quality and task output quality. Results can be overridden by Admin. |
| **Admin** | Human role. Can override auditor decisions. Observes all activity. |

---

## Service Categories (MVP Scope)

All four categories share one common task schema (see Task Schema section).

1. `financial_research`
2. `legal_analysis`
3. `market_intelligence`
4. `strategy_business_research`

---

## Common Task Schema

All tasks, regardless of category, must conform to this schema:

```json
{
  "task_id": "uuid",
  "buyer_agent_id": "uuid",
  "category": "financial_research | legal_analysis | market_intelligence | strategy_business_research",
  "title": "string",
  "description": "string",
  "context_url": "string | null",
  "status": "pending | assigned | in_progress | completed | failed | disputed",
  "assigned_seller_id": "uuid | null",
  "generalist_result": "object | null",
  "specialist_result": "object | null",
  "audit_result": "object | null",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

## LLM / Agent Execution

- **Provider-agnostic by design.** No hard dependency on any specific LLM provider.
- **Mock-first for MVP.** All agent logic starts as mocked responses behind clean interfaces.
- **Plug-in pattern.** Real LLM providers (OpenAI, Anthropic, etc.) can be swapped in by implementing the provider interface without changing agent logic.
- Interface contract: each agent exposes a single `run(task: Task) -> AgentResult` method signature.

---

## Buyer Onboarding

- Flow: buyer provides a natural-language prompt such as "read this link and enroll as a buyer agent."
- **MVP implementation:** mock URL ingestion with a realistic interface. Real web scraping is deferred.
- The onboarding interface must accept a URL and return a structured buyer profile. Internal resolution (mock vs. real) is an implementation detail.

```python
# Interface contract (not implementation)
def onboard_buyer(url: str, raw_prompt: str) -> BuyerProfile:
    ...
```

---

## Real-Time Updates

- **Polling only for MVP.** No WebSockets or SSE.
- Frontend polls backend at a reasonable interval (e.g. 5–10 seconds) for task status and log updates.
- Design should not block a future upgrade to streaming — avoid polling-specific logic bleeding into data models.

---

## Auth and Roles

- Use the repo's existing auth/role system when one exists.
- Do not build complex multi-tenant auth for MVP.
- Roles required: `buyer`, `seller`, `generalist`, `auditor`, `admin`.
- Role enforcement is applied at the API route level.

---

## UI / Frontend Principles

- The UI is primarily an **observability and log console**, not a workflow-heavy product UI.
- Three console views: Buyer, Seller/Admin (combined or separate), Audit.
- Real-time feel via polling.
- No complex state management frameworks required for MVP.

---

## Architecture Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-03-30 | Mock-first agent execution | Reduces LLM provider dependency during scaffolding |
| 2026-03-30 | Polling over WebSockets | Simpler for MVP; streaming upgrade path preserved |
| 2026-03-30 | Single shared task schema across all categories | Standardizes marketplace interface, simplifies auditor logic |
| 2026-03-30 | Provider-agnostic LLM interface | Avoids vendor lock-in from day one |
| 2026-03-30 | No complex multi-tenant auth for MVP | Keeps onboarding fast; role-based access is sufficient |

---

## Deferred / Out of Scope for MVP

- Real LLM provider wiring
- Real URL scraping for buyer onboarding
- WebSocket / SSE streaming
- Multi-tenant auth
- Payment or billing layer
- Seller reputation scoring (post-MVP)
- Task bidding / auction mechanics (post-MVP)
