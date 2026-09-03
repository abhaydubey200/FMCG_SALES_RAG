/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  images: {
    unoptimized: true,
  },
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://api:8000";
    return [
      {
        source: "/api/ai/query/stream",
        destination: `${apiUrl}/api/ai/query/stream`,
        // Streaming endpoints need special handling — no body rewriting
      },
      {
        source: "/query/stream",
        destination: `${apiUrl}/query/stream`,
      },
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${apiUrl}/health`,
      },
      {
        source: "/query",
        destination: `${apiUrl}/query`,
      },
      {
        source: "/documents/:path*",
        destination: `${apiUrl}/documents/:path*`,
      },
      {
        source: "/documents",
        destination: `${apiUrl}/documents`,
      },
      {
        source: "/dashboard",
        destination: `${apiUrl}/dashboard`,
      },
    ];
  },
  // Increase server timeout for API proxy calls
  experimental: {
    serverActions: {
      bodySizeLimit: "50mb",
    },
  },
  // Disable response buffering for streaming
  async headers() {
    return [
      {
        source: "/api/ai/query/stream",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store" },
          { key: "X-Accel-Buffering", value: "no" },
        ],
      },
      {
        source: "/query/stream",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store" },
          { key: "X-Accel-Buffering", value: "no" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
