"use client";

/**
 * Navigation bar.
 *
 * Shows role-appropriate nav links and the current user's identity.
 * Reads from localStorage session — client-side only.
 *
 * Role visibility:
 *   buyer    → Buyer link visible
 *   seller   → Seller link visible
 *   auditor  → Audit link visible
 *   admin    → all links visible
 *   (not logged in) → Login link only
 */

import { useEffect, useState } from "react";
import { session, SessionUser, authApi } from "../lib/api";

const ROLE_COLORS: Record<string, string> = {
  buyer:      "#a3e635",
  seller:     "#f9a8d4",
  auditor:    "#fcd34d",
  generalist: "#7dd3fc",
  admin:      "#c084fc",
};

export default function NavBar() {
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    setUser(session.getUser());
  }, []);

  const handleLogout = () => {
    authApi.logout();
    setUser(null);
    window.location.href = "/login";
  };

  const role = user?.role ?? null;
  const isAdmin = role === "admin";

  return (
    <nav style={{
      padding: "12px 24px",
      borderBottom: "1px solid #222",
      display: "flex",
      gap: "20px",
      alignItems: "center",
    }}>
      <a href="/" style={{ color: "#7dd3fc", textDecoration: "none", fontWeight: "bold", marginRight: "8px" }}>
        AMPS
      </a>

      {/* Role-gated nav links */}
      {(role === "buyer" || isAdmin) && (
        <a href="/buyer" style={{ color: "#a3e635", textDecoration: "none" }}>Buyer</a>
      )}
      {(role === "seller" || isAdmin) && (
        <a href="/seller" style={{ color: "#f9a8d4", textDecoration: "none" }}>Seller</a>
      )}
      {(role === "auditor" || isAdmin) && (
        <a href="/audit" style={{ color: "#fcd34d", textDecoration: "none" }}>Audit</a>
      )}
      {isAdmin && (
        <a href="/admin" style={{ color: "#c084fc", textDecoration: "none" }}>Admin</a>
      )}

      {/* Spacer */}
      <span style={{ flex: 1 }} />

      {/* Identity display */}
      {user ? (
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <span style={{ fontSize: "12px", color: "#555" }}>{user.email}</span>
          <span style={{
            fontSize: "11px",
            color: ROLE_COLORS[role ?? ""] ?? "#888",
            border: `1px solid ${ROLE_COLORS[role ?? ""] ?? "#333"}33`,
            borderRadius: "4px",
            padding: "2px 8px",
          }}>
            {role}
          </span>
          <button
            onClick={handleLogout}
            style={{
              background: "transparent",
              border: "1px solid #333",
              color: "#555",
              padding: "4px 10px",
              cursor: "pointer",
              borderRadius: "4px",
              fontSize: "12px",
              fontFamily: "monospace",
            }}
          >
            Sign out
          </button>
        </div>
      ) : (
        <a href="/login" style={{ color: "#7dd3fc", textDecoration: "none", fontSize: "13px" }}>
          Sign in
        </a>
      )}
    </nav>
  );
}
