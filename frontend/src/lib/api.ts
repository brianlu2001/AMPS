/**
 * AMPS API client — typed wrapper over all backend endpoints.
 *
 * Auth: JWT stored in localStorage. Every request auto-attaches Bearer token.
 * Polling: frontend polls at 5s intervals (no WebSockets needed for MVP).
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Session management
// ---------------------------------------------------------------------------

const TOKEN_KEY = "amps_token";
const USER_KEY  = "amps_user";

export interface SessionUser {
  user_id: string;
  email: string;
  role: "buyer" | "seller" | "generalist" | "auditor" | "admin";
  display_name: string;
  buyer_profile_id?: string;
  seller_profile_id?: string;
}

export const session = {
  getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(TOKEN_KEY);
  },
  getUser(): SessionUser | null {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  },
  set(token: string, user: SessionUser): void {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  isLoggedIn(): boolean { return !!this.getToken(); },
};

// ---------------------------------------------------------------------------
// Core fetch helper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = session.getToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API ${res.status}: ${error}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export type TaskCategory =
  | "financial_research" | "legal_analysis"
  | "market_intelligence" | "strategy_business_research";

export type TaskStatus =
  | "pending" | "assigned" | "in_progress" | "completed" | "failed" | "disputed";

export type AuditStatus =
  | "not_started" | "in_review" | "passed" | "failed" | "overridden";

export interface Task {
  id: string;
  buyer_id: string;
  title: string;
  description: string;
  category: TaskCategory;
  requested_output_type: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  shortlisted_seller_ids: string[];
  selected_seller_id: string | null;
  selected_quote_id: string | null;
  quote_ids: string[];
  marketplace_run_at: string | null;
  context_url: string | null;
  seller_result: Record<string, unknown> | null;
  generalist_result: Record<string, unknown> | null;
  generalist_comparison_enabled: boolean;
  benchmark_comparison_id: string | null;
  audit_status: AuditStatus;
  audit_result_id: string | null;
}

export interface Quote {
  id: string;
  task_id: string;
  seller_id: string;
  proposed_price: number;
  estimated_minutes: number;
  confidence_score: number;
  notes: string | null;
  match_score: number;
  fit_explanation: string | null;
  score_breakdown: Record<string, number>;
  seller_display_name: string | null;
  accepted: boolean;
  created_at: string;
}

export interface AuditResult {
  id: string;
  task_id: string;
  auditor_id: string;
  composite_score: number;
  quality_score: number;
  passed: boolean;
  dimension_scores: Record<string, number>;
  reasoning: string;
  flags: string[];
  recommendations: string[];
  has_benchmark: boolean;
  benchmark_comparison_id: string | null;
  benchmark_winner: string | null;
  benchmark_delta: number | null;
  admin_override: boolean;
  admin_override_reason: string | null;
  overridden_at: string | null;
  scoring_method: string;
  audited_at: string;
}

export interface BenchmarkComparison {
  id: string;
  task_id: string;
  task_category: string | null;
  seller_id: string;
  seller_display_name: string | null;
  generalist_id: string;
  generalist_model: string | null;
  seller_score: number;
  generalist_score: number;
  seller_dimension_scores: Record<string, number>;
  generalist_dimension_scores: Record<string, number>;
  specialist_cost: number;
  generalist_cost: number;
  specialist_eta_minutes: number;
  generalist_eta_minutes: number;
  winner: string;
  delta: number;
  recommendation: string;
  summary: string | null;
  scoring_method: string;
  mock: boolean;
  created_at: string;
}

export interface ActivityLog {
  id: string;
  event_type: string;
  actor_id: string | null;
  actor_role: string | null;
  entity_type: string;
  entity_id: string;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface BuyerProfile {
  id: string;
  user_id: string;
  organization: string | null;
  display_name_hint: string | null;
  industry_hint: string | null;
  preferred_categories: string[];
  use_case_summary: string | null;
  onboarding_confidence: number;
  task_history_count: number;
  created_at: string;
}

export interface SellerOnboardingReview {
  id: string;
  seller_profile_id: string;
  review_status: string;
  overall_score: number | null;
  dimension_scores: Record<string, number>;
  passed: boolean | null;
  issues: string[];
  recommendations: string[];
  reasoning: string | null;
  auditor_comment: string | null;
  admin_override: boolean;
  created_at: string;
  reviewed_at: string | null;
}

// ---------------------------------------------------------------------------
// Marketplace analytics types (mirrors MarketplaceSnapshot.to_dict())
// ---------------------------------------------------------------------------

export interface SupplyDemandCategory {
  demand: number;
  supply: number;
  ratio: number | null;
  signal: "healthy" | "balanced" | "tight" | "over_subscribed" | "no_demand";
}

export interface SellerUtilizationEntry {
  seller_id: string;
  name: string;
  categories: string[];
  active_tasks: number;
  capacity: number;
  utilization: number;
  status: "busy" | "available";
}

export interface MarketplaceAnalytics {
  snapshot_at: string;
  participants: {
    active_buyers: number;
    total_buyers: number;
    active_sellers: number;
    total_sellers: number;
    sellers_by_category: Record<string, number>;
    sellers_pending_review: number;
  };
  tasks: {
    total: number;
    by_status: Record<string, number>;
    by_category: Record<string, number>;
    fill_rate: number | null;
    fill_rate_by_category: Record<string, number | null>;
  };
  pricing: {
    total_quotes: number;
    quote_volume_by_category: Record<string, number>;
    avg_price_overall: number | null;
    avg_price_by_category: Record<string, number | null>;
    price_range_by_category: Record<string, { min: number | null; max: number | null }>;
    price_trend_by_category: Record<string, number[]>;
    avg_eta_by_category: Record<string, number | null>;
  };
  supply_demand: {
    lookback_hours: number;
    demand_by_category: Record<string, number>;
    supply_by_category: Record<string, number>;
    ratio_by_category: Record<string, number | null>;
    signal_by_category: Record<string, string>;
  };
  seller_utilization: {
    sellers: SellerUtilizationEntry[];
    avg_utilization: number | null;
  };
  specialist_vs_generalist: {
    total_comparisons: number;
    specialist_win_rate: number | null;
    avg_quality_delta: number | null;
  };
}

export interface MarketplaceState {
  task_id: string;
  task_status: string;
  marketplace_run_at: string | null;
  shortlisted_seller_ids: string[];
  selected_seller_id: string | null;
  selected_quote_id: string | null;
  quotes: Quote[];
  quote_count: number;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  role: string;
  display_name: string;
}

export const authApi = {
  login: async (email: string, password: string): Promise<TokenResponse> => {
    const tokenRes = await apiFetch<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    session.set(tokenRes.access_token, {
      user_id: tokenRes.user_id,
      role: tokenRes.role as SessionUser["role"],
      email,
      display_name: tokenRes.display_name,
    });
    try {
      const me = await authApi.me();
      session.set(tokenRes.access_token, me as SessionUser);
    } catch { /* keep basic session */ }
    return tokenRes;
  },
  me:     () => apiFetch<SessionUser>("/auth/me"),
  whoami: () => apiFetch<Pick<SessionUser, "user_id" | "email" | "role" | "display_name">>("/auth/whoami"),
  logout: () => session.logout(),
};

// ---------------------------------------------------------------------------
// Buyer
// ---------------------------------------------------------------------------

export const buyerApi = {
  onboard: (instruction: string, url: string | null) =>
    apiFetch<Record<string, unknown>>("/buyer/onboard", {
      method: "POST",
      body: JSON.stringify({ instruction, url }),
    }),

  createTask: (payload: {
    buyer_id: string; title: string; description: string;
    category: TaskCategory; requested_output_type?: string;
    context_url?: string; enable_generalist_comparison?: boolean;
  }) =>
    apiFetch<{ task: Task; marketplace: Record<string, unknown> }>("/buyer/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getTask:   (taskId: string) => apiFetch<Task>(`/buyer/tasks/${taskId}`),
  listTasks: (_buyerId?: string) => apiFetch<Task[]>(`/buyer/tasks`),

  getQuotes:      (taskId: string) => apiFetch<Quote[]>(`/buyer/tasks/${taskId}/quotes`),
  getMarketplace: (taskId: string) => apiFetch<MarketplaceState>(`/buyer/tasks/${taskId}/marketplace`),

  selectSeller: (taskId: string, sellerId: string) =>
    apiFetch<{ success: boolean; message: string; task: Task; accepted_quote: Quote }>
      (`/buyer/tasks/${taskId}/select-seller`, {
        method: "POST",
        body: JSON.stringify({ seller_id: sellerId }),
      }),

  refreshMarketplace: (taskId: string) =>
    apiFetch<Record<string, unknown>>(`/buyer/tasks/${taskId}/marketplace`, { method: "POST" }),
};

// ---------------------------------------------------------------------------
// Seller
// ---------------------------------------------------------------------------

export const sellerApi = {
  register: (payload: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>("/seller/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getRegistrationStatus: () =>
    apiFetch<Record<string, unknown>>("/seller/register/status"),

  listAgents: () => apiFetch<Record<string, unknown>[]>("/seller/agents"),
  getAgent:   (id: string) => apiFetch<Record<string, unknown>>(`/seller/agents/${id}`),

  listMyTasks: () => apiFetch<Record<string, unknown>[]>("/seller/tasks"),

  generateQuote: (taskId: string, sellerId: string) =>
    apiFetch<Quote>(`/seller/tasks/${taskId}/quote?seller_id=${sellerId}`, { method: "POST" }),

  runOnTask: (taskId: string, sellerId: string) =>
    apiFetch<Task>(`/seller/tasks/${taskId}/run?seller_id=${sellerId}`, { method: "POST" }),
};

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export const auditApi = {
  runTaskAudit: (taskId: string) =>
    apiFetch<{ audit_result: AuditResult; benchmark_comparison: BenchmarkComparison | null; task_status: string; audit_status: string }>
      (`/audit/tasks/${taskId}`, { method: "POST" }),

  getTaskAudit: (taskId: string) =>
    apiFetch<{ audit_result: AuditResult; benchmark_comparison: BenchmarkComparison | null; task_status: string; audit_status: string }>
      (`/audit/tasks/${taskId}`),

  getBenchmark: (taskId: string) =>
    apiFetch<BenchmarkComparison>(`/audit/benchmark/${taskId}`),

  runSellerAudit: (sellerId: string) =>
    apiFetch<{ review: SellerOnboardingReview; seller_id: string; seller_name: string; approval_status: string }>
      (`/audit/sellers/${sellerId}`, { method: "POST" }),

  getSellerReview: (sellerId: string) =>
    apiFetch<{ review: SellerOnboardingReview; seller_name: string; approval_status: string }>
      (`/audit/sellers/${sellerId}`),

  listSellerReviews: (status?: string) => {
    const qs = status ? `?review_status=${status}` : "";
    return apiFetch<Array<{ review: SellerOnboardingReview; seller_name: string; approval_status: string }>>
      (`/audit/sellers${qs}`);
  },
};

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export const adminApi = {
  // Users
  listUsers: () => apiFetch<Record<string, unknown>[]>("/admin/users"),

  // Tasks
  listAllTasks: () => apiFetch<Record<string, unknown>[]>("/admin/tasks"),

  // Logs
  getLogs: (limit = 100, entityId?: string) => {
    const p = new URLSearchParams({ limit: String(limit) });
    if (entityId) p.set("entity_id", entityId);
    return apiFetch<ActivityLog[]>(`/admin/logs?${p}`);
  },

  // Audit queue
  getAuditQueue:    () => apiFetch<Record<string, unknown>>("/admin/audit/queue"),
  getPendingAudits: () => apiFetch<Record<string, unknown>[]>("/admin/audit/pending-tasks"),

  // Task audit override
  overrideAudit: (auditId: string, reason: string, newPassed: boolean) =>
    apiFetch<Record<string, unknown>>(`/admin/audit/${auditId}/override`, {
      method: "POST",
      body: JSON.stringify({ reason, new_passed: newPassed }),
    }),

  // Sellers
  listSellers:   () => apiFetch<Record<string, unknown>[]>("/admin/sellers"),
  approveSeller: (id: string) =>
    apiFetch<Record<string, unknown>>(`/admin/sellers/${id}/approve`, { method: "POST" }),
  rejectSeller: (id: string, reason: string) =>
    apiFetch<Record<string, unknown>>(`/admin/sellers/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason, new_passed: false }),
    }),
  overrideSellerReview: (id: string, newStatus: string, reason: string, comment?: string) =>
    apiFetch<Record<string, unknown>>(`/admin/sellers/${id}/review/override`, {
      method: "POST",
      body: JSON.stringify({ new_status: newStatus, reason, comment }),
    }),

  // Benchmark
  getBenchmarkSummary:  () => apiFetch<Record<string, unknown>>("/admin/benchmark/summary"),
  getTaskBenchmark:     (taskId: string) => apiFetch<Record<string, unknown>>(`/admin/benchmark/${taskId}`),
  getGeneralistProfile: () => apiFetch<Record<string, unknown>>("/admin/generalist"),

  // Marketplace analytics
  getMarketplaceAnalytics: (lookbackHours = 24) =>
    apiFetch<MarketplaceAnalytics>(`/admin/marketplace?lookback_hours=${lookbackHours}`),
};

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

export const metaApi = {
  getAgentsSummary: () => apiFetch<Record<string, unknown>>("/agents/summary"),
  health:           () => apiFetch<{ status: string }>("/health"),
};
