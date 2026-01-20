/** @type {import('next').NextConfig} */
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api";
const backendOrigin = apiBase.replace(/\/+$/g, "").replace(/\/api$/i, "");

const nextConfig = {
  outputFileTracingRoot: __dirname,
  reactStrictMode: true,
  swcMinify: true,
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
