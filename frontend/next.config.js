/** @type {import('next').NextConfig} */
const nextConfig = {
  /*
   * AMPS — Next.js configuration for Vercel deployment.
   *
   * Backend URL:
   *   Set NEXT_PUBLIC_API_URL in Vercel project settings → Environment Variables.
   *   The frontend reads this at runtime via process.env.NEXT_PUBLIC_API_URL.
   *   Fallback (local dev): http://localhost:8000
   *
   * Images:
   *   AMPS uses no <Image /> components — all UI is text/CSS only.
   *   remotePatterns is left empty; add entries here if images are added later.
   *
   * Trailing slashes:
   *   Disabled (Next.js default) — keeps URL clean for the API route proxying.
   */

  // Expose the backend URL to the browser bundle.
  // NEXT_PUBLIC_* vars are inlined at build time, so the value set in
  // Vercel's environment variables UI will be baked into the deployment.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },

  // Disable the built-in image optimisation — AMPS uses no <Image /> components
  images: {
    unoptimized: true,
  },

  // Silence the "Missing eslint configuration" warning on Vercel builds.
  // AMPS does not use eslint — add eslint config and remove this to enable.
  eslint: {
    ignoreDuringBuilds: true,
  },

  // Silence TypeScript build errors that Vercel treats as blocking.
  // The LSP errors in the codebase are IDE environment issues (fastapi not installed
  // in the IDE's Python interpreter), not real TS errors in the Next.js app.
  // Remove this once any outstanding TS errors in the frontend are resolved.
  typescript: {
    ignoreBuildErrors: false,
  },
};

module.exports = nextConfig;
