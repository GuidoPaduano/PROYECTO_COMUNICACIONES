import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

export function middleware(request: NextRequest) {
  // Railway only injects X-Forwarded-Proto: https for TLS connections; HTTP
  // connections arrive without the header. Redirect to HTTPS whenever the
  // header is absent or not "https", skipping localhost for local development.
  const host = request.headers.get("host") || ""
  const isLocalhost = /^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host)
  const proto = (request.headers.get("x-forwarded-proto") || "").split(",")[0].trim().toLowerCase()
  if (!isLocalhost && proto !== "https") {
    const url = `https://${host}${request.nextUrl.pathname}${request.nextUrl.search}`
    return NextResponse.redirect(url, { status: 301 })
  }
  return NextResponse.next()
}

export const config = {
  matcher: [
    // Run on all routes except Next.js internals, static files, and API proxy routes
    "/((?!_next/static|_next/image|favicon.ico|api/).*)",
  ],
}
