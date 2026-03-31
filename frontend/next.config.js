/** @type {import('next').NextConfig} */
const nextConfig = {
  // NEXT_PUBLIC_API_URL is read directly from the environment at build time.
  // Set it in Vercel: Project → Settings → Environment Variables.
  // Local dev fallback is handled in src/lib/api.ts:
  //   const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

  // No <Image /> components used — disable optimisation to avoid config warnings.
  images: {
    unoptimized: true,
  },

  // No eslint config in this repo — skip linting during build.
  eslint: {
    ignoreDuringBuilds: true,
  },

  // TypeScript is clean (0 errors). Keep strict checking enabled.
  typescript: {
    ignoreBuildErrors: false,
  },
};

module.exports = nextConfig;
