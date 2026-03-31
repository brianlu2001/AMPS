"use client";
/**
 * Audit Console
 *
 * Tabs:
 *   Task Audit     — run or view audit on a completed task (dimension scores, flags, benchmark link)
 *   Seller Reviews — list onboarding reviews + trigger review audit
 *   Benchmark      — full specialist vs. generalist comparison by task ID
 */

import { useState } from "react";
import { auditApi, AuditResult, BenchmarkComparison, SellerOnboardingReview } from "../../lib/api";
import {
  C, SectionHeader, ScoreBar, DimensionScores, Badge,
  TabBar, ErrorBanner, Empty, btnStyle, cardStyle, inputStyle, scoreColor,
  APPROVAL_COLORS,
} from "../../components/ui";

export default function AuditPage() {
  const [tab, setTab] = useState("task audit");

  // Task audit
  const [taskId, setTaskId]         = useState("");
  const [auditResult, setAuditResult] = useState<AuditResult | null>(null);
  const [benchmark, setBenchmark]   = useState<BenchmarkComparison | null>(null);

  // Seller reviews
  const [reviews, setReviews]       = useState<Array<{ review: SellerOnboardingReview; seller_name: string; approval_status: string }>>([]);
  const [reviewFilter, setReviewFilter] = useState("");
  const [sellerId, setSellerId]     = useState("");
  const [sellerReview, setSellerReview] = useState<{ review: SellerOnboardingReview; seller_name: string; approval_status: string } | null>(null);

  // Benchmark
  const [bmTaskId, setBmTaskId]     = useState("");
  const [fullBenchmark, setFullBenchmark] = useState<BenchmarkComparison | null>(null);

  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const runAudit = async () => {
    if (!taskId) return;
    setLoading(true); setError(null);
    try {
      const res = await auditApi.runTaskAudit(taskId);
      setAuditResult(res.audit_result); setBenchmark(res.benchmark_comparison);
    } catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  const fetchAudit = async () => {
    if (!taskId) return;
    setLoading(true); setError(null);
    try {
      const res = await auditApi.getTaskAudit(taskId);
      setAuditResult(res.audit_result); setBenchmark(res.benchmark_comparison);
    } catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  const loadReviews = async () => {
    setLoading(true); setError(null);
    try { setReviews(await auditApi.listSellerReviews(reviewFilter || undefined)); }
    catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  const runSellerAudit = async () => {
    if (!sellerId) return;
    setLoading(true); setError(null);
    try { setSellerReview(await auditApi.runSellerAudit(sellerId)); }
    catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  const loadBenchmark = async () => {
    if (!bmTaskId) return;
    setLoading(true); setError(null);
    try { setFullBenchmark(await auditApi.getBenchmark(bmTaskId)); }
    catch (e) { setError(String(e)); } finally { setLoading(false); }
  };

  return (
    <div style={{ maxWidth: "900px" }}>
      <h2 style={{ color: C.auditor, marginBottom: "8px" }}>Audit Console</h2>
      <ErrorBanner error={error} />

      <TabBar tabs={["task audit", "seller reviews", "benchmark"]} active={tab} onChange={setTab} color={C.auditor} />

      {/* ---- TASK AUDIT ---- */}
      {tab === "task audit" && (
        <div>
          <div style={{ maxWidth: "440px", marginBottom: "20px" }}>
            <SectionHeader title="Task Output Audit" color={C.auditor} />
            <div style={{ color: C.muted, fontSize: "12px", marginBottom: "8px" }}>
              Scores quality, relevance, completeness, and genericity (specificity) of a seller's delivered output.
            </div>
            <input placeholder="Task ID" value={taskId} onChange={(e) => setTaskId(e.target.value)} style={inputStyle} />
            <div style={{ display: "flex", gap: "8px" }}>
              <button onClick={runAudit}   disabled={loading || !taskId} style={btnStyle(C.auditor)}>Run Audit</button>
              <button onClick={fetchAudit} disabled={loading || !taskId} style={{ ...btnStyle("#555") }}>Fetch Existing</button>
            </div>
          </div>
          {auditResult && <AuditResultPanel audit={auditResult} />}
          {benchmark && <BenchmarkPanel benchmark={benchmark} />}
          {!auditResult && !error && <Empty message="Enter a completed task ID to run or fetch its audit." />}
        </div>
      )}

      {/* ---- SELLER REVIEWS ---- */}
      {tab === "seller reviews" && (
        <div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", marginBottom: "24px" }}>
            <div>
              <SectionHeader title="Audit Seller Profile" color={C.auditor} />
              <div style={{ color: C.muted, fontSize: "12px", marginBottom: "8px" }}>
                Scores completeness, expertise credibility, pricing clarity, category fit, and capacity realism.
              </div>
              <input placeholder="Seller ID" value={sellerId} onChange={(e) => setSellerId(e.target.value)} style={inputStyle} />
              <button onClick={runSellerAudit} disabled={loading || !sellerId} style={btnStyle(C.auditor)}>
                Run Onboarding Audit
              </button>
              {sellerReview && <SellerReviewPanel item={sellerReview} />}
            </div>
            <div>
              <SectionHeader title="Browse Reviews" color={C.auditor} />
              <select value={reviewFilter} onChange={(e) => setReviewFilter(e.target.value)} style={inputStyle}>
                <option value="">All statuses</option>
                {["queued", "needs_review", "in_review", "approved", "rejected"].map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <button onClick={loadReviews} disabled={loading} style={btnStyle(C.auditor)}>Load Reviews</button>
            </div>
          </div>
          {reviews.length > 0 && (
            <>
              <SectionHeader title={`Reviews (${reviews.length})`} color={C.auditor} />
              {reviews.map((item) => <SellerReviewPanel key={item.review.id} item={item} compact />)}
            </>
          )}
        </div>
      )}

      {/* ---- BENCHMARK ---- */}
      {tab === "benchmark" && (
        <div>
          <div style={{ maxWidth: "440px", marginBottom: "20px" }}>
            <SectionHeader title="Specialist vs. Generalist Benchmark" color={C.auditor} />
            <input placeholder="Task ID" value={bmTaskId} onChange={(e) => setBmTaskId(e.target.value)} style={inputStyle} />
            <button onClick={loadBenchmark} disabled={loading || !bmTaskId} style={btnStyle(C.auditor)}>Load Benchmark</button>
          </div>
          {fullBenchmark ? <BenchmarkPanel benchmark={fullBenchmark} full /> : <Empty message="Enter a task ID with a completed benchmark comparison." />}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function AuditResultPanel({ audit: a }: { audit: AuditResult }) {
  const score = a.composite_score ?? a.quality_score;
  return (
    <div style={{ ...cardStyle, marginBottom: "16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
          <span style={{ color: scoreColor(score), fontSize: "28px", fontWeight: "bold" }}>{(score * 100).toFixed(1)}%</span>
          {a.passed ? <Badge label="PASSED" color={C.pass} /> : <Badge label="FAILED" color={C.fail} />}
          {a.admin_override && <Badge label="ADMIN OVERRIDE" color={C.admin} />}
        </div>
        <div style={{ fontSize: "11px", color: C.muted, textAlign: "right" }}>
          {a.scoring_method}<br />{new Date(a.audited_at).toLocaleString()}
        </div>
      </div>

      {a.dimension_scores && Object.keys(a.dimension_scores).length > 0 && (
        <div style={{ marginBottom: "12px" }}>
          <div style={{ color: C.muted, fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "6px" }}>Dimensions</div>
          <DimensionScores scores={a.dimension_scores} />
        </div>
      )}

      <div style={{ color: C.secondary, fontSize: "12px", lineHeight: "1.5", marginBottom: "8px" }}>{a.reasoning}</div>

      {a.flags.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "5px", marginBottom: "6px" }}>
          {a.flags.map((f) => <Badge key={f} label={f} color={C.fail} />)}
        </div>
      )}
      {a.recommendations && a.recommendations.length > 0 && (
        <div>{a.recommendations.map((r, i) => <div key={i} style={{ color: C.warn, fontSize: "11px" }}>→ {r}</div>)}</div>
      )}
      {a.has_benchmark && a.benchmark_winner && (
        <div style={{ marginTop: "10px", padding: "8px", background: "#111", borderRadius: "4px", fontSize: "12px" }}>
          <span style={{ color: C.muted }}>Benchmark: </span>
          <span style={{ color: a.benchmark_winner === "seller" ? C.seller : C.system, fontWeight: "bold" }}>{a.benchmark_winner.toUpperCase()} wins</span>
          {a.benchmark_delta != null && (
            <span style={{ marginLeft: "8px", color: a.benchmark_delta > 0 ? C.pass : C.fail }}>
              {a.benchmark_delta > 0 ? "+" : ""}{(a.benchmark_delta * 100).toFixed(1)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function BenchmarkPanel({ benchmark: b, full }: { benchmark: BenchmarkComparison; full?: boolean }) {
  return (
    <div style={{ ...cardStyle, marginBottom: "16px" }}>
      <div style={{ color: C.auditor, fontSize: "12px", fontWeight: "bold", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "12px" }}>
        Benchmark Comparison
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "12px" }}>
        <div>
          <div style={{ color: C.seller, fontSize: "11px", marginBottom: "4px" }}>Specialist {b.seller_display_name ? `— ${b.seller_display_name}` : ""}</div>
          <div style={{ color: scoreColor(b.seller_score), fontSize: "26px", fontWeight: "bold" }}>{(b.seller_score * 100).toFixed(1)}%</div>
          <div style={{ color: C.muted, fontSize: "11px" }}>${b.specialist_cost.toFixed(2)} · {b.specialist_eta_minutes}min</div>
        </div>
        <div>
          <div style={{ color: C.system, fontSize: "11px", marginBottom: "4px" }}>Generalist {b.generalist_model ? `— ${b.generalist_model}` : ""}</div>
          <div style={{ color: scoreColor(b.generalist_score), fontSize: "26px", fontWeight: "bold" }}>{(b.generalist_score * 100).toFixed(1)}%</div>
          <div style={{ color: C.muted, fontSize: "11px" }}>${b.generalist_cost.toFixed(2)} · {b.generalist_eta_minutes}min</div>
        </div>
      </div>
      <div style={{ display: "flex", gap: "12px", alignItems: "center", marginBottom: "10px" }}>
        <Badge label={b.winner.toUpperCase()} color={b.winner === "seller" ? C.seller : b.winner === "generalist" ? C.system : C.auditor} />
        <span style={{ fontSize: "12px", color: b.delta > 0 ? C.pass : C.fail }}>Δ {b.delta > 0 ? "+" : ""}{(b.delta * 100).toFixed(1)}%</span>
        <Badge label={b.recommendation.replace(/_/g, " ")} color={b.recommendation.includes("specialist") ? C.seller : C.system} />
      </div>
      {full && b.seller_dimension_scores && Object.keys(b.seller_dimension_scores).length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "8px" }}>
          <div>
            <div style={{ color: C.seller, fontSize: "10px", marginBottom: "4px" }}>Specialist Dimensions</div>
            <DimensionScores scores={b.seller_dimension_scores} />
          </div>
          <div>
            <div style={{ color: C.system, fontSize: "10px", marginBottom: "4px" }}>Generalist Dimensions</div>
            <DimensionScores scores={b.generalist_dimension_scores} />
          </div>
        </div>
      )}
      {b.summary && <div style={{ color: C.secondary, fontSize: "11px", lineHeight: "1.4" }}>{b.summary}</div>}
    </div>
  );
}

function SellerReviewPanel({ item, compact }: { item: { review: SellerOnboardingReview; seller_name: string; approval_status: string }; compact?: boolean }) {
  const { review: r, seller_name } = item;
  const score = r.overall_score ?? 0;
  return (
    <div style={{ ...cardStyle, marginBottom: "8px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span style={{ color: C.seller, fontWeight: "bold", fontSize: "13px" }}>{seller_name}</span>
          <Badge label={r.review_status} color={APPROVAL_COLORS[r.review_status] ?? C.secondary} />
        </div>
        <span style={{ color: scoreColor(score), fontSize: "13px" }}>{(score * 100).toFixed(0)}%</span>
      </div>
      {!compact && r.dimension_scores && Object.keys(r.dimension_scores).length > 0 && (
        <div style={{ marginBottom: "8px" }}><DimensionScores scores={r.dimension_scores} /></div>
      )}
      {r.issues.length > 0 && (
        <div>{r.issues.map((issue, i) => <div key={i} style={{ color: C.fail, fontSize: "11px" }}>• {issue}</div>)}</div>
      )}
      {!compact && r.reasoning && (
        <div style={{ color: C.secondary, fontSize: "11px", marginTop: "6px", lineHeight: "1.4" }}>{r.reasoning}</div>
      )}
    </div>
  );
}
