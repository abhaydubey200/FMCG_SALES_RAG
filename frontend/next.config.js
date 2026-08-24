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
        source: "/dashboard",
        destination: `${apiUrl}/dashboard`,
      },
    ];
  },
};

module.exports = nextConfig;
