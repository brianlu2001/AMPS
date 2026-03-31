"use client";
/**
 * Task Detail Page  — /tasks/[id]
 *
 * The single most information-dense view in AMPS. Shows:
 *   - Task metadata + lifecycle status
 *   - Marketplace quotes (ranked by match score)
 *   - Seller selection control (if PENDING)
 *   - Delivered output (if COMPLETED)
 *   - Generalist baseline output (if comparison enabled)
 *   - Audit result with dimension scores
 *   - Benchmark comparison (specialist vs. generalist)
 *   - Task-level activity log
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  buyerApi, auditApi, adminApi,
  Task, Quote, AuditResult, BenchmarkComparison, ActivityLog,
} from "../../../lib/api";
import {
  C, SectionHeader, StatCard, QuoteCard, Badge, ScoreBar,
  DimensionScores, LogFeed, ErrorBanner, Empty, Spinner, btnStyle, cardStyle,
  scoreColor, STATUS_COLORS, AUDIT_COLORS, APPROVAL_COLORS,
} from "../../../components/ui";

export default function TaskDetailPage() {
  const params = useParams();
  const taskId = params?.id as string;

  const [task, setTask]           = useState<Task | null>(null);
  const [quotes, setQuotes]       = useState<Quote[]>([]);
  const [audit, setAudit]         = useState<AuditResult | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkComparison | null>(null);
  const [logs, setLogs]           = useState<ActivityLog[]>([]);
  const [showOutput, setShowOutput] = useState<"seller" | "generalist" | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  // Load all data
  useEffect(() => {
    if (!taskId) return;
    const load = async () => {
      try {
        // Task — try buyer route first, fall back to admin
        let t: Task;
        try { t = await buyerApi.getTask(taskId); }
        catch { t = (await adminApi.listAllTasks()).find((x: any) => x.id === taskId) as unknown as Task; }
        if (!t) throw new Error("Task not found");
        setTask(t);

        // Quotes
        if (t.quote_ids?.length) {
          try { setQuotes(await buyerApi.getQuotes(taskId)); } catch {}
        }

        // Audit result
        if (t.audit_result_id) {
          try {
            const ar = await auditApi.getTaskAudit(taskId);
            setAudit(ar.audit_result);
            setBenchmark(ar.benchmark_comparison);
          } catch {}
        }

        // Benchmark (even without audit result, if comparison ran)
        if (t.benchmark_comparison_id && !benchmark) {
          try { setBenchmark(await auditApi.getBenchmark(taskId)); } catch {}
        }

        // Logs (admin only — graceful failure for non-admins)
        try { setLogs((await adminApi.getLogs(50, taskId)).reverse()); } catch {}

      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [taskId]);

  // Poll task + logs every 5s while in-progress
  useEffect(() => {
    if (!task || !["pending", "assigned", "in_progress"].includes(task.status)) return;
    const iv = setInterval(async () => {
      try {
        let t: Task;
        try { t = await buyerApi.getTask(taskId); }
        catch { return; }
        setTask(t);
      } catch {}
    }, 5000);
    return () => clearInterval(iv);
  }, [task?.status]);

  const handleSelectSeller = async (sellerId: string) => {
    try {
      await buyerApi.selectSeller(taskId, sellerId);
      const t = await buyerApi.getTask(taskId);
      setTask(t);
    } catch (e) { setError(String(e)); }
  };

  if (loading) return <div style={{ padding: "24px" }}><Spinner /></div>;
  if (!task) return <div style={{ padding: "24px" }}><ErrorBanner error={error || "Task not found."} /></div>;

  const acceptedQuote = quotes.find((q) => q.accepted);

  return (
    <div style={{ maxWidth: "920px" }}>
      {/* Back nav */}
      <div style={{ marginBottom: "16px" }}>
        <a href="/buyer" style={{ color: C.muted, fontSize: "12px", textDecoration: "none" }}>← Buyer Console</a>
        <span style={{ color: C.muted, fontSize: "12px" }}> / Task</span>
      </div>

      <ErrorBanner error={error} />

      {/* ---- Task header ---- */}
      <div style={{ ...cardStyle, marginBottom: "16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
          <h2 style={{ color: C.primary, margin: 0, fontSize: "16px" }}>{task.title}</h2>
          <div style={{ display: "flex", gap: "6px" }}>
            <Badge label={task.status}       color={STATUS_COLORS[task.status] ?? C.secondary} />
            <Badge label={task.audit_status} color={AUDIT_COLORS[task.audit_status] ?? C.secondary} />
          </div>
        </div>
        <div style={{ color: C.secondary, fontSize: "13px", marginBottom: "8px", lineHeight: "1.5" }}>
          {task.description}
        </div>
        <div style={{ display: "flex", gap: "20px", fontSize: "12px", flexWrap: "wrap" }}>
          <span><span style={{ color: C.muted }}>Category: </span><span style={{ color: C.primary }}>{task.category.replace(/_/g, " ")}</span></span>
          <span><span style={{ color: C.muted }}>Output: </span><span style={{ color: C.primary }}>{task.requested_output_type}</span></span>
          <span><span style={{ color: C.muted }}>Created: </span><span style={{ color: C.primary }}>{new Date(task.created_at).toLocaleString()}</span></span>
          {task.completed_at && <span><span style={{ color: C.muted }}>Completed: </span><span style={{ color: C.pass }}>{new Date(task.completed_at).toLocaleString()}</span></span>}
          {task.generalist_comparison_enabled && <Badge label="benchmark enabled" color={C.system} />}
        </div>
        {acceptedQuote && (
          <div style={{ marginTop: "10px", padding: "8px", background: "#111", borderRadius: "4px", fontSize: "12px", display: "flex", gap: "16px" }}>
            <span><span style={{ color: C.muted }}>Selected seller: </span><span style={{ color: C.seller }}>{acceptedQuote.seller_display_name ?? acceptedQuote.seller_id.slice(0, 8)}</span></span>
            <span><span style={{ color: C.muted }}>Price: </span><span style={{ color: C.warn }}>${acceptedQuote.proposed_price.toFixed(2)}</span></span>
            <span><span style={{ color: C.muted }}>Match: </span><span style={{ color: scoreColor(acceptedQuote.match_score) }}>{(acceptedQuote.match_score * 100).toFixed(0)}%</span></span>
          </div>
        )}
      </div>

      {/* ---- Quotes ---- */}
      {quotes.length > 0 && (
        <div style={{ marginBottom: "16px" }}>
          <SectionHeader title={`Quotes (${quotes.length})`} color={C.seller} subtitle="ranked by match score" />
          {quotes.map((q) => (
            <QuoteCard
              key={q.id}
              quote={q}
              isSelected={q.accepted || task.selected_quote_id === q.id}
              onSelect={task.status === "pending" ? () => handleSelectSeller(q.seller_id) : undefined}
            />
          ))}
        </div>
      )}
      {quotes.length === 0 && task.status === "pending" && (
        <div style={{ ...cardStyle, marginBottom: "16px" }}>
          <Empty message="No quotes yet. Marketplace matching runs automatically when a task is created." />
          <button
            onClick={async () => { try { await buyerApi.refreshMarketplace(taskId); const t = await buyerApi.getTask(taskId); setTask(t); setQuotes(await buyerApi.getQuotes(taskId)); } catch (e) { setError(String(e)); } }}
            style={{ ...btnStyle(C.buyer), marginTop: "8px" }}
          >
            Re-run Marketplace Matching
          </button>
        </div>
      )}

      {/* ---- Delivered outputs ---- */}
      {(task.seller_result || task.generalist_result) && (
        <div style={{ marginBottom: "16px" }}>
          <SectionHeader title="Delivered Outputs" color={C.primary} />
          <div style={{ display: "flex", gap: "8px", marginBottom: "10px" }}>
            {task.seller_result && (
              <button onClick={() => setShowOutput(showOutput === "seller" ? null : "seller")}
                style={{ ...btnStyle(C.seller), fontSize: "12px", padding: "5px 14px" }}>
                {showOutput === "seller" ? "▲" : "▼"} Specialist Output
              </button>
            )}
            {task.generalist_result && (
              <button onClick={() => setShowOutput(showOutput === "generalist" ? null : "generalist")}
                style={{ ...btnStyle(C.system), fontSize: "12px", padding: "5px 14px" }}>
                {showOutput === "generalist" ? "▲" : "▼"} Generalist Baseline
              </button>
            )}
          </div>
          {showOutput === "seller" && task.seller_result && (
            <OutputPanel label="Specialist Output" color={C.seller} result={task.seller_result} />
          )}
          {showOutput === "generalist" && task.generalist_result && (
            <OutputPanel label="Generalist Baseline" color={C.system} result={task.generalist_result} />
          )}
        </div>
      )}

      {/* ---- Audit result ---- */}
      {audit && (
        <div style={{ marginBottom: "16px" }}>
          <SectionHeader title="Audit Result" color={C.auditor} />
          <div style={cardStyle}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
              <div style={{ display: "flex", gap: "10px", alignItems: "baseline" }}>
                <span style={{ color: scoreColor(audit.composite_score), fontSize: "26px", fontWeight: "bold" }}>
                  {(audit.composite_score * 100).toFixed(1)}%
                </span>
                {audit.passed ? <Badge label="PASSED" color={C.pass} /> : <Badge label="FAILED" color={C.fail} />}
                {audit.admin_override && <Badge label="ADMIN OVERRIDE" color={C.admin} />}
              </div>
              <span style={{ color: C.muted, fontSize: "11px" }}>{audit.scoring_method}</span>
            </div>
            {audit.dimension_scores && Object.keys(audit.dimension_scores).length > 0 && (
              <div style={{ marginBottom: "10px" }}>
                <DimensionScores scores={audit.dimension_scores} />
              </div>
            )}
            <div style={{ color: C.secondary, fontSize: "12px", lineHeight: "1.5", marginBottom: "8px" }}>
              {audit.reasoning}
            </div>
            {audit.flags.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "5px", marginBottom: "6px" }}>
                {audit.flags.map((f) => <Badge key={f} label={f} color={C.fail} />)}
              </div>
            )}
            {audit.recommendations && audit.recommendations.length > 0 && (
              <div>{audit.recommendations.map((r, i) => <div key={i} style={{ color: C.warn, fontSize: "11px" }}>→ {r}</div>)}</div>
            )}
          </div>
        </div>
      )}

      {/* ---- Benchmark comparison ---- */}
      {benchmark && (
        <div style={{ marginBottom: "16px" }}>
          <SectionHeader title="Benchmark: Specialist vs. Generalist" color={C.auditor} />
          <div style={cardStyle}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "12px" }}>
              <div>
                <div style={{ color: C.seller, fontSize: "11px", marginBottom: "4px" }}>Specialist {benchmark.seller_display_name ? `— ${benchmark.seller_display_name}` : ""}</div>
                <div style={{ color: scoreColor(benchmark.seller_score), fontSize: "26px", fontWeight: "bold" }}>{(benchmark.seller_score * 100).toFixed(1)}%</div>
                <div style={{ color: C.muted, fontSize: "11px" }}>${benchmark.specialist_cost.toFixed(2)} · {benchmark.specialist_eta_minutes}min</div>
                {benchmark.seller_dimension_scores && Object.keys(benchmark.seller_dimension_scores).length > 0 && (
                  <div style={{ marginTop: "8px" }}><DimensionScores scores={benchmark.seller_dimension_scores} /></div>
                )}
              </div>
              <div>
                <div style={{ color: C.system, fontSize: "11px", marginBottom: "4px" }}>Generalist {benchmark.generalist_model ? `— ${benchmark.generalist_model}` : ""}</div>
                <div style={{ color: scoreColor(benchmark.generalist_score), fontSize: "26px", fontWeight: "bold" }}>{(benchmark.generalist_score * 100).toFixed(1)}%</div>
                <div style={{ color: C.muted, fontSize: "11px" }}>${benchmark.generalist_cost.toFixed(2)} · {benchmark.generalist_eta_minutes}min</div>
                {benchmark.generalist_dimension_scores && Object.keys(benchmark.generalist_dimension_scores).length > 0 && (
                  <div style={{ marginTop: "8px" }}><DimensionScores scores={benchmark.generalist_dimension_scores} /></div>
                )}
              </div>
            </div>
            <div style={{ display: "flex", gap: "10px", alignItems: "center", marginBottom: "8px" }}>
              <Badge label={benchmark.winner.toUpperCase()} color={benchmark.winner === "seller" ? C.seller : benchmark.winner === "generalist" ? C.system : C.auditor} />
              <span style={{ fontSize: "12px", color: benchmark.delta > 0 ? C.pass : C.fail }}>Δ {benchmark.delta > 0 ? "+" : ""}{(benchmark.delta * 100).toFixed(1)}%</span>
              <Badge label={benchmark.recommendation.replace(/_/g, " ")} color={benchmark.recommendation.includes("specialist") ? C.seller : C.system} />
            </div>
            {benchmark.summary && <div style={{ color: C.secondary, fontSize: "11px", lineHeight: "1.4" }}>{benchmark.summary}</div>}
          </div>
        </div>
      )}

      {/* ---- Task log ---- */}
      {logs.length > 0 && (
        <div>
          <SectionHeader title="Task Activity Log" color={C.muted} />
          <LogFeed logs={logs} maxHeight={260} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// OutputPanel — pretty-print one agent's result
// ---------------------------------------------------------------------------

function OutputPanel({ label, color, result }: { label: string; color: string; result: Record<string, unknown> }) {
  const summary = result.summary as string | undefined;
  const fields = Object.entries(result).filter(([k]) => !["category", "output_type", "mock", "agent_type", "summary"].includes(k));

  return (
    <div style={{ ...cardStyle, marginBottom: "10px", border: `1px solid ${color}44` }}>
      <div style={{ color, fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "8px" }}>{label}</div>
      {summary && (
        <div style={{ color: C.primary, fontSize: "12px", lineHeight: "1.6", marginBottom: "10px" }}>{summary}</div>
      )}
      {fields.map(([k, v]) => (
        <div key={k} style={{ marginBottom: "5px", fontSize: "12px" }}>
          <span style={{ color: C.muted }}>{k.replace(/_/g, " ")}: </span>
          {Array.isArray(v) ? (
            <div style={{ paddingLeft: "8px" }}>
              {(v as unknown[]).map((item, i) => (
                <div key={i} style={{ color: C.secondary }}>
                  {typeof item === "object" ? JSON.stringify(item) : String(item)}
                </div>
              ))}
            </div>
          ) : typeof v === "object" && v !== null ? (
            <span style={{ color: C.secondary }}>{JSON.stringify(v)}</span>
          ) : (
            <span style={{ color: C.secondary }}>{String(v)}</span>
          )}
        </div>
      ))}
    </div>
  );
}
