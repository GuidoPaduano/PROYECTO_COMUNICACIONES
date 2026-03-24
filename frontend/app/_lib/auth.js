"use client"

import { useEffect, useState } from "react"

export const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE_URL)
    ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/+$/,"")
    : "http://localhost:8000/api"

const API_BASE_HAS_API = /\/api\/?$/.test(String(API_BASE))
const AUTH_MARKER_KEY = "auth_session"

function sessionStore() {
  try {
    if (typeof window !== "undefined" && window.sessionStorage) return window.sessionStorage
  } catch {}
  return null
}

function hasAuthMarker() {
  try { return sessionStore()?.getItem(AUTH_MARKER_KEY) === "1" } catch { return false }
}

function setAuthMarker() {
  try { sessionStore()?.setItem(AUTH_MARKER_KEY, "1") } catch {}
}

export function getAccessToken() {
  return null
}

export function getRefreshToken() {
  return null
}

export function setTokens() {
  setAuthMarker()
}

export function clearTokens() {
  try { sessionStore()?.removeItem(AUTH_MARKER_KEY) } catch {}
}

export const ALL_ROLES = ["Profesores", "Preceptores", "Directivos", "Padres", "Alumnos"]

export function getPreviewRole() {
  try { return localStorage.getItem("preview_role") || "" } catch { return "" }
}

export function setPreviewRole(role) {
  try {
    if (role) localStorage.setItem("preview_role", role)
    else localStorage.removeItem("preview_role")
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("preview_role_changed", { detail: role }))
    }
  } catch {}
}

export function useRolePreview() {
  const [preview, _set] = useState(() => getPreviewRole())
  useEffect(() => {
    const h = (e) => _set(e?.detail ?? getPreviewRole())
    window.addEventListener("preview_role_changed", h)
    return () => window.removeEventListener("preview_role_changed", h)
  }, [])
  return [preview, (r) => { setPreviewRole(r); _set(r) }]
}

export function getEffectiveGroups(me) {
  const base = Array.isArray(me?.groups) ? me.groups
             : Array.isArray(me?.grupos) ? me.grupos
             : []
  const isSuper = !!me?.is_superuser || !!me?.user?.is_superuser
  const p = getPreviewRole()
  if (isSuper && p) return [p]
  return base
}

function normalizeApiPath(path) {
  if (!path) return ""

  const raw = String(path)
  if (/^https?:\/\//i.test(raw)) return raw

  const [beforeHash, hash] = raw.split("#")
  const [p0, q] = String(beforeHash).split("?")

  let p = String(p0).replace(/^\/+/, "")
  if (API_BASE_HAS_API) {
    if (p === "api") p = ""
    if (p.startsWith("api/")) p = p.slice(4)
  }

  let rebuilt = p
  if (q != null) rebuilt += `?${q}`
  if (hash != null) rebuilt += `#${hash}`
  return rebuilt
}

function looksLikeLoginRedirect(res) {
  try {
    const url = String(res?.url || "")
    return !!(res?.redirected && (url.includes("/accounts/login/") || url.includes("/login")))
  } catch {
    return false
  }
}

function isProbablyLoginHtml(res) {
  try {
    const ct = (res?.headers?.get?.("content-type") || "").toLowerCase()
    if (!ct.includes("text/html")) return false
    const url = String(res?.url || "")
    return url.includes("/accounts/login/") || url.includes("/login") || url.includes("next=")
  } catch {
    return false
  }
}

function forceRelogin(reason = "No autenticado") {
  clearTokens()
  if (typeof window !== "undefined") window.location.assign("/login")
  throw new Error(reason)
}

export async function authFetch(path, opts = {}) {
  const normalized = normalizeApiPath(path)
  const url = /^https?:\/\//i.test(String(normalized))
    ? String(normalized)
    : `${API_BASE.replace(/\/+$/,"")}/${String(normalized).replace(/^\/+/,"")}`

  const headers = new Headers(opts.headers || {})
  if (!headers.has("Accept")) headers.set("Accept", "application/json")

  const preview = getPreviewRole()
  if (preview) headers.set("X-Preview-Role", preview)

  const method = (opts.method || "GET").toUpperCase()
  let finalUrl = url
  if (preview && method === "GET") {
    const sep = url.includes("?") ? "&" : "?"
    finalUrl = `${url}${sep}view_as=${encodeURIComponent(preview)}`
  }

  if (!headers.has("Content-Type") && opts.body && !(opts.body instanceof FormData)) {
    headers.set("Content-Type", "application/json")
  }

  let res = await fetch(finalUrl, { credentials: "include", ...opts, headers })
  if (looksLikeLoginRedirect(res) || isProbablyLoginHtml(res)) {
    forceRelogin("SesiÃ³n invÃ¡lida o endpoint con redirect a login.")
  }
  if (res.status !== 401 && res.status !== 403) return res

  const ok = await tryRefresh()
  if (!ok) forceRelogin("No autenticado")

  const headers2 = new Headers(opts.headers || {})
  if (!headers2.has("Accept")) headers2.set("Accept", "application/json")
  if (preview) headers2.set("X-Preview-Role", preview)
  if (!headers2.has("Content-Type") && opts.body && !(opts.body instanceof FormData)) {
    headers2.set("Content-Type", "application/json")
  }

  res = await fetch(finalUrl, { credentials: "include", ...opts, headers: headers2 })
  if (looksLikeLoginRedirect(res) || isProbablyLoginHtml(res)) {
    forceRelogin("SesiÃ³n invÃ¡lida o endpoint con redirect a login.")
  }
  return res
}

export async function tryRefresh() {
  try {
    const res = await fetch(`${API_BASE}/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      credentials: "include",
      body: JSON.stringify({}),
    })
    if (!res.ok) return false
    setAuthMarker()
    return true
  } catch {
    return false
  }
}

export async function logout() {
  try {
    try {
      await fetch(`${API_BASE}/token/blacklist/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        credentials: "include",
        body: JSON.stringify({}),
      })
    } catch {}

    try {
      await fetch(`${API_BASE}/auth/logout/`, {
        method: "POST",
        credentials: "include",
      })
    } catch {}
  } finally {
    clearTokens()
    if (typeof window !== "undefined") window.location.replace("/login")
  }
}

export function useAuthGuard(options = {}) {
  const enabled = options?.enabled !== false

  useEffect(() => {
    if (!enabled) return

    try {
      const href = (window.location && window.location.href) ? window.location.href : ""
      const p = (window.location && window.location.pathname) ? window.location.pathname : ""
      if (
        p === "/" ||
        p.startsWith("/login") ||
        p.startsWith("/forgot-password") ||
        p.startsWith("/reset-password") ||
        href.includes("/login") ||
        href.includes("/forgot-password") ||
        href.includes("/reset-password")
      ) {
        return
      }
    } catch {}

    let cancelled = false

    async function verifySession() {
      if (hasAuthMarker()) return
      try {
        const res = await fetch(`${API_BASE}/auth/whoami/`, {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        })
        if (!res.ok) throw new Error("unauthorized")
        setAuthMarker()
      } catch {
        if (!cancelled && typeof window !== "undefined") {
          window.location.href = "/login"
        }
      }
    }

    verifySession()
    return () => { cancelled = true }
  }, [enabled])
}
