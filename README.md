# AMPS — Agent Marketplace for Professional Services

> **Living system contract.** This README describes what exists, how it works, what is mocked, and what needs enhancement. It is the authoritative reference for understanding and extending the MVP.
>
> Architectural decisions are also recorded in `docs/system-contract.md`.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [MVP Goals](#2-mvp-goals)
3. [Why Specialized Agents vs. Generalist Agents](#3-why-specialized-agents-vs-generalist-agents)
4. [Core Roles](#4-core-roles)
5. [End-to-End Workflow](#5-end-to-end-workflow)
6. [Buyer Onboarding Flow](#6-buyer-onboarding-flow)
7. [Seller Onboarding Flow](#7-seller-onboarding-flow)
8. [Marketplace Matching and Quote Selection](#8-marketplace-matching-and-quote-selection)
9. [Generalist Benchmark Layer](#9-generalist-benchmark-layer)
10. [Auditor Layer](#10-auditor-layer)
11. [UI / Dashboard Views](#11-ui--dashboard-views)
12. [Marketplace Dynamics and Pricing Metrics](#12-marketplace-dynamics-and-pricing-metrics)
13. [Repo Structure](#13-repo-structure)
14. [API Endpoints and Key Functions](#14-api-endpoints-and-key-functions)
15. [Data Model Summary](#15-data-model-summary)
16. [Current Limitations and Mocked Components](#16-current-limitations-and-mocked-components)
17. [Scalability and Rewrite Notes](#17-scalability-and-rewrite-notes)
18. [Suggested Next Enhancements](#18-suggested-next-enhancements)
19. [Quick Start](#19-quick-start)
20. [Vercel Deployment](#20-vercel-deployment)

---

## 1. Project Overview

AMPS is an **agent-to-agent marketplace for structured professional services**. Buyers submit tasks through their personal buyer agent. Specialized seller agents compete for and fulfill those tasks. A generalist agent runs in parallel as a baseline comparator. An auditor agent evaluates output quality and seller credentials. An admin role holds final governance authority.

The system is designed to answer one central question:

> **Do specialized domain agents produce meaningfully better outputs than a strong general-purpose agent for structured professional tasks?**

Everything in the system — the benchmark layer, the audit dimensions, the pricing model — is built to generate evidence for or against that thesis.

**Current state:** Full MVP scaffold, mock LLM execution, in-memory store, polling-based observability UI.

---

## 2. MVP Goals

| Goal | Status |
|---|---|
| Buyer onboarding via natural-language instruction + URL | ✅ Implemented (mock URL parsing with real HTTP fallback) |
| Seller registration with expertise claims + auditor review | ✅ Implemented |
| Marketplace matching (weighted 6-dimension scoring) | ✅ Implemented |
| Quote generation and buyer-driven seller selection | ✅ Implemented |
| Specialist seller execution (4 categories) | ✅ Implemented (deterministic mock) |
| Generalist baseline execution in parallel | ✅ Implemented (deterministic mock) |
| Benchmark comparison (specialist vs. generalist) | ✅ Implemented (heuristic scoring) |
| Task output audit (4 dimensions) | ✅ Implemented (heuristic scoring) |
| Seller onboarding audit (5 dimensions) | ✅ Implemented (heuristic scoring) |
| Admin override of audit decisions | ✅ Implemented |
| Role-based access (buyer / seller / auditor / admin) | ✅ Implemented (JWT + X-User-Id dev bypass) |
| Observability console (role-gated dashboards) | ✅ Implemented (Next.js, polling) |
| Marketplace analytics (pricing, supply/demand, utilization) | ✅ Implemented |
| Real LLM execution | ❌ Deferred — interfaces ready, mocks in place |
| Database persistence | ❌ Deferred — in-memory store only |
| Payment / escrow | ❌ Out of scope for MVP |

---

## 3. Why Specialized Agents vs. Generalist Agents

The central thesis of AMPS is that **domain-specialized agents outperform general-purpose LLMs** on structured professional tasks. This is not assumed — it is measured.

Every completed task where `generalist_comparison_enabled=True` produces a `BenchmarkComparison` record that scores both outputs across four dimensions:

| Dimension | What it measures |
|---|---|
| **Quality** | Depth, reasoning, task alignment |
| **Relevance** | How specifically the output addresses the task brief |
| **Completeness** | Presence of expected structural elements |
| **Genericity** (inverted) | Domain-specific content vs. generic statements |

The scoring engine (`benchmark/comparison.py`) applies **asymmetric rules**: specialists receive bonuses for domain-specific fields (key_metrics, risk_flags, clauses_reviewed, etc.) while generalists are penalised for hedge language ("without specialized tools", "general reasoning", etc.). This asymmetry reflects the real-world expectation.

The `admin/marketplace` endpoint aggregates specialist win rates, average quality deltas, and per-category breakdowns — giving a growing body of evidence as tasks accumulate.

**To swap in a real LLM generalist:** replace `GeneralistAgent._generate_mock_content()` with a call to your LLM provider using a vanilla system prompt and no domain tools. The comparison layer requires no changes.

---

## 4. Core Roles

### Buyer
- Represents a human professional who needs research or analysis done.
- Enrolls via a natural-language instruction (e.g. "Read this link and enroll me as a buyer agent").
- Submits tasks, views quotes, selects a seller, and receives delivered outputs.
- Can see only their own tasks, quotes, outputs, and audit results.
- **Model:** `User` (role=buyer) + `BuyerProfile`

### Seller (Specialized)
- Represents a domain-expert agent covering one or more of the four service categories.
- Registers with expertise claims, pricing, and capacity declarations.
- Goes through an onboarding audit before becoming active on the marketplace.
- Executes tasks when assigned; their output is scored by the auditor and compared to the generalist.
- **Model:** `User` (role=seller) + `SellerProfile`
- **Execution classes:** `FinancialResearchSeller`, `LegalAnalysisSeller`, `MarketIntelligenceSeller`, `StrategyResearchSeller`

### Generalist (Benchmark)
- A system-level control agent, not a marketplace seller.
- Runs the same task with the same brief, but without domain tools, indexes, or specialized prompting.
- Exists solely to provide a quality baseline for comparison.
- **Model:** `User` (role=generalist) + `GeneralistProfile`
- **Execution class:** `GeneralistAgent`

### Auditor
- A governance-level agent, not a marketplace seller.
- Runs two workflows: seller onboarding audit and task output audit.
- Decisions can be overridden by admin.
- **Model:** `User` (role=auditor) + `AuditorProfile`
- **Execution class:** `AuditorAgent`

### Admin
- Human role with full read access and override authority.
- Can approve/reject sellers, override audit decisions, and view all marketplace activity.
- Only role that can access the full activity log, all tasks, and marketplace analytics.
- **Model:** `User` (role=admin)

---

## 5. End-to-End Workflow

```
1. BUYER ONBOARDING
   POST /buyer/onboard
   Instruction + URL → parse → fetch → extract profile → BuyerProfile created

2. TASK SUBMISSION + MARKETPLACE MATCHING
   POST /buyer/tasks
   Task created → marketplace matching runs immediately
   → 6-dimension seller scoring → shortlist → quote generation
   Response includes task + marketplace result (quotes ranked by match score)

3. SELLER SELECTION
   POST /buyer/tasks/{id}/select-seller  { seller_id }
   Buyer accepts a quote → task status: PENDING → ASSIGNED

4. SELLER EXECUTION
   POST /seller/tasks/{id}/run?seller_id=...
   Specialist runs → task.seller_result populated
   Generalist runs in parallel (if enabled) → task.generalist_result populated
   BenchmarkComparison created → task status: ASSIGNED → COMPLETED

5. AUDIT
   POST /audit/tasks/{id}
   Auditor scores seller output across 4 dimensions
   AuditResult created → task.audit_status: PASSED | FAILED
   If admin disagrees: POST /admin/audit/{audit_id}/override

6. OBSERVABILITY
   GET /admin/logs          — full activity feed
   GET /admin/marketplace   — supply/demand analytics, pricing, utilization
   GET /admin/benchmark/summary — specialist vs. generalist win rates
```

**Task status lifecycle:**
```
PENDING → ASSIGNED → IN_PROGRESS → COMPLETED | FAILED | DISPUTED
```

**Audit status lifecycle:**
```
NOT_STARTED → IN_REVIEW → PASSED | FAILED | OVERRIDDEN
```

---

## 6. Buyer Onboarding Flow

**Entry point:** `POST /buyer/onboard` → `onboarding/enrollment.py:run_onboarding()`

The buyer onboarding pipeline has four stages. Each stage is a separate module, making them independently testable and replaceable.

```
Stage 1 — Instruction Parsing  (onboarding/instruction_parser.py)
  Input:  "Read this link and enroll me as a buyer agent."
  Output: ParsedInstruction { intent, url_in_text, name_hint, preferred_categories }
  How:    Keyword scan (enroll/register/etc.), regex URL extraction,
          name/org pattern matching, category keyword detection

Stage 2 — URL Ingestion  (onboarding/ingestion.py)
  Input:  URL (from instruction text or separate field)
  Output: IngestionResult { raw_text, title, domain, status, word_count }
  How:    HttpIngestionProvider → real httpx GET + HTML stripping
          MockIngestionProvider → domain-keyed mock corpus (fallback)
  Config: INGESTION_PROVIDER=http|mock, INGESTION_FALLBACK_TO_MOCK=true

Stage 3 — Profile Extraction  (onboarding/profile_extractor.py)
  Input:  IngestionResult + ParsedInstruction
  Output: ExtractedProfile { organization, industry_hint, preferred_categories, use_case_summary }
  How:    Regex patterns on ingested text, keyword vocabulary matching
  ⚠ MVP: heuristic extraction only — no LLM

Stage 4 — Enrollment  (onboarding/enrollment.py)
  Input:  ExtractedProfile + user_id + store
  Output: OnboardingResult { success, profile, message, pipeline_trace, warnings }
  How:    Validates inputs, checks for duplicate, creates BuyerProfile,
          persists to store, emits buyer.onboarded ActivityLog
```

**OnboardingResult** contains the full pipeline trace so the buyer console can show exactly what was parsed, fetched, and extracted — useful for debugging and demos.

**Future upgrade path:** Replace `profile_extractor.py` internals with an LLM call. The `ExtractedProfile` dataclass is the output schema — keep it as-is. The instruction parser and ingestion layer are already production-quality and do not need LLM replacement.

---

## 7. Seller Onboarding Flow

**Entry point:** `POST /seller/register` → `seller_onboarding/registration.py:run_seller_registration()`

```
Stage 1 — Validation  (seller_onboarding/validation.py)
  13 field-level checks: display_name length, description min/max,
  valid categories, valid output types, pricing consistency,
  ETA bounds, capacity bounds, confidence range, expertise claims,
  email/URL format.
  Output: ValidationResult { valid, errors[], warnings[] }

Stage 2 — Profile Build  (registration.py:_build_profile())
  Assembles SellerProfile from validated request.
  Sets approval_status = NEEDS_REVIEW.

Stage 3 — Auditor Review Trigger  (registration.py:_trigger_auditor_review())
  Auto-scores the profile across 5 dimensions:
    completeness, expertise_credibility, pricing_clarity, category_fit, capacity_realism
  If score ≥ 80% AND no issues → auto-approve (status = APPROVED)
  Otherwise → NEEDS_REVIEW, queued for human auditor
  Creates SellerOnboardingReview record.

Stage 4 — Persist + Register  (registration.py:run_seller_registration())
  Saves SellerProfile + SellerOnboardingReview to store.
  Instantiates the correct seller agent class in the registry.
  Emits seller.registered ActivityLog.
```

**Approval status state machine:**
```
PENDING → NEEDS_REVIEW → APPROVED | REJECTED | SUSPENDED(future)
```

**Agent class selection** is driven by the seller's `specialization_categories[0]`:
```python
_CATEGORY_TO_AGENT_CLASS = {
    "financial_research":         FinancialResearchSeller,
    "legal_analysis":             LegalAnalysisSeller,
    "market_intelligence":        MarketIntelligenceSeller,
    "strategy_business_research": StrategyResearchSeller,
}
```

**Future upgrade path:** When real external agent APIs exist, set `agent_type="external_api"` and populate `external_agent_api_url`. The `_instantiate_agent()` function checks `agent_type` and will return an `ExternalApiSellerAgent` wrapper (not yet implemented).

---

## 8. Marketplace Matching and Quote Selection

### Matching Engine (`marketplace/matching.py`)

When a task is created, `run_marketplace()` is called immediately. It scores every seller in the store against the task.

**Eligibility gates (hard filters):**
1. `approval_status == APPROVED`
2. Seller covers the task's `category`
3. Seller supports the task's `requested_output_type`
4. Seller is below capacity

**Weighted composite score (0.0–1.0):**

| Dimension | Weight | Formula |
|---|---|---|
| `category_relevance` | **0.30** | 1.0 if primary spec, 0.75 if secondary |
| `benchmark_score` | **0.20** | normalised 0–1; neutral 0.5 if no history |
| `reputation_score` | **0.20** | normalised 0–5 → 0–1; neutral 0.5 if new |
| `price_score` | **0.15** | inverted: `1 - √(price / $200)`; cheaper scores higher |
| `confidence_score` | **0.10** | seller's self-reported 0–1 |
| `capacity_score` | **0.05** | `(capacity - load) / capacity` |

**Weights are module-level constants** in `marketplace/matching.py` — adjust them without touching logic.

### Quote Generation (`marketplace/quoting.py`)

A `Quote` is generated for each shortlisted seller. It includes:
- `proposed_price` (from `SellerProfile.base_price` for FIXED pricing)
- `estimated_minutes` (from `SellerProfile.estimated_minutes`)
- `confidence_score`
- `match_score`, `score_breakdown`, `fit_explanation` — from the matching engine
- `seller_display_name` — denormalised for display

### Seller Selection (`marketplace/workflow.py:select_seller()`)

```
POST /buyer/tasks/{id}/select-seller  { seller_id }
→ validates task is PENDING + seller is shortlisted + quote exists
→ marks quote.accepted = True, rejects others
→ sets task.selected_seller_id + task.selected_quote_id
→ task.status: PENDING → ASSIGNED
```

**Future upgrade path:** Replace flat price calculation with a dynamic pricing model in `quoting.py:_calculate_price()`. Add ETA adjustment based on queue depth in `_calculate_eta()`.

---

## 9. Generalist Benchmark Layer

**Entry point:** `benchmark/runner.py:run_generalist_comparison()` — called automatically after specialist execution.

```
After seller.run(task) populates task.seller_result:

1. GeneralistAgent.run(task)
   → task.generalist_result populated
   → same task brief, no domain tools or specialized prompting

2. benchmark/comparison.py:build_comparison()
   → score_output(seller_result, is_specialist=True)
   → score_output(generalist_result, is_specialist=False)
   → compute delta, determine winner, build recommendation

3. BenchmarkComparison persisted
   → task.benchmark_comparison_id set
   → GeneralistProfile.wins/losses/ties/benchmark_score updated
   → 6 ActivityLog events emitted
```

**Scoring asymmetry (intentional):**

| Signal | Specialist effect | Generalist effect |
|---|---|---|
| Domain-specific fields present | +bonus on quality + specificity | — |
| Generic language markers present | — | -penalty on quality + genericity |
| `agent_type="generalist"` flag | — | -small penalty |
| `risk_flags`, `key_metrics` etc. | +completeness bonus | absent → -completeness |

**Expected output with mock data:** specialist ~80% vs. generalist ~65% (delta +0.15) → `winner=seller`, `recommendation=use_specialist`.

**`recommendation` values:**
- `use_specialist` — clear specialist advantage
- `use_generalist` — generalist competitive; consider cost savings
- `consider_generalist` — marginal quality win but much cheaper
- `tie` — no significant difference

**Future upgrade path:** Replace `GeneralistAgent._generate_mock_content()` with a real LLM call using a vanilla system prompt. Replace `benchmark/comparison.py:score_output()` with an LLM-as-judge that evaluates both outputs against a rubric and returns dimension scores.

---

## 10. Auditor Layer

The auditor runs two independent workflows. All scoring lives in `auditor/scoring.py`.

### Workflow A — Task Output Audit

**Entry point:** `POST /audit/tasks/{id}` → `AuditorAgent.audit_task()`

**Scoring dimensions (weights, 0.0–1.0 each):**

| Dimension | Weight | What it measures |
|---|---|---|
| `quality` | **0.35** | Depth, richness, domain field presence |
| `relevance` | **0.25** | Word overlap with task brief, numeric specifics, category signals |
| `completeness` | **0.25** | Structural elements, output-type checks, sources |
| `genericity` | **0.15** | Inverted: 1.0 = specific, 0.0 = generic |

Pass threshold: composite ≥ 0.70.

### Workflow B — Seller Onboarding Audit

**Entry point:** `POST /audit/sellers/{id}` → `AuditorAgent.audit_seller_onboarding()`

**Scoring dimensions:**

| Dimension | Weight | What it measures |
|---|---|---|
| `completeness` | **0.25** | Required fields, contact info |
| `expertise_credibility` | **0.30** | Claims length, credential keywords, count |
| `pricing_clarity` | **0.20** | Model/price consistency, quote_notes |
| `category_fit` | **0.15** | Valid categories, reasonable count |
| `capacity_realism` | **0.10** | Capacity/ETA within bounds |

Auto-approve threshold: composite ≥ 0.80 AND no hard issues.

### Admin Override

All audit decisions (both workflows) support admin override:

```
POST /admin/audit/{audit_id}/override          { reason, new_passed }
POST /admin/sellers/{id}/approve               — flips to APPROVED
POST /admin/sellers/{id}/reject                { reason, new_passed }
POST /admin/sellers/{id}/review/override       { new_status, reason, comment }
```

Every override stamps `admin_override=True`, `overridden_at`, `overridden_by_user_id`, and increments `AuditorProfile.override_count`.

**Future upgrade path:** Replace `auditor/scoring.py` dimension scorers with LLM-as-judge sub-calls. Function signatures are identical — the return types (`TaskAuditScores`, `OnboardingAuditScores`) stay the same.

---

## 11. UI / Dashboard Views

The frontend is a **monospace dark-theme observability console**, not a consumer product. All pages poll the backend at 5-second intervals.

| Route | Role | What it shows |
|---|---|---|
| `/login` | All | Demo credential hints, JWT login |
| `/buyer` | Buyer | Onboarding pipeline trace, task submission, quote selection, task list |
| `/seller` | Seller | Own profile + onboarding review, assigned tasks, marketplace discovery, execute tool |
| `/audit` | Auditor | Task output audit (dimension bars), seller review queue, benchmark comparison |
| `/admin` | Admin | Activity log, all users, all tasks, seller registry, marketplace analytics, benchmark summary, audit queue |
| `/tasks/[id]` | Buyer/Admin | Full task detail: quotes, specialist output, generalist output, audit result, benchmark, task log |

**Shared component library:** `frontend/src/components/ui.tsx`
- `StatCard`, `ScoreBar`, `Badge`, `TabBar`, `LogFeed`, `TaskRow`, `QuoteCard`, `DimensionScores`, `Empty`, `ErrorBanner`, `Spinner`

**Design system:**
- Background: `#0f0f0f` (page) / `#1a1a1a` (cards) / `#111` (inset)
- Role colors: buyer `#a3e635` · seller `#f9a8d4` · auditor `#fcd34d` · admin `#c084fc` · system `#7dd3fc`
- Semantic: pass `#a3e635` · warn `#fcd34d` · fail `#f87171`

**Auth:** JWT stored in `localStorage`. Every API call attaches `Authorization: Bearer <token>`. Dev bypass: `X-User-Id` header accepted without JWT.

---

## 12. Marketplace Dynamics and Pricing Metrics

**Entry point:** `GET /admin/marketplace?lookback_hours=24` → `analytics/marketplace.py:compute_marketplace_snapshot()`

All calculations are pure functions — no side effects, deterministic.

### Metrics computed

**Participants:**
- Active buyers (buyers with ≥1 task), total buyers
- Active sellers (APPROVED), total sellers, sellers by category, pending reviews

**Tasks:**
- Volume by status, volume by category
- `fill_rate = completed / total`
- `fill_rate_by_category` per category

**Pricing (per category):**
- `avg_price = mean(quote.proposed_price)`
- `price_range = {min, max}` across quotes
- `price_trend` = daily average of accepted quotes, last 7 days (oldest→newest)
- `avg_eta = mean(quote.estimated_minutes)`

**Supply/Demand:**
- `demand = tasks submitted in lookback window, by category`
- `supply = Σ max(0, seller.capacity - in_progress_load)` for APPROVED sellers in category
- `ratio = supply / demand`
- `signal`: `healthy (≥2.0)` | `balanced (1.0–2.0)` | `tight (<1.0)` | `over_subscribed (0)` | `no_demand`

**Seller Utilization:**
- Per-seller: `utilization = in_progress_tasks / capacity`
- `avg_utilization = mean(utilization)` across APPROVED sellers

**Specialist vs. Generalist:**
- `specialist_win_rate = seller_wins / total_comparisons`
- `avg_quality_delta = mean(seller_score - generalist_score)`

---

## 13. Repo Structure

```
AMPS/
├── backend/
│   ├── main.py                    # FastAPI app, startup, routers
│   ├── config.py                  # Settings from env vars
│   ├── store.py                   # In-memory store singleton (replace with DB)
│   ├── seed.py                    # Demo users, profiles, tasks, 1 completed workflow (stable IDs)
│   │
│   ├── models/
│   │   ├── enums.py               # UserRole, TaskCategory, TaskStatus, etc.
│   │   ├── user.py                # User, BuyerProfile, SellerProfile, GeneralistProfile, AuditorProfile
│   │   └── task.py                # Task, Quote, Transaction, AuditResult, BenchmarkComparison,
│   │                              #   ActivityLog, SellerOnboardingReview
│   │
│   ├── agents/
│   │   ├── base.py                # BaseAgent (abstract), AgentResult
│   │   ├── buyer.py               # BuyerAgent — thin adapter over onboarding pipeline
│   │   ├── seller.py              # BaseSellerAgent + 4 specializations (all mock)
│   │   ├── generalist.py          # GeneralistAgent — benchmark baseline (mock)
│   │   ├── auditor.py             # AuditorAgent — orchestrator over auditor/scoring.py
│   │   └── registry.py            # AgentRegistry singleton (in-memory)
│   │
│   ├── onboarding/                # Buyer onboarding pipeline
│   │   ├── instruction_parser.py  # Stage 1: NL instruction → ParsedInstruction
│   │   ├── ingestion.py           # Stage 2: URL → IngestionResult (HTTP + mock providers)
│   │   ├── profile_extractor.py   # Stage 3: text → ExtractedProfile (heuristic)
│   │   └── enrollment.py          # Stage 4: orchestrator → OnboardingResult
│   │
│   ├── seller_onboarding/         # Seller registration pipeline
│   │   ├── validation.py          # 13-rule field validator → ValidationResult
│   │   └── registration.py        # Orchestrator + auto-review → RegistrationResult
│   │
│   ├── marketplace/               # Task routing engine
│   │   ├── matching.py            # 6-dimension weighted scoring + eligibility gates
│   │   ├── quoting.py             # Quote generation from match results
│   │   └── workflow.py            # run_marketplace() + select_seller()
│   │
│   ├── benchmark/                 # Specialist vs. generalist comparison
│   │   ├── comparison.py          # Score both outputs → BenchmarkComparison
│   │   └── runner.py              # run_generalist_comparison() — called post-execution
│   │
│   ├── auditor/
│   │   └── scoring.py             # Shared scorers for task audit + onboarding audit
│   │
│   ├── analytics/
│   │   └── marketplace.py         # compute_marketplace_snapshot() → MarketplaceSnapshot
│   │
│   ├── auth/
│   │   ├── tokens.py              # issue_token() / decode_token() — HS256 JWT
│   │   └── deps.py                # get_current_user, require_role, convenience aliases
│   │
│   └── api/routes/
│       ├── auth.py                # POST /auth/login, GET /auth/me, /auth/whoami
│       ├── buyer.py               # /buyer/onboard, /buyer/tasks (+ marketplace sub-routes)
│       ├── seller.py              # /seller/register, /seller/agents, /seller/tasks
│       ├── audit.py               # /audit/tasks, /audit/sellers
│       └── admin.py               # /admin/* (full access, analytics, overrides)
│
├── frontend/src/
│   ├── app/
│   │   ├── page.tsx               # Landing / role selector
│   │   ├── login/page.tsx         # JWT login with demo credential hints
│   │   ├── buyer/page.tsx         # Buyer console (4 tabs)
│   │   ├── seller/page.tsx        # Seller console (4 tabs)
│   │   ├── audit/page.tsx         # Audit console (3 tabs)
│   │   ├── admin/page.tsx         # Admin console (7 tabs)
│   │   └── tasks/[id]/page.tsx    # Task detail page
│   ├── components/
│   │   ├── NavBar.tsx             # Role-gated nav + sign-out
│   │   └── ui.tsx                 # Shared component library
│   └── lib/api.ts                 # Typed API client + session management
│
├── docs/
│   └── system-contract.md         # Architectural decision log
├── .env.example                   # All environment variables
└── docker-compose.yml             # Backend + frontend containers
```

---

## 14. API Endpoints and Key Functions

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Email + password → JWT token |
| `GET`  | `/auth/me` | Current user identity + profile IDs |
| `GET`  | `/auth/whoami` | Quick identity check |

### Buyer
| Method | Path | Description |
|---|---|---|
| `POST` | `/buyer/onboard` | Run 4-stage onboarding pipeline |
| `POST` | `/buyer/tasks` | Submit task + auto-run marketplace matching |
| `GET`  | `/buyer/tasks` | List buyer's own tasks |
| `GET`  | `/buyer/tasks/{id}` | Single task |
| `GET`  | `/buyer/tasks/{id}/quotes` | Ranked quotes for task |
| `GET`  | `/buyer/tasks/{id}/marketplace` | Full marketplace state |
| `POST` | `/buyer/tasks/{id}/marketplace` | Re-run marketplace matching |
| `POST` | `/buyer/tasks/{id}/select-seller` | Accept a quote, assign seller |

### Seller
| Method | Path | Description |
|---|---|---|
| `POST` | `/seller/register` | Seller registration pipeline |
| `GET`  | `/seller/register/status` | Own registration + review status |
| `GET`  | `/seller/agents` | List all registered agents |
| `GET`  | `/seller/agents/{id}` | Single seller profile |
| `GET`  | `/seller/tasks` | Seller's assigned tasks |
| `POST` | `/seller/tasks/{id}/quote` | Generate quote for a task |
| `POST` | `/seller/tasks/{id}/run` | Execute seller + generalist comparison |

### Audit
| Method | Path | Description |
|---|---|---|
| `POST` | `/audit/tasks/{id}` | Run task output audit |
| `GET`  | `/audit/tasks/{id}` | Retrieve audit result + benchmark |
| `GET`  | `/audit/benchmark/{id}` | Retrieve benchmark comparison |
| `POST` | `/audit/sellers/{id}` | Run seller onboarding audit |
| `GET`  | `/audit/sellers/{id}` | Retrieve seller review |
| `GET`  | `/audit/sellers` | List all reviews (filterable by status) |

### Admin
| Method | Path | Description |
|---|---|---|
| `GET`  | `/admin/users` | All users |
| `GET`  | `/admin/tasks` | All tasks |
| `GET`  | `/admin/logs` | Activity log (filterable) |
| `GET`  | `/admin/sellers` | Seller registry with review summaries |
| `POST` | `/admin/sellers/{id}/approve` | Manually approve seller |
| `POST` | `/admin/sellers/{id}/reject` | Manually reject seller with reason |
| `POST` | `/admin/sellers/{id}/review/override` | Fine-grained review status change |
| `POST` | `/admin/audit/{id}/override` | Override task audit decision |
| `GET`  | `/admin/audit/queue` | Audit workload summary |
| `GET`  | `/admin/audit/pending-tasks` | Completed tasks not yet audited |
| `GET`  | `/admin/benchmark/summary` | Aggregate comparison statistics |
| `GET`  | `/admin/benchmark/{task_id}` | Full comparison for a task |
| `GET`  | `/admin/generalist` | Generalist profile + W/L/T record |
| `GET`  | `/admin/marketplace` | Full marketplace analytics snapshot |

### Meta (public)
| Method | Path | Description |
|---|---|---|
| `GET` | `/` | App metadata |
| `GET` | `/health` | Health check |
| `GET` | `/agents/summary` | All registered agents |

### Key backend functions

| Function | File | Purpose |
|---|---|---|
| `run_onboarding()` | `onboarding/enrollment.py` | Buyer onboarding orchestrator |
| `run_seller_registration()` | `seller_onboarding/registration.py` | Seller registration orchestrator |
| `run_marketplace()` | `marketplace/workflow.py` | Match + quote generation |
| `select_seller()` | `marketplace/workflow.py` | Accept quote, assign seller |
| `run_generalist_comparison()` | `benchmark/runner.py` | Parallel generalist execution + scoring |
| `build_comparison()` | `benchmark/comparison.py` | Score both outputs, build `BenchmarkComparison` |
| `score_task_output()` | `auditor/scoring.py` | 4-dimension task output scoring |
| `score_seller_onboarding()` | `auditor/scoring.py` | 5-dimension onboarding scoring |
| `compute_marketplace_snapshot()` | `analytics/marketplace.py` | Full analytics computation |

---

## 15. Data Model Summary

### Core objects

| Model | File | Key fields |
|---|---|---|
| `User` | `models/user.py` | `id`, `email`, `role`, `is_active` |
| `BuyerProfile` | `models/user.py` | `user_id`, `organization`, `preferred_categories`, `onboarding_confidence` |
| `SellerProfile` | `models/user.py` | `user_id`, `specialization_categories`, `expertise_claims`, `pricing_model`, `base_price`, `approval_status`, `confidence_score`, `reputation_score` |
| `GeneralistProfile` | `models/user.py` | `model_identifier`, `cost_per_task`, `wins`, `losses`, `ties`, `benchmark_score` |
| `AuditorProfile` | `models/user.py` | `audits_completed`, `override_count`, `avg_task_quality_score`, `scoring_method` |
| `Task` | `models/task.py` | `buyer_id`, `category`, `status`, `shortlisted_seller_ids`, `selected_seller_id`, `seller_result`, `generalist_result`, `audit_status`, `benchmark_comparison_id` |
| `Quote` | `models/task.py` | `task_id`, `seller_id`, `proposed_price`, `match_score`, `score_breakdown`, `fit_explanation`, `accepted` |
| `AuditResult` | `models/task.py` | `composite_score`, `dimension_scores`, `passed`, `flags`, `recommendations`, `has_benchmark`, `admin_override` |
| `BenchmarkComparison` | `models/task.py` | `seller_score`, `generalist_score`, `seller_dimension_scores`, `generalist_dimension_scores`, `specialist_cost`, `winner`, `delta`, `recommendation` |
| `SellerOnboardingReview` | `models/task.py` | `review_status`, `overall_score`, `dimension_scores`, `issues`, `recommendations`, `admin_override` |
| `ActivityLog` | `models/task.py` | `event_type`, `actor_id`, `actor_role`, `entity_type`, `entity_id`, `message`, `metadata` |

### Enumerations (`models/enums.py`)

| Enum | Values |
|---|---|
| `UserRole` | `buyer`, `seller`, `generalist`, `auditor`, `admin` |
| `TaskCategory` | `financial_research`, `legal_analysis`, `market_intelligence`, `strategy_business_research` |
| `TaskStatus` | `pending`, `assigned`, `in_progress`, `completed`, `failed`, `disputed` |
| `AuditStatus` | `not_started`, `in_review`, `passed`, `failed`, `overridden` |
| `ApprovalStatus` | `pending`, `needs_review`, `approved`, `rejected`, `suspended` |
| `PricingModel` | `fixed`, `quoted`, `free` |
| `OutputType` | `report`, `summary`, `structured_json`, `bullet_list` |

---

## 16. Current Limitations and Mocked Components

This table is the authoritative reference for what is MVP-only. Before extending any subsystem, check here first.

| Component | What is mocked / limited | Location |
|---|---|---|
| **Seller execution** | All 4 `_generate_mock_content()` methods return hardcoded dicts with `"mock": True` | `agents/seller.py` |
| **Generalist execution** | `_generate_mock_content()` returns deterministic generic output | `agents/generalist.py` |
| **Buyer profile extraction** | Heuristic regex — no LLM, no real NLP | `onboarding/profile_extractor.py` |
| **URL ingestion** | `HttpIngestionProvider` does real HTTP + regex HTML stripping; no JS rendering | `onboarding/ingestion.py` |
| **Benchmark scoring** | Heuristic key-counting, not LLM-as-judge | `benchmark/comparison.py` |
| **Task audit scoring** | Heuristic dimension scorers, not LLM-as-judge | `auditor/scoring.py` |
| **Onboarding audit scoring** | Same heuristic scorers | `auditor/scoring.py` |
| **Benchmark scores on SellerProfile** | `benchmark_score=None` for new sellers → neutral prior 0.5 in matching | `marketplace/matching.py` |
| **Reputation scores** | `reputation_score=0.0` for new sellers → neutral prior 0.5 in matching | `marketplace/matching.py` |
| **Price trend** | Only reflects accepted quotes — sparse in early use | `analytics/marketplace.py` |
| **Database** | Python dicts in `InMemoryStore` — **no persistence between restarts** | `store.py` |
| **Agent registry** | Python dict — **no persistence between restarts** | `agents/registry.py` |
| **Password storage** | Plain text on `User.password` — MVP only | `models/user.py` |
| **Auth provider** | Self-signed JWT with `SECRET_KEY` — no OAuth, no MFA | `auth/tokens.py` |
| **Payment / escrow** | `Transaction` model exists but no payment processing | `models/task.py` |
| **ETA calculation** | Flat `estimated_minutes` from SellerProfile — no queue depth adjustment | `marketplace/quoting.py` |
| **Seller capacity** | Only counts `IN_PROGRESS` tasks — no reservation system | `marketplace/matching.py` |
| **Price calculation** | Uses `base_price` directly — no dynamic pricing | `marketplace/quoting.py` |
| **X-User-Id dev bypass** | Active in all environments — must be disabled before production | `auth/deps.py` |
| **CORS** | `allow_origins=*` effectively — locked to `localhost:3000` by default | `config.py` |

---

## 17. Scalability and Rewrite Notes

### When to replace the in-memory store

The `InMemoryStore` is the single biggest architectural debt. Everything else is well-separated and easy to swap, but the store needs replacement before:
- Multiple server processes (load balancing)
- Data persistence across restarts
- Any production deployment

**Replacement path:**
1. Add SQLAlchemy models mirroring the existing Pydantic models (same field names)
2. Replace `store = InMemoryStore()` with a `SessionLocal = sessionmaker(...)` factory
3. Inject the session via `Depends(get_db)` in each route
4. Run Alembic migrations from `models/`

The Pydantic models in `models/user.py` and `models/task.py` can serve as the schema definition directly.

### When to add real LLM execution

The agent interfaces are designed for this. The minimum change for each agent type:

**Seller agents:**
```python
# In agents/seller.py, replace:
def _generate_mock_content(self, task: Task) -> Dict:
    ...  # current hardcoded dict
# With:
def _generate_mock_content(self, task: Task) -> Dict:
    return self.llm_client.call(
        system_prompt=DOMAIN_SYSTEM_PROMPTS[self.category],
        user_prompt=task.description,
        context_url=task.context_url,
    )
```

**Generalist:**
```python
# In agents/generalist.py:
def _generate_mock_content(self, task: Task) -> Dict:
    return self.llm_client.call(
        system_prompt="You are a helpful assistant.",  # No domain context
        user_prompt=task.description,
    )
```

**Auditor (LLM-as-judge):**
```python
# In auditor/scoring.py, replace individual dimension scorers with:
def score_task_output(result, task, ...):
    return llm_judge.evaluate(
        task_brief=task.description,
        output=result,
        rubric=AUDIT_RUBRIC,
    )
```

### When to add async

All agent `run()` methods are currently synchronous. The FastAPI routes that call them will block during execution. For production:
1. Change `run(task)` → `async run(task)` in `BaseAgent`
2. Use `asyncio.gather()` in `benchmark/runner.py` to run specialist and generalist truly in parallel
3. Consider a task queue (Celery, ARQ, or Redis Streams) for long-running executions

### Auth provider replacement

`auth/tokens.py` is the only file that needs changing to swap to Clerk, Auth0, or Cognito. The `auth/deps.py` dependency functions (`get_current_user`, `require_role`) are provider-agnostic — they resolve a `User` object, nothing more.

---

## 18. Suggested Next Enhancements

Ordered by estimated impact / effort:

### High impact, moderate effort
1. **Database layer** — Replace `InMemoryStore` with PostgreSQL + SQLAlchemy + Alembic. All field names are already defined; it's a structural migration, not a logic rewrite.
2. **Real LLM seller execution** — Wire one real seller agent (e.g. `FinancialResearchSeller`) to a real LLM. The interface requires only replacing `_generate_mock_content()`. Use this to validate the benchmark comparison produces real signal.
3. **LLM-as-judge auditor** — Replace `auditor/scoring.py` dimension scorers with a structured LLM evaluation call. This is the highest-value quality improvement: heuristic scores are proxies; LLM-judge scores are real.

### High impact, lower effort
4. **bcrypt password hashing** — Replace plain-text `User.password` with `bcrypt`. Only `api/routes/auth.py:login()` changes.
5. **Disable X-User-Id dev bypass** — Gate behind `settings.dev_mode` in `auth/deps.py`.
6. **Benchmark score propagation** — After each comparison, update `SellerProfile.benchmark_score` (rolling mean) and `reputation_score`. Currently `benchmark_score=None` for all seeded sellers, which forces the neutral prior in matching.
7. **Seller capacity reservation** — Add a booking system so capacity is reserved at ASSIGNED status, not just counted at IN_PROGRESS.

### Medium impact, moderate effort
8. **Async execution + task queue** — Move seller execution to a background job (ARQ or Celery). Return task ID immediately, poll for results. Required for any LLM with >2s latency.
9. **Dynamic ETA model** — Replace flat `estimated_minutes` with a model that adjusts based on current queue depth and task complexity signals (description length, output type).
10. **Price trend data** — The `price_trend_by_category` chart is currently sparse. Add more demo accepted quotes in `seed.py` to show what the chart looks like when populated.
11. **Seller re-registration** — Currently blocked ("re-registration not yet supported"). Add a profile update flow.
12. **Multi-category sellers** — The matching engine supports it; the agent class selection only uses `categories[0]`. Add a proper multi-category execution router.

### Lower priority
13. **WebSocket / SSE activity feed** — Replace 5s polling with server-sent events for the admin log console.
14. **Seller reputation scoring** — Automatically update `SellerProfile.reputation_score` from completed `AuditResult` records after each task.
15. **Buyer feedback loop** — Add a buyer-facing rating after task completion. Feed into audit scoring.
16. **Auction / bidding mechanics** — Replace direct quote acceptance with a bidding window where multiple sellers can compete.
17. **Task categories expansion** — Adding a new category requires: one new `TaskCategory` enum value, one new `BaseSellerAgent` subclass, one entry in `_CATEGORY_TO_AGENT_CLASS`. The rest of the system adapts automatically.
18. **OAuth / SSO** — Replace self-signed JWT with Clerk or Auth0. Only `auth/tokens.py` and `auth/deps.py` need updating.

---

## 19. Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+

### Local development (no Docker)

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# API explorer: http://localhost:8000/docs

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev
# Console: http://localhost:3000
```

### Docker

```bash
cp .env.example .env
docker-compose up
```

### Demo accounts (seeded at startup)

| Email | Password | Role | Notes |
|---|---|---|---|
| `buyer@amps.dev` | `buyer123` | buyer | 4 tasks (3 PENDING with quotes, 1 COMPLETED with audit + benchmark) |
| `seller1@amps.dev` | `seller123` | seller | Financial Research Pro — approved, $75/task |
| `seller2@amps.dev` | `seller123` | seller | Legal Analysis Pro — approved, $95/task |
| `seller3@amps.dev` | `seller123` | seller | MarketIntel Pro — needs_review (demo of review flow) |
| `seller4@amps.dev` | `seller123` | seller | Strategy Pro — approved, $85/task |
| `generalist@amps.dev` | `gen123` | generalist | Baseline agent |
| `auditor@amps.dev` | `audit123` | auditor | |
| `admin@amps.dev` | `admin123` | admin | Full access |

### Demo task flow (via API docs at `/docs`)

**On startup, the system is already pre-loaded with:**
- 4 seller agents (3 approved, 1 pending review)
- 1 buyer with 3 PENDING tasks (each with quotes already generated)
- 1 COMPLETED task with seller result, generalist result, benchmark, and audit result
- Activity log with realistic events

**To run a full workflow from scratch:**
```
1.  POST /auth/login                    { email, password }
2.  POST /buyer/onboard                 { instruction, url }
3.  POST /buyer/tasks                   { buyer_id, title, description, category }
    → marketplace matching auto-runs, quotes returned
4.  GET  /buyer/tasks/{id}/quotes       → ranked quotes with match scores
5.  POST /buyer/tasks/{id}/select-seller { seller_id }
6.  POST /seller/tasks/{id}/run?seller_id=...
    → specialist executes, generalist baseline runs, BenchmarkComparison created
7.  POST /audit/tasks/{id}
    → AuditResult with dimension scores
8.  GET  /admin/marketplace             → supply/demand analytics
9.  GET  /admin/benchmark/summary       → specialist win rate
```

### Environment variables

See `.env.example` for all variables. Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev-secret-...` | JWT signing key — **change in production** |
| `INGESTION_PROVIDER` | `http` | `http` for real URL fetching, `mock` for always-mock |
| `INGESTION_FALLBACK_TO_MOCK` | `true` | Fall back to mock content if HTTP fetch fails |
| `AUDIT_QUALITY_THRESHOLD` | `0.70` | Task audit pass/fail threshold |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed frontend origins |

---

---

## 20. Vercel Deployment

### Architecture assessment

This is a **monorepo with two separate apps** that must be deployed independently:

| Part | Framework | Vercel-compatible? |
|---|---|---|
| `frontend/` | Next.js 14 (App Router) | **Yes — fully supported** |
| `backend/` | Python / FastAPI | **No — deploy separately** |

**Vercel only hosts the frontend.** The Python backend must be deployed on a platform that runs Python processes (Railway, Render, Fly.io, etc.). The frontend communicates with the backend via `NEXT_PUBLIC_API_URL`.

---

### Frontend: confirmed deployable

The frontend passes all pre-deployment checks:

- **Build:** `npm run build` exits cleanly (9 routes, 0 errors, 0 TS errors)
- **Root route `/`:** renders the landing page — does **not** 404
- **All routes present:** `/`, `/login`, `/buyer`, `/seller`, `/admin`, `/audit`, `/tasks/[id]`
- **All routes static or SSR:** no broken dynamic imports, no missing env vars blocking build
- **`vercel.json`:** valid schema, security headers only — no invalid fields
- **`package.json`:** `build` script is `next build`, correct and standard
- **`tsconfig.json`:** standard Next.js App Router config
- **`next-env.d.ts`:** present and committed

---

### Step-by-step Vercel deployment

#### Step 1 — Commit everything

These files **must be committed** before deploying (Vercel clones from git):

```bash
cd frontend
git add next-env.d.ts package-lock.json
cd ..
git add frontend/src/app/buyer/page.tsx frontend/next.config.js .gitignore
git commit -m "fix: TS error in buyer page, clean next.config, update gitignore"
git push
```

#### Step 2 — Create the Vercel project

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import your GitHub repository
3. In the **Configure Project** screen, set:

| Setting | Value |
|---|---|
| **Root Directory** | `frontend` |
| **Framework Preset** | Next.js (auto-detected) |
| **Build Command** | *(leave empty — uses `npm run build` from package.json)* |
| **Output Directory** | *(leave empty — Next.js default `.next`)* |
| **Install Command** | *(leave empty — uses `npm install`)* |

> **Root Directory is the critical setting.** Without it, Vercel looks for `package.json` at the repo root, finds none, and the build fails. Set it to `frontend` in the Vercel UI — this cannot be put in `vercel.json`.

#### Step 3 — Set environment variables

In Vercel → Project → Settings → Environment Variables, add:

| Name | Value | Environment |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://your-backend.example.com` | Production, Preview, Development |

> If the backend is not yet deployed, you can temporarily set this to any valid URL — the frontend will build and serve pages, but API calls will fail gracefully with error banners. Set the real URL once the backend is live.

#### Step 4 — Add custom domain

In Vercel → Project → Settings → Domains:
1. Add `ampsmarketplace.com`
2. Add `www.ampsmarketplace.com`
3. Vercel will show the DNS records to set at your registrar:

| Type | Name | Value |
|---|---|---|
| `A` | `@` | `76.76.21.21` |
| `CNAME` | `www` | `cname.vercel-dns.com` |

#### Step 5 — Deploy

Click **Deploy**. Vercel runs:
```
npm install   (inside frontend/)
npm run build (inside frontend/)
```

Expected output:
```
Route (app)          Size
○ /                  137 B
○ /login             ...
○ /buyer             ...
○ /seller            ...
○ /admin             ...
○ /audit             ...
ƒ /tasks/[id]        ...
```

---

### Backend deployment (not on Vercel)

The FastAPI backend **cannot run on Vercel** because:
- Vercel only runs Node.js and Edge runtimes (not Python)
- The backend uses long-lived in-memory state (`InMemoryStore`) incompatible with stateless serverless functions
- The backend requires persistent process startup (seeding, registry init)

**Recommended platforms for the backend:**

| Platform | Steps |
|---|---|
| **Railway** | New project → Deploy from GitHub → set root to `backend/` → start command: `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Render** | New Web Service → root `backend/` → build: `pip install -r requirements.txt` → start: `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Fly.io** | `fly launch` inside `backend/` — uses the existing `Dockerfile` |

After deploying the backend, update `NEXT_PUBLIC_API_URL` in Vercel and redeploy the frontend.

**Backend CORS:** before deploying, update `.env` / backend config so `CORS_ORIGINS` includes your Vercel domain:
```
CORS_ORIGINS=https://ampsmarketplace.com,https://www.ampsmarketplace.com
```

---

### Exact Vercel settings reference

```
Root Directory:   frontend
Build Command:    npm run build       (auto from package.json)
Install Command:  npm install         (auto)
Output Directory: .next               (auto, Next.js default)
Node.js Version:  20.x               (set in Vercel project settings)
```

Required environment variable:
```
NEXT_PUBLIC_API_URL = https://your-backend-host.example.com
```

---

### Local pre-deployment validation

Run these commands before every deployment to catch errors early:

```bash
cd frontend

# 1. Install deps
npm install

# 2. Type-check (must exit with no output = 0 errors)
npx tsc --noEmit

# 3. Production build (must complete without errors)
npm run build

# 4. Verify all 9 routes appear in build output
#    Expected: ○ /  ○ /login  ○ /buyer  ○ /seller  ○ /admin  ○ /audit  ƒ /tasks/[id]
```

---

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **404 on all routes after deploy** | Root Directory not set to `frontend` | In Vercel UI: Project → Settings → General → Root Directory → `frontend` |
| **Build fails: "next: not found"** | Same as above — Vercel looking at repo root | Set Root Directory to `frontend` |
| **Build fails: Type error** | TypeScript regression | Run `npx tsc --noEmit` locally and fix errors before pushing |
| **Pages load but API calls fail** | `NEXT_PUBLIC_API_URL` not set or wrong | Vercel → Environment Variables → set correct backend URL → redeploy |
| **API calls fail with CORS error** | Backend CORS config doesn't include Vercel domain | Add `https://ampsmarketplace.com` to `CORS_ORIGINS` in backend config |
| **`www.ampsmarketplace.com` doesn't work** | Missing CNAME record | Add `CNAME www → cname.vercel-dns.com` at your registrar |
| **Deployment uses wrong Node version** | Default Vercel Node < 20 | Vercel → Settings → General → Node.js Version → 20.x |

---

*Last updated: 2026-03-31 · See `docs/system-contract.md` for detailed architectural decision log.*
