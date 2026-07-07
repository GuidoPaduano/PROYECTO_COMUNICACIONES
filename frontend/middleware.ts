import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

export function middleware(request: NextRequest) {
  // Railway terminates TLS at the edge and forwards X-Forwarded-Proto to the app.
  // Redirect HTTP → HTTPS so browsers always use a secure connection.
  const proto = request.headers.get("x-forwarded-proto")
  if (proto === "http") {
    const host = request.headers.get("host") || ""
    const url = `https://${host}${request.nextUrl.pathname}${request.nextUrl.search}`
    return NextResponse.redirect(url, { status: 301 })
  }
  return NextResponse.next()
}

export const config = {
  matcher: [
    // Run on all routes except Next.js internals and static files
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
}
