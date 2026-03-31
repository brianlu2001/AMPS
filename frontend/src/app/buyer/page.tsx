"use client";
/**
 * Buyer Dashboard
 *
 * Tabs:
 *   Overview    — summary stats + recent task list
 *   Submit      — onboard + submit new task
 *   Tasks       — full task list with status + quotes
 *   Timeline    — personal activity log (polled 5s)
 */

import { useEffect, useState } from "react";
import {
  buyerApi, session, Task, Quote, ActivityLog, TaskCategory,
} from "../../lib/api";
import {
  C, SectionHeader, StatCard, TaskRow, QuoteCard, LogFeed,
  Badge, TabBar, Spinner, ErrorBanner, Empty,
  btnStyle, cardStyle, inputStyle, scoreColor, STATUS_COLORS,
} from "../../components/ui";

const CATEGORIES: TaskCategory[] = [
  "financial_research", "legal_analysis",
  "market_intelligence", "strategy_business_research",
];
const EXAMPLE_INSTRUCTIONS = [
  "Read this link and enroll me as a buyer agent.",
  "I'm from Meridian Capital. Set me up as a buyer for financial research.",
  "Enroll me — I need legal analysis and market intelligence.",
];
const STAGE_COLORS: Record<string, string> = {
  ok: C.pass, mock: C.warn, fetch_error: C.fail, parse_error: C.fail, none: C.muted,
};

export default function BuyerPage() {
  const user = session.getUser();
  const [tab, setTab] = useState("overview");

  // Profile state
  const [profile, setProfile]             = useState<Record<string, unknown> | null>(null);
  const [onboardResult, setOnboardResult] = useState<Record<string, unknown> | null>(null);
  const [instruction, setInstruction]     = useState(EXAMPLE_INSTRUCTIONS[0]);
  const [url, setUrl]                     = useState("");

  // Task state
  const [tasks, setTasks]         = useState<Task[]>([]);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDesc, setTaskDesc]   = useState("");
  const [taskCat, setTaskCat]     = useState<TaskCategory>("financial_research");

  // Quote state
  const [quotesByTask, setQuotesByTask] = useState<Record<string, Quote[]>>({});
  const [selectingTask, setSelectingTask] = useState<string | null>(null);

  // Logs
  const [logs, setLogs] = useState<ActivityLog[]>([]);

  // UI
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  // Restore profile from session
  useEffect(() => {
    if (user?.buyer_profile_id) setProfile({ id: user.buyer_profile_id });
  }, []);

  // Poll tasks
  useEffect(() => {
    if (!profile?.id) return;
    const fetch = () => buyerApi.listTasks().then(setTasks).catch(console.error);
    fetch();
    const iv = setInterval(fetch, 5000);
    return () => clearInterval(iv);
  }, [profile?.id]);

  // Fetch quotes for completed/assigned tasks
  useEffect(() => {
    tasks.forEach((t) => {
      if (t.quote_ids?.length && !quotesByTask[t.id]) {
        buyerApi.getQuotes(t.id)
          .then((qs) => setQuotesByTask((prev) => ({ ...prev, [t.id]: qs })))
          .catch(() => {});
      }
    });
  }, [tasks]);

  // Note: task polling is handled by the effect above (gated on profile?.id).
  // No separate poll needed here — removing the redundant user-gated listTasks call.

  const handleOnboard = async () => {
    setLoading(true); setError(null);
    try {
      const res = await buyerApi.onboard(instruction, url || null);
      setOnboardResult(res);
      if ((res as any).success && (res as any).profile) {
        setProfile((res as any).profile);
      }
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const handleCreateTask = async () => {
    if (!profile?.id) return;
    setLoading(true); setError(null);
    try {
      const res = await buyerApi.createTask({
        buyer_id: profile.id as string, title: taskTitle,
        description: taskDesc, category: taskCat,
        enable_generalist_comparison: true,
      });
      const newTask = (res as any).task as Task;
      setTasks((prev) => [newTask, ...prev]);
      setTaskTitle(""); setTaskDesc("");
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const handleSelectSeller = async (taskId: string, sellerId: string) => {
    setLoading(true);
    try {
      await buyerApi.selectSeller(taskId, sellerId);
      const updated = await buyerApi.listTasks();
      setTasks(updated);
      setSelectingTask(null);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  // Derived stats
  const completedTasks = tasks.filter((t) => t.status === "completed");
  const totalSpend = Object.values(quotesByTask)
    .flat()
    .filter((q) => q.accepted)
    .reduce((sum, q) => sum + q.proposed_price, 0);
  const auditPassed = completedTasks.filter((t) => t.audit_status === "passed").length;

  return (
    <div style={{ maxWidth: "900px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
        <h2 style={{ color: C.buyer, margin: 0 }}>Buyer Console</h2>
        {profile?.id && (
          <div style={{ textAlign: "right", fontSize: "11px", color: C.muted }}>
            {user?.email}<br />
            Profile: <span style={{ color: C.buyer }}>{String(profile.id).slice(0, 8)}…</span>
            {(profile as any).organization && <> · {(profile as any).organization}</>}
          </div>
        )}
      </div>

      <ErrorBanner error={error} />

      {/* Stats row */}
      {profile?.id && (
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "24px" }}>
          <StatCard label="Tasks"     value={tasks.length}        color={C.buyer} />
          <StatCard label="Completed" value={completedTasks.length} color={C.pass} />
          <StatCard label="Total Spend" value={`$${totalSpend.toFixed(0)}`} color={C.warn} />
          <StatCard label="Audits Passed" value={auditPassed} sub={`of ${completedTasks.length}`} color={C.pass} />
        </div>
      )}

      <TabBar tabs={["overview", "submit", "tasks", "timeline"]} active={tab} onChange={setTab} color={C.buyer} />

      {/* ---- OVERVIEW ---- */}
      {tab === "overview" && (
        <div>
          {!profile?.id ? (
            <div style={{ color: C.secondary, fontSize: "13px" }}>
              Go to the <button onClick={() => setTab("submit")} style={{ background: "none", border: "none", color: C.buyer, cursor: "pointer", fontFamily: "monospace", fontSize: "13px", textDecoration: "underline" }}>Submit</button> tab to enroll as a buyer agent first.
            </div>
          ) : (
            <>
              <SectionHeader title="Recent Tasks" color={C.buyer} subtitle="latest 5" />
              {tasks.slice(0, 5).map((t) => (
                <TaskRow key={t.id} task={t} href={`/tasks/${t.id}`} />
              ))}
              {tasks.length === 0 && <Empty message="No tasks yet. Submit your first task." />}
            </>
          )}
        </div>
      )}

      {/* ---- SUBMIT ---- */}
      {tab === "submit" && (
        <div style={{ maxWidth: "520px" }}>
          {/* Onboarding */}
          <SectionHeader title="Enroll as Buyer Agent" color={C.buyer} />
          <div style={{ color: C.muted, fontSize: "12px", marginBottom: "10px" }}>
            Provide a natural-language instruction + optional URL. The pipeline parses, fetches, and extracts your profile.
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "5px", marginBottom: "10px" }}>
            {EXAMPLE_INSTRUCTIONS.map((ex) => (
              <button key={ex} onClick={() => setInstruction(ex)} style={{
                background: instruction === ex ? "#1e2e1e" : "transparent",
                border: `1px solid ${instruction === ex ? C.buyer : C.inputBorder}`,
                color: instruction === ex ? C.buyer : C.muted,
                padding: "3px 10px", cursor: "pointer", borderRadius: "12px",
                fontSize: "11px", fontFamily: "monospace",
              }}>
                {ex.length > 52 ? ex.slice(0, 50) + "…" : ex}
              </button>
            ))}
          </div>
          <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={2} style={{ ...inputStyle, resize: "vertical" }} />
          <input type="url" placeholder="Context URL (optional)" value={url} onChange={(e) => setUrl(e.target.value)} style={inputStyle} />
          <button onClick={handleOnboard} disabled={loading || !instruction.trim()} style={btnStyle(C.buyer)}>
            {loading ? "Enrolling…" : "Enroll as Buyer Agent"}
          </button>
          {onboardResult && <OnboardingResult result={onboardResult} />}

          {/* Task creation (only if enrolled) */}
          {profile?.id && (
            <>
              <div style={{ marginTop: "32px" }} />
              <SectionHeader title="Submit New Task" color={C.buyer} />
              <input placeholder="Task title" value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} style={inputStyle} />
              <textarea placeholder="Task description / prompt" value={taskDesc} onChange={(e) => setTaskDesc(e.target.value)} rows={3} style={{ ...inputStyle, resize: "vertical" }} />
              <select value={taskCat} onChange={(e) => setTaskCat(e.target.value as TaskCategory)} style={inputStyle}>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
              </select>
              <button onClick={handleCreateTask} disabled={loading || !taskTitle.trim() || !taskDesc.trim()} style={btnStyle(C.buyer)}>
                {loading ? "Submitting…" : "Submit Task →"}
              </button>
            </>
          )}
        </div>
      )}

      {/* ---- TASKS ---- */}
      {tab === "tasks" && (
        <div>
          <SectionHeader title="My Tasks" color={C.buyer} subtitle="polling every 5s" />
          {tasks.length === 0 && <Empty message="No tasks yet." />}
          {tasks.map((t) => (
            <div key={t.id} style={{ ...cardStyle, marginBottom: "10px" }}>
              {/* Task header */}
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                <a href={`/tasks/${t.id}`} style={{ color: C.primary, fontWeight: "bold", textDecoration: "none", fontSize: "13px" }}>
                  {t.title}
                </a>
                <div style={{ display: "flex", gap: "6px" }}>
                  <Badge label={t.status}       color={STATUS_COLORS[t.status] ?? C.secondary} />
                  <Badge label={t.audit_status} color={t.audit_status === "passed" ? C.pass : t.audit_status === "failed" ? C.fail : C.warn} />
                </div>
              </div>
              <div style={{ color: C.muted, fontSize: "11px", marginBottom: "8px" }}>
                {t.category.replace(/_/g, " ")} · {new Date(t.created_at).toLocaleDateString()}
                {t.selected_seller_id && <> · Seller: <span style={{ color: C.seller }}>{t.selected_seller_id.slice(0, 8)}</span></>}
              </div>

              {/* Quotes */}
              {quotesByTask[t.id] && quotesByTask[t.id].length > 0 && (
                <div>
                  <div style={{ color: C.muted, fontSize: "11px", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                    Quotes ({quotesByTask[t.id].length})
                    {t.status === "pending" && (
                      <button onClick={() => setSelectingTask(selectingTask === t.id ? null : t.id)}
                        style={{ marginLeft: "8px", background: "none", border: "none", color: C.buyer, cursor: "pointer", fontSize: "11px", fontFamily: "monospace" }}>
                        {selectingTask === t.id ? "▲ hide" : "▼ select seller"}
                      </button>
                    )}
                  </div>
                  {selectingTask === t.id && quotesByTask[t.id].map((q) => (
                    <QuoteCard key={q.id} quote={q}
                      isSelected={t.selected_quote_id === q.id}
                      onSelect={() => handleSelectSeller(t.id, q.seller_id)} />
                  ))}
                  {selectingTask !== t.id && quotesByTask[t.id].slice(0, 1).map((q) => (
                    <div key={q.id} style={{ fontSize: "12px", color: C.secondary }}>
                      Best: <span style={{ color: C.seller }}>{q.seller_display_name}</span>
                      {" · "}${q.proposed_price} · Match: <span style={{ color: scoreColor(q.match_score) }}>{(q.match_score * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ---- TIMELINE ---- */}
      {tab === "timeline" && (
        <div>
          <SectionHeader title="My Activity" color={C.buyer} subtitle="derived from task events" />
          <div style={{ color: C.muted, fontSize: "12px", marginBottom: "10px" }}>
            Showing events related to your tasks. Full log available in the Admin console.
          </div>
          <Empty message="Task-level event timeline — view full log in Admin console or drill into a task at /tasks/{id}." />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Onboarding result panel (re-used from prior version, cleaned up)
// ---------------------------------------------------------------------------

function OnboardingResult({ result }: { result: Record<string, unknown> }) {
  const success    = result.success as boolean;
  const message    = result.message as string;
  const confidence = (result.confidence as number) ?? 0;
  const profile    = result.profile as Record<string, unknown> | null;
  const warnings   = result.warnings as string[] ?? [];

  return (
    <div style={{ marginTop: "12px", background: C.inset, border: `1px solid ${success ? C.pass + "44" : C.fail + "44"}`, borderRadius: "6px", padding: "14px", fontSize: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "10px" }}>
        <span style={{ color: success ? C.pass : C.fail, fontWeight: "bold" }}>{success ? "ENROLLED" : "FAILED"}</span>
        {success && <span style={{ color: C.muted }}>Confidence: <span style={{ color: scoreColor(confidence) }}>{(confidence * 100).toFixed(0)}%</span></span>}
      </div>
      <div style={{ color: C.primary, lineHeight: "1.5", marginBottom: "8px" }}>{message}</div>
      {profile && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
          {(profile.organization as string) && <KV k="Organization" v={profile.organization as string} />}
          {(profile.industry_hint as string) && <KV k="Industry" v={profile.industry_hint as string} />}
          {Array.isArray(profile.preferred_categories) && profile.preferred_categories.length > 0 &&
            <KV k="Categories" v={(profile.preferred_categories as string[]).map(c => c.replace(/_/g, " ")).join(", ")} />}
        </div>
      )}
      {warnings.length > 0 && (
        <div style={{ marginTop: "8px" }}>
          {warnings.map((w, i) => <div key={i} style={{ color: C.warn, fontSize: "11px" }}>⚠ {w}</div>)}
        </div>
      )}
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ fontSize: "11px" }}>
      <span style={{ color: C.muted }}>{k}: </span>
      <span style={{ color: C.primary }}>{v}</span>
    </div>
  );
}

const inset = C.inset;
