import type { NextConfig } from "next";

if (process.env.VERCEL === "1" && !process.env.NEXT_PUBLIC_API_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL must point to the deployed FastAPI service before a Vercel build.",
  );
}

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
