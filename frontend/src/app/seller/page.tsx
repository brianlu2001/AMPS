"use client";
/**
 * Seller Dashboard
 *
 * Tabs:
 *   Overview    — stats: tasks won, revenue, audit score, benchmark standing
 *   My Tasks    — tasks assigned to this seller
 *   Marketplace — all seller agents (for discovery / comparison)
 *   Execute     — dev tool: run seller on a task
 */

import { useEffect, useState } from "react";
import { sellerApi, session, Task } from "../../lib/api";
import {
  C, SectionHeader, StatCard, TaskRow, Badge, ScoreBar,
  DimensionScores, TabBar, Spinner, ErrorBanner, Empty,
  btnStyle, cardStyle, inputStyle, scoreColor, APPROVAL_COLORS,
} from "../../components/ui";

export default function SellerPage() {
  const user = session.getUser();
  const isSeller = user?.role === "seller";
  const [tab, setTab] = useState("overview");

  // Own seller state
  const [myProfile, setMyProfile]     = useState<Record<string, unknown> | null>(null);
  const [myReview, setMyReview]       = useState<Record<string, unknown> | null>(null);
  const [myTasks, setMyTasks]         = useState<Record<string, unknown>[]>([]);

  // Marketplace
  const [allSellers, setAllSellers]   = useState<Record<string, unknown>[]>([]);

  // Execute tool
  const [taskId, setTaskId]           = useState("");
  const [execSellerId, setExecSellerId] = useState("");
  const [execResult, setExecResult]   = useState<Record<string, unknown> | null>(null);

  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  // Load on mount
  useEffect(() => {
    sellerApi.listAgents().then(setAllSellers).catch(console.error);
    if (isSeller) {
      sellerApi.listMyTasks()
        .then(setMyTasks)
        .catch(console.error);
      sellerApi.getRegistrationStatus()
        .then((s) => {
          setMyProfile((s as any).seller_profile ?? null);
          setMyReview((s as any).onboarding_review ?? null);
        })
        .catch(console.error);
    }
  }, [isSeller]);

  // Poll my tasks
  useEffect(() => {
    if (!isSeller) return;
    const iv = setInterval(() => {
      sellerApi.listMyTasks().then(setMyTasks).catch(() => {});
    }, 5000);
    return () => clearInterval(iv);
  }, [isSeller]);

  const handleExecute = async () => {
    if (!taskId || !execSellerId) return;
    setLoading(true); setError(null);
    try {
      const task = await sellerApi.runOnTask(taskId, execSellerId);
      setExecResult(task as unknown as Record<string, unknown>);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  // Derived stats for seller's own view
  const completedTasks = myTasks.filter((t: any) => t.status === "completed");
  const revenue = myTasks
    .filter((t: any) => t.status === "completed" && t.selected_seller_id)
    .length; // placeholder count — real revenue from quotes

  const repScore   = myProfile ? Number((myProfile as any).reputation_score ?? 0) : 0;
  const benchScore = myProfile ? (myProfile as any).benchmark_score : null;

  return (
    <div style={{ maxWidth: "900px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
        <h2 style={{ color: C.seller, margin: 0 }}>Seller Console</h2>
        {user && (
          <div style={{ textAlign: "right", fontSize: "11px", color: C.muted }}>
            {user.email}
            {myProfile && (
              <><br /><span style={{ color: C.seller }}>{(myProfile as any).display_name}</span></>
            )}
          </div>
        )}
      </div>

      <ErrorBanner error={error} />

      {/* Stats (seller-specific) */}
      {isSeller && (
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "24px" }}>
          <StatCard label="Tasks"      value={myTasks.length}       color={C.seller} />
          <StatCard label="Completed"  value={completedTasks.length} color={C.pass} />
          <StatCard label="Reputation" value={repScore.toFixed(1)}  sub="/ 5.0" color={C.warn} />
          {benchScore !== null && benchScore !== undefined
            ? <StatCard label="Benchmark"  value={`${(Number(benchScore) * 100).toFixed(0)}%`} color={scoreColor(Number(benchScore))} />
            : <StatCard label="Benchmark"  value="—"  sub="no comparisons yet" color={C.muted} />}
        </div>
      )}

      <TabBar
        tabs={isSeller ? ["overview", "my tasks", "marketplace", "execute"] : ["marketplace", "execute"]}
        active={tab} onChange={setTab} color={C.seller}
      />

      {/* ---- OVERVIEW ---- */}
      {tab === "overview" && isSeller && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
          {/* Profile card */}
          <div style={cardStyle}>
            <SectionHeader title="My Profile" color={C.seller} />
            {myProfile ? (
              <>
                <div style={{ color: C.seller, fontWeight: "bold", marginBottom: "4px" }}>{(myProfile as any).display_name}</div>
                <div style={{ color: C.secondary, fontSize: "12px", marginBottom: "8px" }}>
                  {((myProfile as any).specialization_categories as string[] ?? []).join(", ").replace(/_/g, " ")}
                </div>
                <div style={{ fontSize: "12px", marginBottom: "8px" }}>
                  <span style={{ color: C.muted }}>Price: </span><span style={{ color: C.warn }}>${(myProfile as any).base_price}</span>
                  {" · "}
                  <span style={{ color: C.muted }}>ETA: </span><span style={{ color: C.primary }}>{(myProfile as any).estimated_minutes}min</span>
                </div>
                <div style={{ fontSize: "12px" }}>
                  <span style={{ color: C.muted }}>Confidence: </span>
                  <ScoreBar score={Number((myProfile as any).confidence_score ?? 0)} width={100} />
                </div>
                <div style={{ marginTop: "8px" }}>
                  <Badge
                    label={(myProfile as any).approval_status ?? "unknown"}
                    color={APPROVAL_COLORS[(myProfile as any).approval_status] ?? C.secondary}
                  />
                </div>
              </>
            ) : (
              <Empty message="No seller profile found for your account." />
            )}
          </div>

          {/* Onboarding review card */}
          <div style={cardStyle}>
            <SectionHeader title="Onboarding Review" color={C.auditor} />
            {myReview ? (
              <>
                <div style={{ marginBottom: "8px" }}>
                  <Badge
                    label={(myReview as any).review_status}
                    color={APPROVAL_COLORS[(myReview as any).review_status] ?? C.secondary}
                  />
                  {(myReview as any).overall_score != null && (
                    <span style={{ color: C.muted, fontSize: "12px", marginLeft: "10px" }}>
                      Score: <span style={{ color: scoreColor((myReview as any).overall_score) }}>
                        {((myReview as any).overall_score * 100).toFixed(0)}%
                      </span>
                    </span>
                  )}
                </div>
                {(myReview as any).dimension_scores && (
                  <DimensionScores scores={(myReview as any).dimension_scores} />
                )}
                {((myReview as any).issues as string[] ?? []).length > 0 && (
                  <div style={{ marginTop: "8px" }}>
                    {((myReview as any).issues as string[]).map((issue: string, i: number) => (
                      <div key={i} style={{ color: C.fail, fontSize: "11px" }}>• {issue}</div>
                    ))}
                  </div>
                )}
                {((myReview as any).recommendations as string[] ?? []).length > 0 && (
                  <div style={{ marginTop: "6px" }}>
                    {((myReview as any).recommendations as string[]).map((rec: string, i: number) => (
                      <div key={i} style={{ color: C.warn, fontSize: "11px" }}>→ {rec}</div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <Empty message="No onboarding review found." />
            )}
          </div>
        </div>
      )}

      {/* ---- MY TASKS ---- */}
      {tab === "my tasks" && isSeller && (
        <div>
          <SectionHeader title="Assigned Tasks" color={C.seller} subtitle="polling every 5s" />
          {myTasks.length === 0 && <Empty message="No tasks assigned yet." />}
          {myTasks.map((t: any) => (
            <TaskRow key={t.id} task={t} href={`/tasks/${t.id}`} />
          ))}
        </div>
      )}

      {/* ---- MARKETPLACE ---- */}
      {tab === "marketplace" && (
        <div>
          <SectionHeader title="Registered Seller Agents" color={C.seller} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "12px" }}>
            {allSellers.map((s: any) => (
              <SellerCard key={s.agent_id} seller={s} isMe={s.user_id === user?.user_id} />
            ))}
          </div>
          {allSellers.length === 0 && <Empty message="No seller agents registered." />}
        </div>
      )}

      {/* ---- EXECUTE (dev tool) ---- */}
      {tab === "execute" && (
        <div style={{ maxWidth: "480px" }}>
          <SectionHeader title="Execute Seller on Task" color={C.seller} subtitle="dev tool" />
          <div style={{ color: C.muted, fontSize: "12px", marginBottom: "10px" }}>
            Manually trigger seller execution. In normal flow this happens after buyer selects a seller.
          </div>
          <input placeholder="Task ID" value={taskId} onChange={(e) => setTaskId(e.target.value)} style={inputStyle} />
          <select value={execSellerId} onChange={(e) => setExecSellerId(e.target.value)} style={inputStyle}>
            <option value="">Select seller…</option>
            {allSellers.map((s: any) => (
              <option key={s.agent_id} value={s.agent_id}>{s.name}</option>
            ))}
          </select>
          <button onClick={handleExecute} disabled={loading || !taskId || !execSellerId} style={btnStyle(C.seller)}>
            {loading ? "Running…" : "Execute →"}
          </button>
          {execResult && (
            <div style={{ marginTop: "12px" }}>
              <Badge label={`status: ${(execResult as any).status}`} color={C.pass} />
              {(execResult as any).benchmark_comparison_id && (
                <div style={{ marginTop: "6px" }}>
                  <a href={`/tasks/${(execResult as any).id}`} style={{ color: C.system, fontSize: "12px" }}>
                    View benchmark comparison →
                  </a>
                </div>
              )}
              <pre style={{ background: C.inset, border: `1px solid ${C.border}`, padding: "10px", borderRadius: "6px", fontSize: "11px", color: C.seller, marginTop: "10px", overflowX: "auto", maxHeight: "300px" }}>
                {JSON.stringify(execResult, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SellerCard({ seller, isMe }: { seller: Record<string, unknown>; isMe?: boolean }) {
  const s = seller as any;
  return (
    <div style={{ ...cardStyle, border: isMe ? `1px solid ${C.seller}` : `1px solid ${C.border}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
        <span style={{ color: C.seller, fontWeight: "bold", fontSize: "13px" }}>{s.name}</span>
        {isMe && <Badge label="you" color={C.seller} />}
      </div>
      <div style={{ color: C.secondary, fontSize: "11px", marginBottom: "6px" }}>
        {(s.specializations as string[] ?? []).join(", ").replace(/_/g, " ")}
      </div>
      <div style={{ display: "flex", gap: "12px", fontSize: "11px", marginBottom: "6px" }}>
        <span><span style={{ color: C.muted }}>$</span><span style={{ color: C.warn }}>{s.base_price}</span></span>
        <span><span style={{ color: C.muted }}>conf: </span><span style={{ color: scoreColor(Number(s.confidence_score)) }}>{(s.confidence_score * 100).toFixed(0)}%</span></span>
        {s.reputation_score > 0 && <span><span style={{ color: C.muted }}>rep: </span><span style={{ color: C.warn }}>{Number(s.reputation_score).toFixed(1)}</span></span>}
      </div>
      <Badge label={s.approval_status ?? "unknown"} color={APPROVAL_COLORS[s.approval_status] ?? C.secondary} />
    </div>
  );
}
