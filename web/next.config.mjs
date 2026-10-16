/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: {
    // Lint is run explicitly in CI; do not fail the production build on it.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
