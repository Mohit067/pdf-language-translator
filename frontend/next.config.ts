import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    // Default proxy timeout is 30s; allow slow uploads of large documents through the /api rewrite
    proxyTimeout: 300_000,
    // The /api rewrite truncates request bodies above 10 MB by default. Keep this ceiling high:
    // the real upload limit is enforced by the backend (MAX_UPLOAD_MB), so that is the only setting to change.
    proxyClientMaxBodySize: "1gb",
  },
  // Rewrites are resolved at build time: Docker builds must set BACKEND_INTERNAL_URL
  async rewrites() {
    const backendUrl =
      process.env.BACKEND_INTERNAL_URL ||
      (process.env.NODE_ENV === "production" ? "http://backend:8000" : "http://127.0.0.1:8000");
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
