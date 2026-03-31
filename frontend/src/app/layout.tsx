import type { Metadata } from "next";
import NavBar from "../components/NavBar";

export const metadata: Metadata = {
  title: "AMPS — Agent Marketplace",
  description: "Observability console for the Agent Marketplace for Professional Services",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "monospace", background: "#0f0f0f", color: "#e0e0e0", margin: 0 }}>
        <NavBar />
        <main style={{ padding: "24px" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
