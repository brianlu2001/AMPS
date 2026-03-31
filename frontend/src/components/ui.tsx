"use client";
/**
 * Shared UI primitives for AMPS observability console.
 *
 * Design system:
 *   Background: #0f0f0f (page) / #1a1a1a (cards) / #111 (inset)
 *   Text:       #e0e0e0 (primary) / #888 (secondary) / #555 (muted)
 *   Borders:    #222 (standard) / #333 (inputs)
 *   Role colors: buyer=#a3e635 seller=#f9a8d4 auditor=#fcd34d admin=#c084fc system=#7dd3fc
 *   Semantic:   pass=#a3e635 warn=#fcd34d fail=#f87171
 */

import React from "react";

// ---------------------------------------------------------------------------
// Colours (re-exported so pages don't hardcode them)
// ---------------------------------------------------------------------------

export const C = {
  buyer:       "#a3e635",
  seller:      "#f9a8d4",
  auditor:     "#fcd34d",
  admin:       "#c084fc",
  system:      "#7dd3fc",
  pass:        "#a3e635",
  warn:        "#fcd34d",
  fail:        "#f87171",
  muted:       "#555",
  secondary:   "#888",
  primary:     "#e0e0e0",
  card:        "#1a1a1a",
  inset:       "#111",
  border:      "#222",
  inputBorder: "#333",
} as const;

export const ROLE_COLORS: Record<string, string> = {
  buyer: C.buyer, seller: C.seller, auditor: C.auditor,
  admin: C.admin, generalist: C.system, system: C.system,
};

export const STATUS_COLORS: Record<string, string> = {
  pending: C.secondary, assigned: C.system, in_progress: C.warn,
  completed: C.pass, failed: C.fail, disputed: C.seller,
};

export const AUDIT_COLORS: Record<string, string> = {
  not_started: C.muted, in_review: C.warn,
  passed: C.pass, failed: C.fail, overridden: C.admin,
};

export const APPROVAL_COLORS: Record<string, string> = {
  pending: C.secondary, needs_review: C.warn,
  approved: C.pass, rejected: C.fail, suspended: C.fail,
};

// ---------------------------------------------------------------------------
// score → colour helper
// ---------------------------------------------------------------------------

export function scoreColor(s: number): string {
  if (s >= 0.80) return C.pass;
  if (s >= 0.60) return C.warn;
  return C.fail;
}

// ---------------------------------------------------------------------------
// Base styles
// ---------------------------------------------------------------------------

export const inputStyle: React.CSSProperties = {
  width: "100%", background: C.card, border: `1px solid ${C.inputBorder}`,
  color: C.primary, padding: "8px 10px", borderRadius: "4px",
  marginBottom: "8px", fontFamily: "monospace", fontSize: "13px",
  boxSizing: "border-box",
};

export const cardStyle: React.CSSProperties = {
  background: C.card, border: `1px solid ${C.border}`,
  borderRadius: "6px", padding: "14px",
};

export function btnStyle(color: string): React.CSSProperties {
  return {
    background: "transparent", border: `1px solid ${color}`,
    color, padding: "7px 16px", cursor: "pointer",
    borderRadius: "4px", fontFamily: "monospace", fontSize: "13px",
  };
}

// ---------------------------------------------------------------------------
// StatCard
// ---------------------------------------------------------------------------

export function StatCard({
  label, value, sub, color = C.system,
}: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div style={{ ...cardStyle, minWidth: "110px" }}>
      <div style={{ color: C.secondary, fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: "4px" }}>{label}</div>
      <div style={{ color, fontSize: "22px", fontWeight: "bold", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ color: C.muted, fontSize: "11px", marginTop: "4px" }}>{sub}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ScoreBar  — horizontal fill bar for 0–1 scores
// ---------------------------------------------------------------------------

export function ScoreBar({
  score, label, width = 200,
}: { score: number; label?: string; width?: number }) {
  const pct = Math.round(score * 100);
  const color = scoreColor(score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      {label && <span style={{ color: C.secondary, fontSize: "11px", width: "80px", flexShrink: 0 }}>{label}</span>}
      <div style={{ width, height: "6px", background: "#222", borderRadius: "3px", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: "3px" }} />
      </div>
      <span style={{ color, fontSize: "11px", width: "34px" }}>{pct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

export function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      display: "inline-block", padding: "2px 8px", borderRadius: "10px",
      border: `1px solid ${color}44`, color, fontSize: "11px", fontFamily: "monospace",
    }}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// SectionHeader
// ---------------------------------------------------------------------------

export function SectionHeader({
  title, color = C.system, subtitle, actions,
}: { title: string; color?: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "12px" }}>
      <div>
        <span style={{ color, fontSize: "12px", fontWeight: "bold", textTransform: "uppercase", letterSpacing: "1px" }}>{title}</span>
        {subtitle && <span style={{ color: C.muted, fontSize: "11px", marginLeft: "8px" }}>{subtitle}</span>}
      </div>
      {actions && <div>{actions}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LogFeed — real-time activity log display
// ---------------------------------------------------------------------------

export interface LogEntry {
  id: string;
  event_type: string;
  actor_role: string | null;
  message: string;
  created_at: string;
}

export function LogFeed({ logs, maxHeight = 320 }: { logs: LogEntry[]; maxHeight?: number }) {
  return (
    <div style={{
      background: C.inset, border: `1px solid ${C.border}`, borderRadius: "6px",
      padding: "10px 12px", maxHeight, overflowY: "auto",
      fontFamily: "monospace", fontSize: "11px",
    }}>
      {logs.length === 0 && <span style={{ color: C.muted }}>No events yet.</span>}
      {logs.map((log) => (
        <div key={log.id} style={{ display: "flex", gap: "8px", marginBottom: "5px", lineHeight: "1.4" }}>
          <span style={{ color: C.muted, flexShrink: 0, width: "60px" }}>
            {new Date(log.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </span>
          <span style={{ color: C.system, flexShrink: 0 }}>[{log.event_type}]</span>
          <span style={{ color: ROLE_COLORS[log.actor_role ?? "system"] ?? C.secondary, flexShrink: 0 }}>
            [{log.actor_role ?? "system"}]
          </span>
          <span style={{ color: C.primary }}>{log.message}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TaskRow — compact single-line task summary
// ---------------------------------------------------------------------------

export function TaskRow({ task, href }: { task: { id: string; title: string; category: string; status: string; audit_status: string }; href?: string }) {
  const content = (
    <div style={{ display: "flex", alignItems: "center", gap: "12px", padding: "10px 12px", background: C.card, border: `1px solid ${C.border}`, borderRadius: "5px", marginBottom: "6px" }}>
      <span style={{ color: C.primary, flex: 1, fontSize: "13px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{task.title}</span>
      <span style={{ color: C.muted, fontSize: "11px", flexShrink: 0 }}>{task.category.replace(/_/g, " ")}</span>
      <Badge label={task.status}       color={STATUS_COLORS[task.status] ?? C.secondary} />
      <Badge label={task.audit_status} color={AUDIT_COLORS[task.audit_status] ?? C.secondary} />
      <span style={{ color: C.muted, fontSize: "10px", flexShrink: 0 }}>{task.id.slice(0, 8)}</span>
    </div>
  );
  if (href) return <a href={href} style={{ textDecoration: "none" }}>{content}</a>;
  return content;
}

// ---------------------------------------------------------------------------
// QuoteCard
// ---------------------------------------------------------------------------

export function QuoteCard({
  quote, onSelect, isSelected,
}: { quote: import("../lib/api").Quote; onSelect?: () => void; isSelected?: boolean }) {
  return (
    <div style={{
      ...cardStyle,
      border: isSelected ? `1px solid ${C.buyer}` : `1px solid ${C.border}`,
      marginBottom: "8px",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
        <div>
          <span style={{ color: C.seller, fontWeight: "bold", fontSize: "13px" }}>
            {quote.seller_display_name ?? quote.seller_id.slice(0, 8)}
          </span>
          {isSelected && <Badge label="SELECTED" color={C.buyer} />}
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ color: C.warn, fontSize: "18px", fontWeight: "bold" }}>${quote.proposed_price.toFixed(2)}</div>
          <div style={{ color: C.secondary, fontSize: "11px" }}>{quote.estimated_minutes}min ETA</div>
        </div>
      </div>

      {/* Match score bar */}
      <div style={{ marginBottom: "8px" }}>
        <ScoreBar score={quote.match_score} label="Match" width={160} />
      </div>

      {quote.fit_explanation && (
        <div style={{ color: C.secondary, fontSize: "11px", marginBottom: "8px", lineHeight: "1.4" }}>
          {quote.fit_explanation}
        </div>
      )}

      {/* Score breakdown pills */}
      {Object.keys(quote.score_breakdown).length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "8px" }}>
          {Object.entries(quote.score_breakdown).map(([k, v]) => (
            <span key={k} style={{ fontSize: "10px", color: C.muted, background: "#111", padding: "2px 6px", borderRadius: "3px" }}>
              {k.replace(/_/g, " ")}: {(v * 100).toFixed(0)}%
            </span>
          ))}
        </div>
      )}

      {onSelect && !isSelected && (
        <button onClick={onSelect} style={{ ...btnStyle(C.buyer), fontSize: "12px", padding: "5px 14px" }}>
          Select this seller
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DimensionScores — shows audit dimension bars
// ---------------------------------------------------------------------------

export function DimensionScores({ scores }: { scores: Record<string, number> }) {
  if (!scores || Object.keys(scores).length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
      {Object.entries(scores).map(([dim, val]) => (
        <ScoreBar key={dim} score={val} label={dim} width={150} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

export function Empty({ message }: { message: string }) {
  return <div style={{ color: C.muted, fontSize: "13px", padding: "16px 0" }}>{message}</div>;
}

// ---------------------------------------------------------------------------
// Error banner
// ---------------------------------------------------------------------------

export function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div style={{ color: C.fail, background: "#2e1a1a", border: `1px solid ${C.fail}44`, borderRadius: "4px", padding: "8px 12px", marginBottom: "12px", fontSize: "12px" }}>
      {error}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TabBar — simple tab switcher
// ---------------------------------------------------------------------------

export function TabBar({
  tabs, active, onChange, color = C.system,
}: { tabs: string[]; active: string; onChange: (t: string) => void; color?: string }) {
  return (
    <div style={{ display: "flex", gap: "0", marginBottom: "20px", borderBottom: `1px solid ${C.border}` }}>
      {tabs.map((t) => (
        <button key={t} onClick={() => onChange(t)} style={{
          background: "transparent", border: "none",
          borderBottom: active === t ? `2px solid ${color}` : "2px solid transparent",
          color: active === t ? color : C.secondary,
          padding: "8px 16px", cursor: "pointer",
          fontFamily: "monospace", fontSize: "12px",
          textTransform: "uppercase", letterSpacing: "0.5px",
        }}>
          {t}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------

export function Spinner() {
  return <span style={{ color: C.muted, fontSize: "13px" }}>Loading…</span>;
}
