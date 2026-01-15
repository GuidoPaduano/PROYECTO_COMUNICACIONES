/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/agregar-nota/:path*",
        destination: "http://127.0.0.1:8000/agregar-nota/:path*",
      },
    ]
  },
};

export default nextConfig;
