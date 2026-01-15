/** @type {import('next').NextConfig} */
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api";
const backendOrigin = apiBase.replace(/\/+$/g, "").replace(/\/api$/i, "");

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/agregar-nota/:path*",
        destination: `${backendOrigin}/agregar-nota/:path*`,
      },
    ]
  },
};

export default nextConfig;
