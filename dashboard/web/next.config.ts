import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(__dirname),
  },
  async rewrites() {
    return [
      {
        source: "/_dashboard_api/:path*",
        destination: "http://127.0.0.1:8002/:path*",
      },
    ];
  },
};

export default nextConfig;
