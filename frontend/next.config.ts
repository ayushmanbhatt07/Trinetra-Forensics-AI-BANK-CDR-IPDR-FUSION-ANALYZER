import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.APP_BACKEND_URL ?? "http://localhost:10000"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
