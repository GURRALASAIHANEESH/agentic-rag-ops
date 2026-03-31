/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    remotePatterns: [],
  },
  async headers() {
    return [];
  },
  async rewrites() {
    const backend = process.env.INTERNAL_API_URL ?? "http://localhost:8000";
    return [
      {
        source: '/api/:path*',
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;