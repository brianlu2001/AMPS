"use client";

/**
 * Login page.
 *
 * Accepts email + password, calls POST /auth/login, stores the JWT token,
 * then redirects to the role-appropriate console.
 *
 * Demo accounts (seeded at startup — see backend/seed.py):
 *   buyer@amps.dev      / buyer123   → /buyer
 *   seller1@amps.dev    / seller123  → /seller
 *   seller2@amps.dev    / seller123  → /seller
 *   admin@amps.dev      / admin123   → /admin
 *   auditor@amps.dev    / audit123   → /audit
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "../../lib/api";

const ROLE_REDIRECTS: Record<string, string> = {
  buyer:      "/buyer",
  seller:     "/seller",
  admin:      "/admin",
  auditor:    "/audit",
  generalist: "/seller",
};

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authApi.login(email, password);
      // Redirect to role-appropriate console
      const dest = ROLE_REDIRECTS[res.role] ?? "/";
      router.push(dest);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "400px", margin: "80px auto" }}>
      <h2 style={{ color: "#7dd3fc", marginBottom: "24px" }}>Sign In to AMPS</h2>

      {error && (
        <div style={{ color: "#f87171", marginBottom: "12px", fontSize: "13px" }}>
          {error}
        </div>
      )}

      <input
        type="email"
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        style={inputStyle}
        onKeyDown={(e) => e.key === "Enter" && handleLogin()}
      />
      <input
        type="password"
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        style={inputStyle}
        onKeyDown={(e) => e.key === "Enter" && handleLogin()}
      />

      <button
        onClick={handleLogin}
        disabled={loading || !email || !password}
        style={{
          width: "100%",
          background: "transparent",
          border: "1px solid #7dd3fc",
          color: "#7dd3fc",
          padding: "10px",
          cursor: "pointer",
          borderRadius: "4px",
          fontFamily: "monospace",
          fontSize: "14px",
          marginBottom: "24px",
        }}
      >
        {loading ? "Signing in..." : "Sign In"}
      </button>

      {/* Demo credentials hint */}
      <div style={{
        background: "#111",
        border: "1px solid #222",
        borderRadius: "6px",
        padding: "12px",
        fontSize: "11px",
        color: "#555",
      }}>
        <div style={{ color: "#444", marginBottom: "6px" }}>Demo accounts:</div>
        {[
          ["buyer@amps.dev",      "buyer123",  "buyer"],
          ["seller1@amps.dev",    "seller123", "seller"],
          ["seller2@amps.dev",    "seller123", "seller"],
          ["auditor@amps.dev",    "audit123",  "auditor"],
          ["admin@amps.dev",      "admin123",  "admin"],
        ].map(([em, pw, role]) => (
          <div
            key={em}
            style={{ marginBottom: "3px", cursor: "pointer" }}
            onClick={() => { setEmail(em); setPassword(pw); }}
          >
            <span style={{ color: "#666" }}>{em}</span>
            <span style={{ color: "#444" }}> / {pw}</span>
            <span style={{ color: roleColor(role), marginLeft: "8px" }}>[{role}]</span>
          </div>
        ))}
        <div style={{ marginTop: "6px", color: "#333" }}>Click a row to fill credentials.</div>
      </div>
    </div>
  );
}

function roleColor(role: string) {
  const colors: Record<string, string> = {
    buyer: "#a3e635", seller: "#f9a8d4", admin: "#c084fc", auditor: "#fcd34d",
  };
  return colors[role] ?? "#888";
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "#1a1a1a",
  border: "1px solid #333",
  color: "#e0e0e0",
  padding: "10px",
  borderRadius: "4px",
  marginBottom: "8px",
  fontFamily: "monospace",
  fontSize: "13px",
  boxSizing: "border-box",
};
