import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  experimental: {
    serverActions: {
      // Server Action 上传 PDF 上限设为 17 MB（要比前端略大一点）
      bodySizeLimit: '17mb',
    },
  },
  allowedDevOrigins: [process.env.NEXT_DEV_ORIGIN!]
};

export default nextConfig;
