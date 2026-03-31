"use client";
/**
 * Admin Dashboard
 *
 * Tabs:
 *   Activity   — live log feed (polled 5s) — primary observability view
 *   Users      — all users with roles
 *   Tasks      — all tasks, filterable by status
 *   Sellers    — seller registry, approval controls, onboarding review scores
 *   Benchmark  — specialist vs. generalist summary + generalist profile
 *   Audit      — audit queue stats + pending tasks
 */

import { useEffect, useState } from "react";
import { adminApi, ActivityLog, MarketplaceAnalytics } from "../../lib/api";
import {
  C, SectionHeader, StatCard, TaskRow, LogFeed, Badge, ScoreBar,
  TabBar, ErrorBanner, Empty, Spinner, btnStyle, cardStyle, inputStyle,
  scoreColor, ROLE_COLORS, STATUS_COLORS, APPROVAL_COLORS,
} from "../../components/ui";

export default function AdminPage() {
  const [tab, setTab] = useState("activity");

  const [logs, setLogs]     = useState<ActivityLog[]>([]);
  const [users, setUsers]   = useState<Record<string, unknown>[]>([]);
  const [tasks, setTasks]   = useState<Record<string, unknown>[]>([]);
  const [sellers, setSellers] = useState<Record<string, unknown>[]>([]);
  const [benchSummary, setBenchSummary]   = useState<Record<string, unknown> | null>(null);
  const [generalist, setGeneralist]       = useState<Record<string, unknown> | null>(null);
  const [auditQueue, setAuditQueue]       = useState<Record<string, unknown> | null>(null);
  const [pendingAudits, setPendingAudits] = useState<Record<string, unknown>[]>([]);
  const [marketplace, setMarketplace]     = useState<MarketplaceAnalytics | null>(null);
  const [rejectReason, setRejectReason]   = useState<Record<string, string>>({});

  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  // Poll logs every 5s always
  useEffect(() => {
    const fetch = async () => {
      try { setLogs((await adminApi.getLogs(60)).reverse()); setError(null); }
      catch (e) { setError(String(e)); }
    };
    fetch();
    const iv = setInterval(fetch, 5000);
    return () => clearInterval(iv);
  }, []);

  // Load tab-specific data
  useEffect(() => {
    if (tab === "users")     adminApi.listUsers().then(setUsers).catch(console.error);
    if (tab === "tasks")     adminApi.listAllTasks().then(setTasks).catch(console.error);
    if (tab === "sellers")   adminApi.listSellers().then(setSellers).catch(console.error);
    if (tab === "benchmark") {
      adminApi.getBenchmarkSummary().then(setBenchSummary).catch(console.error);
      adminApi.getGeneralistProfile().then(setGeneralist).catch(console.error);
    }
    if (tab === "audit") {
      adminApi.getAuditQueue().then(setAuditQueue).catch(console.error);
      adminApi.getPendingAudits().then(setPendingAudits).catch(console.error);
    }
    if (tab === "marketplace") {
      adminApi.getMarketplaceAnalytics(24).then(setMarketplace).catch(console.error);
    }
  }, [tab]);

  const handleApprove = async (id: string) => {
    setLoading(true);
    try { await adminApi.approveSeller(id); setSellers(await adminApi.listSellers()); }
    catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  const handleReject = async (id: string) => {
    setLoading(true);
    try { await adminApi.rejectSeller(id, rejectReason[id] || "Rejected by admin"); setSellers(await adminApi.listSellers()); }
    catch (e) { setError(String(e)); } finally { setLoading(false); }
  };

  return (
    <div style={{ maxWidth: "980px" }}>
      <h2 style={{ color: C.admin, marginBottom: "8px" }}>Admin Console</h2>
      <ErrorBanner error={error} />

      <TabBar tabs={["activity", "users", "tasks", "sellers", "marketplace", "benchmark", "audit"]} active={tab} onChange={setTab} color={C.admin} />

      {/* ---- ACTIVITY ---- */}
      {tab === "activity" && (
        <div>
          <SectionHeader title="Live Activity Log" color={C.admin} subtitle="polling every 5s" />
          <LogFeed logs={logs} maxHeight={560} />
        </div>
      )}

      {/* ---- USERS ---- */}
      {tab === "users" && (
        <div>
          <SectionHeader title={`Users (${users.length})`} color={C.admin}
            actions={<button onClick={() => adminApi.listUsers().then(setUsers)} style={btnStyle(C.admin)}>Refresh</button>} />
          {users.length === 0 ? <Spinner /> : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: "left", borderBottom: `1px solid ${C.border}` }}>
                  {["Email", "Name", "Role", "Joined", "Active"].map((h) => <th key={h} style={{ padding: "8px 6px" }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {users.map((u: any) => (
                  <tr key={u.id} style={{ borderBottom: `1px solid #1a1a1a` }}>
                    <td style={{ padding: "8px 6px", color: C.primary }}>{u.email}</td>
                    <td style={{ padding: "8px 6px", color: C.secondary }}>{u.display_name}</td>
                    <td style={{ padding: "8px 6px" }}><Badge label={u.role} color={ROLE_COLORS[u.role] ?? C.secondary} /></td>
                    <td style={{ padding: "8px 6px", color: C.muted }}>{new Date(u.created_at).toLocaleDateString()}</td>
                    <td style={{ padding: "8px 6px" }}><span style={{ color: u.is_active ? C.pass : C.fail }}>{u.is_active ? "yes" : "no"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ---- TASKS ---- */}
      {tab === "tasks" && (
        <div>
          <SectionHeader title={`All Tasks (${tasks.length})`} color={C.admin}
            actions={<button onClick={() => adminApi.listAllTasks().then(setTasks)} style={btnStyle(C.admin)}>Refresh</button>} />
          {tasks.length > 0 && (
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "16px" }}>
              {(["pending", "assigned", "in_progress", "completed", "failed"] as const).map((s) => (
                <StatCard key={s} label={s.replace(/_/g, " ")}
                  value={tasks.filter((t: any) => t.status === s).length}
                  color={STATUS_COLORS[s] ?? C.secondary} />
              ))}
            </div>
          )}
          {tasks.length === 0 ? <Spinner /> : tasks.map((t: any) => <TaskRow key={t.id} task={t} href={`/tasks/${t.id}`} />)}
        </div>
      )}

      {/* ---- SELLERS ---- */}
      {tab === "sellers" && (
        <div>
          <SectionHeader title="Seller Registry" color={C.admin}
            actions={<button onClick={() => adminApi.listSellers().then(setSellers)} style={btnStyle(C.admin)}>Refresh</button>} />
          {sellers.length > 0 && (
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "16px" }}>
              {(["approved", "needs_review", "pending", "rejected"] as const).map((s) => (
                <StatCard key={s} label={s.replace(/_/g, " ")}
                  value={sellers.filter((sel: any) => sel.approval_status === s).length}
                  color={APPROVAL_COLORS[s] ?? C.secondary} />
              ))}
            </div>
          )}
          {sellers.length === 0 ? <Spinner /> : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: "left", borderBottom: `1px solid ${C.border}` }}>
                  {["Name", "Categories", "Price", "Status", "Review Score", "Actions"].map((h) => <th key={h} style={{ padding: "8px 6px" }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {sellers.map((s: any) => (
                  <tr key={s.agent_id} style={{ borderBottom: `1px solid #1a1a1a`, verticalAlign: "top" }}>
                    <td style={{ padding: "8px 6px", color: C.seller }}>{s.name}</td>
                    <td style={{ padding: "8px 6px", color: C.secondary, fontSize: "11px" }}>
                      {(s.specializations as string[] ?? []).map((c: string) => c.replace(/_/g, " ")).join(", ")}
                    </td>
                    <td style={{ padding: "8px 6px", color: C.warn }}>${s.base_price}</td>
                    <td style={{ padding: "8px 6px" }}><Badge label={s.approval_status} color={APPROVAL_COLORS[s.approval_status] ?? C.secondary} /></td>
                    <td style={{ padding: "8px 6px" }}>
                      {s.onboarding_review ? (
                        <div>
                          <span style={{ color: scoreColor(s.onboarding_review.overall_score ?? 0) }}>
                            {((s.onboarding_review.overall_score ?? 0) * 100).toFixed(0)}%
                          </span>
                          <span style={{ color: C.muted, marginLeft: "6px", fontSize: "11px" }}>
                            {s.onboarding_review.review_status}
                          </span>
                          {s.onboarding_review.issues_count > 0 && (
                            <span style={{ color: C.fail, marginLeft: "5px", fontSize: "11px" }}>
                              {s.onboarding_review.issues_count} issue{s.onboarding_review.issues_count > 1 ? "s" : ""}
                            </span>
                          )}
                        </div>
                      ) : <span style={{ color: C.muted }}>—</span>}
                    </td>
                    <td style={{ padding: "8px 6px" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                        <div style={{ display: "flex", gap: "5px" }}>
                          <button onClick={() => handleApprove(s.agent_id)} disabled={loading}
                            style={{ ...btnStyle(C.pass), padding: "3px 8px", fontSize: "11px" }}>Approve</button>
                          <button onClick={() => handleReject(s.agent_id)} disabled={loading}
                            style={{ ...btnStyle(C.fail), padding: "3px 8px", fontSize: "11px" }}>Reject</button>
                        </div>
                        <input placeholder="Reject reason…"
                          value={rejectReason[s.agent_id] ?? ""}
                          onChange={(e) => setRejectReason((prev) => ({ ...prev, [s.agent_id]: e.target.value }))}
                          style={{ ...inputStyle, marginBottom: 0, fontSize: "11px", padding: "3px 7px" }} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ---- MARKETPLACE ---- */}
      {tab === "marketplace" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <SectionHeader title="Marketplace Analytics" color={C.admin} subtitle="24h window" />
            <button onClick={() => adminApi.getMarketplaceAnalytics(24).then(setMarketplace).catch(console.error)}
              style={{ ...btnStyle(C.admin) }}>Refresh</button>
          </div>
          {!marketplace ? <Spinner /> : <MarketplaceView data={marketplace} />}
        </div>
      )}

      {/* ---- BENCHMARK ---- */}
      {tab === "benchmark" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
          {/* Comparison summary */}
          <div>
            <SectionHeader title="Comparison Summary" color={C.admin} />
            {!benchSummary ? <Spinner /> : (
              <>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "14px" }}>
                  <StatCard label="Total"          value={(benchSummary as any).total_comparisons ?? 0} color={C.system} />
                  <StatCard label="Specialist Wins" value={(benchSummary as any).seller_wins ?? 0}      color={C.seller} />
                  <StatCard label="Generalist Wins" value={(benchSummary as any).generalist_wins ?? 0}  color={C.system} />
                  <StatCard label="Ties"            value={(benchSummary as any).ties ?? 0}             color={C.auditor} />
                </div>
                {(benchSummary as any).seller_win_rate != null && (
                  <div style={{ marginBottom: "10px" }}>
                    <div style={{ color: C.muted, fontSize: "11px", marginBottom: "4px" }}>Specialist Win Rate</div>
                    <ScoreBar score={(benchSummary as any).seller_win_rate} width={180} />
                  </div>
                )}
                {(benchSummary as any).avg_delta != null && (
                  <div style={{ fontSize: "12px", marginBottom: "12px" }}>
                    <Row k="Avg Δ"          v={`${((benchSummary as any).avg_delta * 100).toFixed(1)}%`} color={(benchSummary as any).avg_delta > 0 ? C.pass : C.fail} />
                    <Row k="Avg Specialist" v={`${(((benchSummary as any).avg_specialist_score ?? 0) * 100).toFixed(0)}%`} color={scoreColor((benchSummary as any).avg_specialist_score ?? 0)} />
                    <Row k="Avg Generalist" v={`${(((benchSummary as any).avg_generalist_score ?? 0) * 100).toFixed(0)}%`} color={scoreColor((benchSummary as any).avg_generalist_score ?? 0)} />
                  </div>
                )}
                {(benchSummary as any).by_category && Object.keys((benchSummary as any).by_category).length > 0 && (
                  <div>
                    <div style={{ color: C.muted, fontSize: "10px", textTransform: "uppercase", marginBottom: "6px" }}>By Category</div>
                    {Object.entries((benchSummary as any).by_category).map(([cat, d]: any) => (
                      <div key={cat} style={{ fontSize: "11px", marginBottom: "3px" }}>
                        <span style={{ color: C.secondary }}>{cat.replace(/_/g, " ")}: </span>
                        <span style={{ color: C.seller }}>{d.seller_wins}W </span>
                        <span style={{ color: C.system }}>{d.generalist_wins}W </span>
                        <span style={{ color: C.muted }}>{d.ties}T</span>
                      </div>
                    ))}
                  </div>
                )}
                {(benchSummary as any).total_comparisons === 0 && (
                  <Empty message="No benchmark comparisons yet. Execute a task with generalist_comparison_enabled=true." />
                )}
              </>
            )}
          </div>

          {/* Generalist profile */}
          <div>
            <SectionHeader title="Generalist Baseline" color={C.system} />
            {!generalist ? <Spinner /> : (
              <div style={cardStyle}>
                <div style={{ color: C.system, fontWeight: "bold", marginBottom: "4px" }}>{(generalist as any).name}</div>
                <div style={{ color: C.secondary, fontSize: "12px", marginBottom: "10px" }}>
                  {(generalist as any).model_identifier} · ${(generalist as any).cost_per_task ?? 0.02}/task · {(generalist as any).estimated_minutes ?? 5}min
                </div>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "12px" }}>
                  <StatCard label="Tasks Run" value={(generalist as any).tasks_completed ?? 0} color={C.system} />
                  <StatCard label="Benchmark"
                    value={(generalist as any).benchmark_score != null ? `${((generalist as any).benchmark_score * 100).toFixed(0)}%` : "—"}
                    color={C.auditor} />
                </div>
                {(generalist as any).record && (
                  <div style={{ fontSize: "12px", display: "flex", gap: "14px" }}>
                    <span style={{ color: C.fail }}>Losses: {(generalist as any).record.losses}</span>
                    <span style={{ color: C.pass }}>Wins: {(generalist as any).record.wins}</span>
                    <span style={{ color: C.auditor }}>Ties: {(generalist as any).record.ties}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ---- AUDIT ---- */}
      {tab === "audit" && (
        <div>
          <SectionHeader title="Audit Queue" color={C.admin}
            actions={
              <button onClick={() => {
                adminApi.getAuditQueue().then(setAuditQueue).catch(console.error);
                adminApi.getPendingAudits().then(setPendingAudits).catch(console.error);
              }} style={btnStyle(C.admin)}>Refresh</button>
            }
          />
          {auditQueue && (
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "20px" }}>
              <StatCard label="Unaudited Tasks"    value={(auditQueue as any).completed_unaudited ?? 0}    color={C.warn} />
              <StatCard label="Passed"             value={(auditQueue as any).audit_passed ?? 0}            color={C.pass} />
              <StatCard label="Failed"             value={(auditQueue as any).audit_failed ?? 0}            color={C.fail} />
              <StatCard label="Overridden"         value={(auditQueue as any).audit_overridden ?? 0}        color={C.admin} />
              <StatCard label="Reviews Pending"    value={(auditQueue as any).seller_reviews_queued ?? 0}   color={C.auditor} />
              <StatCard label="Sellers Approved"   value={(auditQueue as any).seller_reviews_approved ?? 0} color={C.pass} />
            </div>
          )}
          <SectionHeader title={`Completed Tasks Awaiting Audit (${pendingAudits.length})`} color={C.admin} />
          {pendingAudits.length === 0
            ? <Empty message="All completed tasks have been audited." />
            : pendingAudits.map((t: any) => <TaskRow key={t.id} task={t} href={`/tasks/${t.id}`} />)}
        </div>
      )}
    </div>
  );
}

function Row({ k, v, color }: { k: string; v: string; color?: string }) {
  return (
    <div style={{ marginBottom: "3px" }}>
      <span style={{ color: C.muted }}>{k}: </span>
      <span style={{ color: color ?? C.primary }}>{v}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MarketplaceView — renders the full analytics snapshot
// ---------------------------------------------------------------------------

const SIGNAL_COLORS: Record<string, string> = {
  healthy:        C.pass,
  balanced:       C.buyer,
  tight:          C.warn,
  over_subscribed: C.fail,
  no_demand:      C.muted,
};

function MarketplaceView({ data: d }: { data: import("../../lib/api").MarketplaceAnalytics }) {
  const cats = Object.keys(d.tasks.by_category).length > 0
    ? Object.keys(d.tasks.by_category)
    : ["financial_research", "legal_analysis", "market_intelligence", "strategy_business_research"];

  return (
    <div>
      {/* ── Snapshot time ─────────────────────────────────────────── */}
      <div style={{ color: C.muted, fontSize: "11px", marginBottom: "16px" }}>
        Snapshot: {new Date(d.snapshot_at).toLocaleString()} · demand window: {d.supply_demand.lookback_hours}h
      </div>

      {/* ── Participants ──────────────────────────────────────────── */}
      <SectionHeader title="Participants" color={C.system} />
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "20px" }}>
        <StatCard label="Active Buyers"  value={d.participants.active_buyers}   sub={`of ${d.participants.total_buyers} total`}  color={C.buyer} />
        <StatCard label="Active Sellers" value={d.participants.active_sellers}  sub={`of ${d.participants.total_sellers} total`} color={C.seller} />
        <StatCard label="Pending Review" value={d.participants.sellers_pending_review} color={C.warn} />
        {Object.entries(d.participants.sellers_by_category).map(([cat, n]) => (
          <StatCard key={cat} label={cat.replace(/_/g, " ")} value={n} sub="approved sellers" color={C.seller} />
        ))}
      </div>

      {/* ── Tasks ─────────────────────────────────────────────────── */}
      <SectionHeader title="Task Volume" color={C.system} />
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "8px" }}>
        <StatCard label="Total Tasks" value={d.tasks.total} color={C.system} />
        {Object.entries(d.tasks.by_status).map(([s, n]) => (
          <StatCard key={s} label={s.replace(/_/g, " ")} value={n} color={STATUS_COLORS[s] ?? C.secondary} />
        ))}
        {d.tasks.fill_rate != null && (
          <StatCard label="Fill Rate" value={`${(d.tasks.fill_rate * 100).toFixed(0)}%`}
            sub="completed / total" color={scoreColor(d.tasks.fill_rate)} />
        )}
      </div>

      {/* Category breakdown table */}
      {cats.length > 0 && (
        <div style={{ marginBottom: "20px", overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr style={{ color: C.muted, textAlign: "left", borderBottom: `1px solid ${C.border}` }}>
                <th style={{ padding: "6px 8px" }}>Category</th>
                <th style={{ padding: "6px 8px" }}>Tasks</th>
                <th style={{ padding: "6px 8px" }}>Fill Rate</th>
                <th style={{ padding: "6px 8px" }}>Avg Price</th>
                <th style={{ padding: "6px 8px" }}>Price Range</th>
                <th style={{ padding: "6px 8px" }}>Avg ETA</th>
                <th style={{ padding: "6px 8px" }}>Quotes</th>
                <th style={{ padding: "6px 8px" }}>Demand</th>
                <th style={{ padding: "6px 8px" }}>Supply</th>
                <th style={{ padding: "6px 8px" }}>D/S Ratio</th>
                <th style={{ padding: "6px 8px" }}>Signal</th>
              </tr>
            </thead>
            <tbody>
              {cats.map((cat) => {
                const fillR   = d.tasks.fill_rate_by_category[cat];
                const avgP    = d.pricing.avg_price_by_category[cat];
                const rangeP  = d.pricing.price_range_by_category[cat];
                const avgEta  = d.pricing.avg_eta_by_category[cat];
                const qVol    = d.pricing.quote_volume_by_category[cat] ?? 0;
                const demand  = d.supply_demand.demand_by_category[cat] ?? 0;
                const supply  = d.supply_demand.supply_by_category[cat] ?? 0;
                const ratio   = d.supply_demand.ratio_by_category[cat];
                const signal  = d.supply_demand.signal_by_category[cat] ?? "no_demand";
                const taskCnt = d.tasks.by_category[cat] ?? 0;
                return (
                  <tr key={cat} style={{ borderBottom: `1px solid #1a1a1a` }}>
                    <td style={{ padding: "6px 8px", color: C.seller, fontSize: "11px" }}>{cat.replace(/_/g, " ")}</td>
                    <td style={{ padding: "6px 8px", color: C.primary }}>{taskCnt}</td>
                    <td style={{ padding: "6px 8px" }}>
                      {fillR != null ? <span style={{ color: scoreColor(fillR) }}>{(fillR * 100).toFixed(0)}%</span> : <span style={{ color: C.muted }}>—</span>}
                    </td>
                    <td style={{ padding: "6px 8px", color: C.warn }}>
                      {avgP != null ? `$${avgP.toFixed(2)}` : "—"}
                    </td>
                    <td style={{ padding: "6px 8px", color: C.secondary, fontSize: "11px" }}>
                      {rangeP?.min != null ? `$${rangeP.min}–$${rangeP.max}` : "—"}
                    </td>
                    <td style={{ padding: "6px 8px", color: C.secondary }}>
                      {avgEta != null ? `${avgEta.toFixed(0)}min` : "—"}
                    </td>
                    <td style={{ padding: "6px 8px", color: C.secondary }}>{qVol}</td>
                    <td style={{ padding: "6px 8px", color: C.secondary }}>{demand}</td>
                    <td style={{ padding: "6px 8px", color: C.secondary }}>{supply}</td>
                    <td style={{ padding: "6px 8px", color: ratio != null ? scoreColor(Math.min(ratio / 2, 1)) : C.muted }}>
                      {ratio != null ? ratio.toFixed(2) : "—"}
                    </td>
                    <td style={{ padding: "6px 8px" }}>
                      <Badge label={signal.replace(/_/g, " ")} color={SIGNAL_COLORS[signal] ?? C.secondary} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Pricing trend placeholders ───────────────────────────── */}
      {Object.keys(d.pricing.price_trend_by_category).length > 0 && (
        <div style={{ marginBottom: "20px" }}>
          <SectionHeader title="Price Trends (accepted quotes, last 7 days)" color={C.system} subtitle="oldest → newest" />
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            {Object.entries(d.pricing.price_trend_by_category).map(([cat, trend]) => (
              <div key={cat} style={{ ...cardStyle, minWidth: "200px" }}>
                <div style={{ color: C.seller, fontSize: "11px", marginBottom: "6px" }}>{cat.replace(/_/g, " ")}</div>
                {trend.length === 0
                  ? <div style={{ color: C.muted, fontSize: "11px" }}>No accepted quotes yet</div>
                  : (
                    <div style={{ display: "flex", gap: "4px", alignItems: "flex-end", height: "40px" }}>
                      {trend.map((price, i) => {
                        const maxP = Math.max(...trend);
                        const pct  = maxP > 0 ? price / maxP : 0;
                        return (
                          <div key={i} title={`$${price}`} style={{
                            width: "16px", height: `${Math.max(4, pct * 36)}px`,
                            background: C.warn, borderRadius: "2px", flexShrink: 0,
                          }} />
                        );
                      })}
                    </div>
                  )}
                {trend.length > 0 && (
                  <div style={{ color: C.muted, fontSize: "10px", marginTop: "4px" }}>
                    latest: <span style={{ color: C.warn }}>${trend[trend.length - 1]}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Seller Utilization ────────────────────────────────────── */}
      <SectionHeader title="Seller Utilization" color={C.system}
        subtitle={d.seller_utilization.avg_utilization != null
          ? `avg ${(d.seller_utilization.avg_utilization * 100).toFixed(0)}%`
          : "no active sellers"} />
      {d.seller_utilization.sellers.length === 0
        ? <Empty message="No approved sellers." />
        : (
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "20px" }}>
            {d.seller_utilization.sellers.map((s) => (
              <div key={s.seller_id} style={{ ...cardStyle, minWidth: "160px" }}>
                <div style={{ color: C.seller, fontSize: "12px", fontWeight: "bold", marginBottom: "4px" }}>{s.name}</div>
                <div style={{ color: C.muted, fontSize: "10px", marginBottom: "6px" }}>
                  {s.categories.map(c => c.replace(/_/g, " ")).join(", ")}
                </div>
                <ScoreBar score={s.utilization} width={130} />
                <div style={{ fontSize: "11px", marginTop: "4px" }}>
                  <span style={{ color: C.muted }}>{s.active_tasks}/{s.capacity} tasks · </span>
                  <Badge label={s.status} color={s.status === "busy" ? C.warn : C.pass} />
                </div>
              </div>
            ))}
          </div>
        )}

      {/* ── Specialist vs. Generalist ─────────────────────────────── */}
      <SectionHeader title="Specialist vs. Generalist" color={C.system} />
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
        <StatCard label="Comparisons" value={d.specialist_vs_generalist.total_comparisons} color={C.system} />
        {d.specialist_vs_generalist.specialist_win_rate != null && (
          <StatCard label="Specialist Win Rate"
            value={`${(d.specialist_vs_generalist.specialist_win_rate * 100).toFixed(0)}%`}
            color={scoreColor(d.specialist_vs_generalist.specialist_win_rate)} />
        )}
        {d.specialist_vs_generalist.avg_quality_delta != null && (
          <StatCard label="Avg Quality Δ"
            value={`${d.specialist_vs_generalist.avg_quality_delta >= 0 ? "+" : ""}${(d.specialist_vs_generalist.avg_quality_delta * 100).toFixed(1)}%`}
            color={d.specialist_vs_generalist.avg_quality_delta >= 0 ? C.pass : C.fail} />
        )}
        {d.specialist_vs_generalist.total_comparisons === 0 && (
          <Empty message="No comparisons yet. Execute a task to generate benchmark data." />
        )}
      </div>
    </div>
  );
}
