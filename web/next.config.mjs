/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Gateway base URL for API calls from the console. Every page reads
  // process.env.NEXT_PUBLIC_GATEWAY_URL (client-side fetch/EventSource
  // calls need the NEXT_PUBLIC_ prefix to be inlined into the browser
  // bundle) — this must be that exact name, not a bare GATEWAY_URL.
  env: {
    NEXT_PUBLIC_GATEWAY_URL: process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8080",
  },
};

export default nextConfig;
