/** @type {import('next').NextConfig} */
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api";
const normalizedApiBase = apiBase.replace(/\/+$/g, "");
const backendOrigin = normalizedApiBase.replace(/\/api$/i, "");

const nextConfig = {
  outputFileTracingRoot: __dirname,
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
      {
        source: "/agregar-nota/:path*",
        destination: `${backendOrigin}/agregar-nota/:path*`,
      },
    ];
  },
};

export default nextConfig;
