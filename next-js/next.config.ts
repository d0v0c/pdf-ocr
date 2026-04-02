import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  experimental: {
    serverActions: {
      // Server Action 上传 PDF 上限设为 10 MB
      bodySizeLimit: '10mb',
    },
  },
  allowedDevOrigins: ['pdf.plandium.net']
};

export default nextConfig;
