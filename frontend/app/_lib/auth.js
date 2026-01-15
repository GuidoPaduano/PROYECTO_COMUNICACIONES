"use client"

import { useEffect, useState } from "react"

export const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE_URL)
    ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/+$/,"")
    : "http://localhost:8000/api"

// ✅ Si el API_BASE ya termina en "/api" (o "/api/"), evitamos duplicar prefijos.
const API_BASE_HAS_API = /\/api\/?$/.test(String(API_BASE))

export function getAccessToken() {
  try { return localStorage.getItem("access_token") } catch { return null }
}
export function getRefreshToken() {
  try { return localStorage.getItem("refresh_token") } catch { return null }
}
export function setTokens(access, refresh) {
  try {
    if (access) localStorage.setItem("access_token", access)
    if (refresh) localStorage.setItem("refresh_token", refresh)
  } catch {}
}
export function clearTokens() {
  try {
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
  } catch {}
}

/** =========================================================
 *  “Vista como…” (preview global de rol)
 *  Guarda el rol simulado y notifica a toda la app.
 *  Roles válidos: "Profesores", "Preceptores", "Padres", "Alumnos"
 * ========================================================= */
export const ALL_ROLES = ["Profesores", "Preceptores", "Padres", "Alumnos"]

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

/** Devuelve los grupos efectivos aplicando la vista previa si corresponde. */
export function getEffectiveGroups(me) {
  const base = Array.isArray(me?.groups) ? me.groups
             : Array.isArray(me?.grupos) ? me.grupos
             : []
  const isSuper = !!me?.is_superuser || !!me?.user?.is_superuser
  const p = getPreviewRole()
  if (isSuper && p) return [p]
  return base
}

/* =========================================================
   Helpers URL: evita /api/api/ aunque le pasen "/api/..."
   ========================================================= */
function normalizeApiPath(path) {
  if (!path) return ""

  const raw = String(path)

  // ✅ Si es URL absoluta (http/https), no se toca.
  if (/^https?:\/\//i.test(raw)) return raw

  // Separar hash y query para no romper ?a=b#x
  const [beforeHash, hash] = raw.split("#")
  const [p0, q] = String(beforeHash).split("?")

  let p = String(p0).replace(/^\/+/, "") // sin slash inicial

  // ✅ Si API_BASE ya incluye "/api", recortamos el prefijo "api/".
  // Si API_BASE NO incluye "/api" (configuración común), lo dejamos tal cual.
  if (API_BASE_HAS_API) {
    if (p === "api") p = ""
    if (p.startsWith("api/")) p = p.slice(4)
  }

  let rebuilt = p
  if (q != null) rebuilt += `?${q}`
  if (hash != null) rebuilt += `#${hash}`
  return rebuilt
}

/* =========================================================
   FIX: detectar redirect a login o “HTML de login”
   ========================================================= */
function looksLikeLoginRedirect(res) {
  try {
    const url = String(res?.url || "")
    if (res?.redirected && (url.includes("/accounts/login/") || url.includes("/login"))) return true
    return false
  } catch {
    return false
  }
}

function isProbablyLoginHtml(res) {
  try {
    const ct = (res?.headers?.get?.("content-type") || "").toLowerCase()
    if (!ct.includes("text/html")) return false
    const url = String(res?.url || "")
    // Solo nos importa HTML si el destino “huele a login”
    if (url.includes("/accounts/login/")) return true
    if (url.includes("/login")) return true
    if (url.includes("next=")) return true
    return false
  } catch {
    return false
  }
}

function forceRelogin(reason = "No autenticado") {
  clearTokens()
  if (typeof window !== "undefined") window.location.assign("/login")
  throw new Error(reason)
}

/**
 * Hace fetch con Bearer; si da 401/403 intenta refrescar y reintenta una vez.
 * Incluye credentials para compatibilidad con sesión (cookies).
 * Agrega el header X-Preview-Role y `?view_as=` cuando hay “Vista como…”.
 */
export async function authFetch(path, opts = {}) {
  const normalized = normalizeApiPath(path)

  const url = /^https?:\/\//i.test(String(normalized))
    ? String(normalized)
    : `${API_BASE.replace(/\/+$/,"")}/${String(normalized).replace(/^\/+/,"")}`

  const token = getAccessToken()
  const headers = new Headers(opts.headers || {})

  if (!headers.has("Accept")) headers.set("Accept", "application/json")
  if (token) headers.set("Authorization", `Bearer ${token}`)

  // —— Vista como ——
  const preview = getPreviewRole()
  if (preview) headers.set("X-Preview-Role", preview)

  // Agregar ?view_as= para endpoints que lean querystring.
  const addQueryForAllMethods = false
  const method = (opts.method || "GET").toUpperCase()
  let finalUrl = url
  if (preview && (method === "GET" || addQueryForAllMethods)) {
    const sep = url.includes("?") ? "&" : "?"
    finalUrl = `${url}${sep}view_as=${encodeURIComponent(preview)}`
  }

  // Content-Type por defecto para cuerpos no-FormData
  if (!headers.has("Content-Type") && opts.body && !(opts.body instanceof FormData)) {
    headers.set("Content-Type", "application/json")
  }

  let res = await fetch(finalUrl, { credentials: "include", ...opts, headers })

  // ✅ FIX: si terminamos en login_required (redirect) o HTML de login, reloguear
  if (looksLikeLoginRedirect(res) || isProbablyLoginHtml(res)) {
    forceRelogin("Sesión inválida o endpoint con redirect a login.")
  }

  if (res.status !== 401 && res.status !== 403) return res

  // Intentamos refresh una vez
  const ok = await tryRefresh()
  if (!ok) {
    forceRelogin("No autenticado")
  }

  // Reintento con nuevo access
  const headers2 = new Headers(opts.headers || {})
  const newToken = getAccessToken()
  if (!headers2.has("Accept")) headers2.set("Accept", "application/json")
  if (newToken) headers2.set("Authorization", `Bearer ${newToken}`)

  // Reenviar vista como también en el reintento
  if (preview) headers2.set("X-Preview-Role", preview)
  if (!headers2.has("Content-Type") && opts.body && !(opts.body instanceof FormData)) {
    headers2.set("Content-Type", "application/json")
  }

  res = await fetch(finalUrl, { credentials: "include", ...opts, headers: headers2 })

  // ✅ Re-check por si el reintento terminó en login/html
  if (looksLikeLoginRedirect(res) || isProbablyLoginHtml(res)) {
    forceRelogin("Sesión inválida o endpoint con redirect a login.")
  }

  return res
}

/**
 * Intenta rotar/renovar el access (y refresh si ROTATE_REFRESH_TOKENS=True).
 * Guarda el refresh nuevo cuando existe; si no, mantiene el actual.
 */
export async function tryRefresh() {
  const refresh = getRefreshToken()
  if (!refresh) return false
  try {
    const res = await fetch(`${API_BASE}/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ refresh })
    })
    if (!res.ok) return false
    const data = await res.json().catch(() => ({}))
    if (!data?.access) return false
    setTokens(data.access, data.refresh || refresh)
    return true
  } catch {
    return false
  }
}

/**
 * Cerrar sesión completa:
 * 1) Blacklistea el refresh (si existe) -> /api/token/blacklist/
 * 2) Cierra sesión de Django (si usabas cookies) -> /api/auth/logout/
 * 3) Limpia storage y redirige a /login
 */
export async function logout() {
  try {
    const refresh = getRefreshToken()
    if (refresh) {
      try {
        await fetch(`${API_BASE}/token/blacklist/`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ refresh }),
        })
      } catch {}
    }

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

/** Hook simple: si no hay token, te manda a /login. */
export function useAuthGuard() {
  useEffect(() => {
    const t = getAccessToken()
    if (!t && typeof window !== "undefined") {
      window.location.href = "/login"
    }
  }, [])
}
