/** @type {import('next').NextConfig} */
const nextConfig = {
  // The device posts raw audio; keep responses uncached by default.
  async headers() {
    return [
      {
        source: "/api/:path*",
        headers: [{ key: "Cache-Control", value: "no-store" }],
      },
    ];
  },
};

export default nextConfig;
