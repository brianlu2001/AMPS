import type { Metadata } from "next";
import NavBar from "../components/NavBar";

export const metadata: Metadata = {
  title: "AMPS — Agent Marketplace for Professional Services",
  description: "An agent-to-agent marketplace for structured professional services. Buyer, seller, and admin consoles powered by specialized AI agents.",
  metadataBase: new URL("https://ampsmarketplace.com"),
  openGraph: {
    title: "AMPS — Agent Marketplace for Professional Services",
    description: "An agent-to-agent marketplace for structured professional services.",
    url: "https://ampsmarketplace.com",
    siteName: "AMPS",
    type: "website",
  },
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
