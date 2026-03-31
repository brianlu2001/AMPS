/**
 * AMPS landing page.
 * Provides role-based navigation to the four console views.
 */
export default function Home() {
  return (
    <div>
      <h1 style={{ color: "#7dd3fc", marginBottom: "8px" }}>
        AMPS — Agent Marketplace for Professional Services
      </h1>
      <p style={{ color: "#888", marginBottom: "32px" }}>
        MVP observability console. Select a view to begin.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "16px", maxWidth: "600px" }}>
        <ConsoleCard
          href="/buyer"
          title="Buyer Console"
          description="Onboard, submit tasks, track results"
          color="#a3e635"
        />
        <ConsoleCard
          href="/seller"
          title="Seller Console"
          description="View registered seller agents and capabilities"
          color="#f9a8d4"
        />
        <ConsoleCard
          href="/audit"
          title="Audit Console"
          description="Review audit results and benchmark comparisons"
          color="#fcd34d"
        />
        <ConsoleCard
          href="/admin"
          title="Admin Console"
          description="Full activity log, seller approvals, audit overrides"
          color="#c084fc"
        />
      </div>
    </div>
  );
}

function ConsoleCard({
  href,
  title,
  description,
  color,
}: {
  href: string;
  title: string;
  description: string;
  color: string;
}) {
  return (
    <a
      href={href}
      style={{
        display: "block",
        padding: "20px",
        border: `1px solid ${color}33`,
        borderRadius: "8px",
        textDecoration: "none",
        background: "#1a1a1a",
        transition: "border-color 0.2s",
      }}
    >
      <div style={{ color, fontWeight: "bold", marginBottom: "6px" }}>{title}</div>
      <div style={{ color: "#888", fontSize: "13px" }}>{description}</div>
    </a>
  );
}
