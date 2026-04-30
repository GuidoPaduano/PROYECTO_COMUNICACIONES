"use client"

import { useEffect, useState } from "react"

export const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE_URL)
    ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/+$/, "")
    : "/api"
export const SCHOOL_PARENT_DOMAIN =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_PARENT_DOMAIN)
    ? String(process.env.NEXT_PUBLIC_PARENT_DOMAIN).trim().toLowerCase()
    : ""
export const BACKEND_BASE_URL =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_BACKEND_BASE_URL)
    ? process.env.NEXT_PUBLIC_BACKEND_BASE_URL.replace(/\/+$/, "")
    : ""

const API_BASE_HAS_API = /\/api\/?$/.test(String(API_BASE))
const AUTH_MARKER_KEY = "auth_session"
const SESSION_CONTEXT_KEY = "auth_context"
const LAST_SCHOOL_KEY = "auth_last_school"
const SESSION_CONTEXT_EVENT = "auth_context_changed"
const SESSION_PROFILE_MAX_AGE_MS = 30000
const PROFILE_API_MAX_AGE_MS = 15000
export const DEFAULT_SCHOOL_LOGO_URL = "/imagenes/Logo%20Color.png"
export const DEFAULT_SCHOOL_PRIMARY_COLOR = "#0c1b3f"
export const DEFAULT_SCHOOL_ACCENT_COLOR = "#1d4ed8"
export const DEFAULT_PUBLIC_BRANDING = {
  name: "Plataforma de Comunicaciones",
  short_name: "",
  logo_url: DEFAULT_SCHOOL_LOGO_URL,
  primary_color: DEFAULT_SCHOOL_PRIMARY_COLOR,
  accent_color: DEFAULT_SCHOOL_ACCENT_COLOR,
}

export function buildApiUrl(path = "") {
  const base = String(API_BASE || "/api").replace(/\/+$/, "")
  const suffix = String(path || "").replace(/^\/+/, "")
  const url = `${base}/${suffix}`

  if (/^https?:\/\//i.test(url)) return url

  if (typeof window !== "undefined" && window.location?.origin) {
    return new URL(url, window.location.origin).toString()
  }

  return url
}

export function buildBackendUrl(path = "") {
  const suffix = String(path || "").replace(/^\/+/, "")
  if (BACKEND_BASE_URL) return `${BACKEND_BASE_URL}/${suffix}`

  const base = String(API_BASE || "").replace(/\/+$/, "")
  if (/^https?:\/\//i.test(base)) {
    const origin = base.replace(/\/api$/i, "")
    return `${origin}/${suffix}`
  }

  return `/${suffix}`
}

let sessionProfileCache = null
let sessionProfilePromise = null
let profileApiCache = null
let profileApiPromise = null

function normalizeHexColor(value, fallback) {
  const raw = String(value || "").trim()
  return /^#[0-9a-fA-F]{6}$/.test(raw) ? raw.toLowerCase() : fallback
}

function normalizeHostname(rawHost) {
  return String(rawHost || "")
    .trim()
    .toLowerCase()
    .replace(/:\d+$/, "")
    .replace(/\.+$/, "")
}

export function getSchoolSlugFromHost(rawHost = "") {
  const host = normalizeHostname(rawHost)
  if (!host || host === "localhost" || host === "127.0.0.1") return ""

  if (SCHOOL_PARENT_DOMAIN) {
    if (host === SCHOOL_PARENT_DOMAIN) return ""
    const suffix = `.${SCHOOL_PARENT_DOMAIN}`
    if (host.endsWith(suffix)) {
      const prefix = host.slice(0, -suffix.length).trim()
      if (prefix && !prefix.includes(".") && prefix !== "www") {
        return prefix
      }
    }
  }

  if (host.endsWith(".localhost")) {
    const prefix = host.slice(0, -".localhost".length).trim()
    if (prefix && !prefix.includes(".")) return prefix
  }

  return ""
}

function sessionStore() {
  try {
    if (typeof window !== "undefined" && window.sessionStorage) return window.sessionStorage
  } catch {}
  return null
}

function localStore() {
  try {
    if (typeof window !== "undefined" && window.localStorage) return window.localStorage
  } catch {}
  return null
}

function getRelativeLocation() {
  try {
    if (typeof window === "undefined" || !window.location) return ""
    const pathname = String(window.location.pathname || "")
    const search = String(window.location.search || "")
    const hash = String(window.location.hash || "")
    return `${pathname}${search}${hash}` || ""
  } catch {
    return ""
  }
}

function buildLoginHref(nextPath = "") {
  const fallback = "/login"
  const target = String(nextPath || "").trim()
  if (!target || !target.startsWith("/") || target.startsWith("//") || target.startsWith("/login")) {
    return fallback
  }
  return `/login?next=${encodeURIComponent(target)}`
}

export function sanitizePostLoginPath(rawPath = "") {
  const value = String(rawPath || "").trim()
  if (!value || !value.startsWith("/") || value.startsWith("//")) return ""
  if (value === "/" || value.startsWith("/login")) return ""
  return value
}

function dispatchSessionContext(context) {
  try {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(SESSION_CONTEXT_EVENT, { detail: context || null }))
    }
  } catch {}
}

function hasAuthMarker() {
  try {
    return sessionStore()?.getItem(AUTH_MARKER_KEY) === "1"
  } catch {
    return false
  }
}

function setAuthMarker() {
  try {
    sessionStore()?.setItem(AUTH_MARKER_KEY, "1")
  } catch {}
}

export function normalizeSchool(rawSchool) {
  if (!rawSchool || typeof rawSchool !== "object") return null

  const id = rawSchool.id ?? rawSchool.school_id ?? null
  const name = String(rawSchool.name || rawSchool.school_name || "").trim()
  const shortName = String(rawSchool.short_name || rawSchool.school_short_name || "").trim()
  const slug = String(rawSchool.slug || rawSchool.school_slug || "").trim()
  const logoUrl = String(rawSchool.logo_url || rawSchool.school_logo_url || "").trim() || DEFAULT_SCHOOL_LOGO_URL
  const primaryColor = normalizeHexColor(
    rawSchool.primary_color || rawSchool.school_primary_color,
    DEFAULT_SCHOOL_PRIMARY_COLOR
  )
  const accentColor = normalizeHexColor(
    rawSchool.accent_color || rawSchool.school_accent_color,
    DEFAULT_SCHOOL_ACCENT_COLOR
  )
  const isActive = rawSchool.is_active !== false

  if (id == null && !name && !slug) return null

  return {
    id,
    name: name || slug || "",
    short_name: shortName,
    slug,
    logo_url: logoUrl,
    primary_color: primaryColor,
    accent_color: accentColor,
    is_active: isActive,
  }
}

function buildPublicBranding(school, fallback = DEFAULT_PUBLIC_BRANDING) {
  const normalizedFallback = {
    name: String(fallback?.name || DEFAULT_PUBLIC_BRANDING.name).trim() || DEFAULT_PUBLIC_BRANDING.name,
    short_name: String(fallback?.short_name || "").trim(),
    logo_url: String(fallback?.logo_url || DEFAULT_PUBLIC_BRANDING.logo_url).trim() || DEFAULT_PUBLIC_BRANDING.logo_url,
    primary_color: normalizeHexColor(fallback?.primary_color, DEFAULT_PUBLIC_BRANDING.primary_color),
    accent_color: normalizeHexColor(fallback?.accent_color, DEFAULT_PUBLIC_BRANDING.accent_color),
  }
  const normalizedSchool = normalizeSchool(school)
  if (!normalizedSchool) return normalizedFallback
  return {
    name: normalizedSchool.name || normalizedFallback.name,
    short_name: normalizedSchool.short_name || "",
    logo_url: normalizedSchool.logo_url || normalizedFallback.logo_url,
    primary_color: normalizedSchool.primary_color || normalizedFallback.primary_color,
    accent_color: normalizedSchool.accent_color || normalizedFallback.accent_color,
  }
}

function getSchoolParamFromWindow() {
  try {
    if (typeof window === "undefined") return ""
    return new URLSearchParams(window.location.search || "").get("school") || ""
  } catch {
    return ""
  }
}

export function getHostSchoolSlugFromWindow() {
  try {
    if (typeof window === "undefined") return ""
    return getSchoolSlugFromHost(window.location.hostname || "")
  } catch {
    return ""
  }
}

export function getRequestedSchoolIdentifierFromWindow() {
  return getSchoolParamFromWindow() || getHostSchoolSlugFromWindow() || ""
}

export function getLastSessionSchool() {
  try {
    const raw = localStore()?.getItem(LAST_SCHOOL_KEY)
    if (!raw) return null
    return normalizeSchool(JSON.parse(raw))
  } catch {
    return null
  }
}

function rememberLastSessionSchool(rawSchool) {
  const school = normalizeSchool(rawSchool)
  if (!school?.slug && school?.id == null) return
  try {
    localStore()?.setItem(LAST_SCHOOL_KEY, JSON.stringify(school))
  } catch {}
}

export function getLastSchoolLoginHref() {
  const school = getLastSessionSchool()
  return school ? buildSchoolLoginHref(school) : ""
}

export function buildSchoolLoginHref(school) {
  const normalizedSchool = normalizeSchool(school)
  const schoolSlug = String(normalizedSchool?.slug || "").trim()
  if (!schoolSlug) return "/login"

  if (SCHOOL_PARENT_DOMAIN) {
    const protocol =
      typeof window !== "undefined" && window.location?.protocol
        ? window.location.protocol
        : "https:"
    return `${protocol}//${schoolSlug}.${SCHOOL_PARENT_DOMAIN}/login`
  }

  return `/login?school=${encodeURIComponent(schoolSlug)}`
}

export function usePublicSchoolBranding(options = {}) {
  const {
    fallback = DEFAULT_PUBLIC_BRANDING,
    clearSession = false,
  } = options || {}
  const [branding, setBranding] = useState(() => buildPublicBranding(null, fallback))

  useEffect(() => {
    if (clearSession) {
      try {
        clearTokens()
      } catch {}
    }

    let alive = true
    ;(async () => {
      try {
        const schoolParam = getRequestedSchoolIdentifierFromWindow()
        const url = new URL(buildApiUrl("/public/school-branding/"))
        if (schoolParam) url.searchParams.set("school", schoolParam)
        const res = await fetch(url.toString(), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        })
        if (!res.ok) return
        const data = await res.json().catch(() => ({}))
        if (alive) {
          setBranding(buildPublicBranding(data?.school, fallback))
        }
      } catch {}
    })()

    return () => {
      alive = false
    }
  }, [clearSession, fallback])

  return branding
}

function normalizeSchoolList(rawSchools) {
  if (!Array.isArray(rawSchools)) return []

  const items = []
  const seen = new Set()

  for (const rawSchool of rawSchools) {
    const school = normalizeSchool(rawSchool)
    const key = school?.id != null ? `id:${school.id}` : school?.slug ? `slug:${school.slug}` : ""
    if (!school || !key || seen.has(key)) continue
    seen.add(key)
    items.push(school)
  }

  return items
}

function normalizeGroups(rawGroups) {
  if (!Array.isArray(rawGroups)) return []
  return rawGroups
    .map((group) => (typeof group === "string" ? group : group?.name || group?.nombre || ""))
    .filter(Boolean)
}

export function buildSessionContext(payload = {}) {
  const initialSchool = normalizeSchool(payload?.school || payload?.user?.school || null)
  const availableSchools = normalizeSchoolList(
    payload?.available_schools || payload?.availableSchools || payload?.user?.available_schools || []
  )
  const groups = normalizeGroups(
    payload?.groups || payload?.user?.groups || []
  )
  const username = String(payload?.username || payload?.user?.username || "").trim()
  const fullName = String(
    payload?.full_name ||
      payload?.user?.full_name ||
      [payload?.first_name, payload?.last_name].filter(Boolean).join(" ") ||
      [payload?.user?.first_name, payload?.user?.last_name].filter(Boolean).join(" ")
  ).trim()
  const school = initialSchool || availableSchools[0] || null

  return {
    userLabel: fullName || username,
    username,
    groups,
    role: String(payload?.rol || payload?.user?.rol || "").trim(),
    isSuperuser: !!payload?.is_superuser || !!payload?.user?.is_superuser,
    school,
    availableSchools,
  }
}

export function getSessionContext() {
  try {
    const raw = sessionStore()?.getItem(SESSION_CONTEXT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === "object" ? parsed : null
  } catch {
    return null
  }
}

export function setSessionContext(context) {
  try {
    const store = sessionStore()
    if (!store) return null

    if (!context) {
      store.removeItem(SESSION_CONTEXT_KEY)
      dispatchSessionContext(null)
      return null
    }

    store.setItem(SESSION_CONTEXT_KEY, JSON.stringify(context))
    rememberLastSessionSchool(context?.school)
    dispatchSessionContext(context)
    return context
  } catch {
    return null
  }
}

export function clearSessionContext() {
  try {
    sessionStore()?.removeItem(SESSION_CONTEXT_KEY)
  } catch {}
  invalidateSessionProfileCache()
  dispatchSessionContext(null)
}

export function syncSessionContext(payload = {}) {
  const previous = getSessionContext() || {}
  const next = buildSessionContext(payload)
  const merged = {
    ...previous,
    ...next,
    userLabel: next.userLabel || previous.userLabel || "",
    username: next.username || previous.username || "",
    groups: Array.isArray(next.groups) ? next.groups : previous.groups || [],
    role: next.role || previous.role || "",
    isSuperuser: !!next.isSuperuser,
    school: next.school || previous.school || null,
    availableSchools: next.availableSchools.length ? next.availableSchools : previous.availableSchools || [],
  }
  return setSessionContext(merged)
}

function schoolMatchesIdentifier(school, rawValue) {
  const value = String(rawValue || "").trim()
  if (!school || !value) return false

  if (value.startsWith("slug:")) return school.slug === value.slice(5)
  if (value.startsWith("id:")) return String(school.id) === value.slice(3)

  return (
    String(school.id) === value ||
    String(school.slug || "") === value ||
    String(school.name || "").toLowerCase() === value.toLowerCase()
  )
}

export function selectSessionSchool(rawValue) {
  const context = getSessionContext()
  if (!context) return null

  const selected =
    normalizeSchool(rawValue) ||
    (Array.isArray(context.availableSchools)
      ? context.availableSchools.find((school) => schoolMatchesIdentifier(school, rawValue))
      : null)

  if (!selected) return null

  invalidateSessionProfileCache()
  return setSessionContext({
    ...context,
    school: selected,
  })
}

function getSessionProfileCacheKey() {
  const context = getSessionContext()
  const previewRole = getPreviewRole()
  const schoolRef =
    String(context?.school?.slug || context?.school?.id || getRequestedSchoolIdentifierFromWindow() || "").trim()
  return `${previewRole || "default"}::${schoolRef || "default"}`
}

function getCachedSessionProfile() {
  const cacheKey = getSessionProfileCacheKey()
  if (
    sessionProfileCache?.key === cacheKey &&
    sessionProfileCache?.expiresAt > Date.now() &&
    sessionProfileCache?.data
  ) {
    return sessionProfileCache.data
  }
  return null
}

export function getCachedSessionProfileData() {
  return getCachedSessionProfile()
}

function buildCachedJsonResponse(data) {
  return new Response(JSON.stringify(data || {}), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "X-Session-Profile-Cache": "hit",
    },
  })
}

export function invalidateSessionProfileCache() {
  sessionProfileCache = null
  sessionProfilePromise = null
  profileApiCache = null
  profileApiPromise = null
}

export async function getSessionProfile(options = {}) {
  const force = options?.force === true
  const maxAgeMs =
    Number.isFinite(Number(options?.maxAgeMs)) && Number(options?.maxAgeMs) > 0
      ? Number(options.maxAgeMs)
      : SESSION_PROFILE_MAX_AGE_MS

  const cacheKey = getSessionProfileCacheKey()
  const now = Date.now()

  if (
    !force &&
    sessionProfileCache?.key === cacheKey &&
    sessionProfileCache?.expiresAt > now &&
    sessionProfileCache?.data
  ) {
    return sessionProfileCache.data
  }

  if (!force && sessionProfilePromise?.key === cacheKey && sessionProfilePromise?.promise) {
    return sessionProfilePromise.promise
  }

  const promise = (async () => {
    const res = await authFetch("/auth/whoami/", { skipProfileCache: true })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data?.detail || `HTTP ${res.status}`)
    }
    syncSessionContext(data)
    sessionProfileCache = {
      key: cacheKey,
      data,
      expiresAt: Date.now() + maxAgeMs,
    }
    return data
  })()

  sessionProfilePromise = { key: cacheKey, promise }

  try {
    return await promise
  } finally {
    if (sessionProfilePromise?.promise === promise) {
      sessionProfilePromise = null
    }
  }
}

function getProfileApiCacheKey() {
  const context = getSessionContext()
  const previewRole = getPreviewRole()
  const schoolRef =
    String(context?.school?.slug || context?.school?.id || getRequestedSchoolIdentifierFromWindow() || "").trim()
  return `${previewRole || "default"}::${schoolRef || "default"}`
}

export function getCachedProfileApi() {
  const cacheKey = getProfileApiCacheKey()
  if (
    profileApiCache?.key === cacheKey &&
    profileApiCache?.expiresAt > Date.now() &&
    profileApiCache?.data
  ) {
    return profileApiCache.data
  }
  return null
}

export async function getProfileApi(options = {}) {
  const force = options?.force === true
  const maxAgeMs =
    Number.isFinite(Number(options?.maxAgeMs)) && Number(options?.maxAgeMs) > 0
      ? Number(options.maxAgeMs)
      : PROFILE_API_MAX_AGE_MS

  const cacheKey = getProfileApiCacheKey()
  const now = Date.now()

  if (
    !force &&
    profileApiCache?.key === cacheKey &&
    profileApiCache?.expiresAt > now &&
    profileApiCache?.data
  ) {
    return profileApiCache.data
  }

  if (!force && profileApiPromise?.key === cacheKey && profileApiPromise?.promise) {
    return profileApiPromise.promise
  }

  const promise = (async () => {
    const res = await authFetch("/perfil_api/", {
      skipProfileApiCache: true,
      headers: { Accept: "application/json" },
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data?.detail || `HTTP ${res.status}`)
    }
    syncSessionContext(data)
    profileApiCache = {
      key: cacheKey,
      data,
      expiresAt: Date.now() + maxAgeMs,
    }
    return data
  })()

  profileApiPromise = { key: cacheKey, promise }

  try {
    return await promise
  } finally {
    if (profileApiPromise?.promise === promise) {
      profileApiPromise = null
    }
  }
}

export function getSessionAlumnoRouteId(profile) {
  if (!profile || typeof profile !== "object") return null

  const pk = profile?.alumno?.id ?? profile?.alumno?.pk ?? null
  if (pk != null && String(pk).trim() !== "") return String(pk).trim()

  const legajo = profile?.alumno?.id_alumno ?? null
  if (legajo != null && String(legajo).trim() !== "") return String(legajo).trim()

  const username = String(profile?.username ?? profile?.user?.username ?? "").trim()
  if (username) return username

  return null
}

export async function resolveSessionAlumnoRouteId(options = {}) {
  const profile = options?.profile && typeof options.profile === "object"
    ? options.profile
    : await getSessionProfile(options)
  return getSessionAlumnoRouteId(profile)
}

export function useSessionContext() {
  const [context, setContext] = useState(() => getSessionContext())

  useEffect(() => {
    const handler = (event) => {
      setContext(event?.detail ?? getSessionContext())
    }
    if (typeof window !== "undefined") {
      window.addEventListener(SESSION_CONTEXT_EVENT, handler)
      return () => window.removeEventListener(SESSION_CONTEXT_EVENT, handler)
    }
    return undefined
  }, [])

  return context
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
  try {
    sessionStore()?.removeItem(AUTH_MARKER_KEY)
  } catch {}
  invalidateSessionProfileCache()
  clearSessionContext()
  setPreviewRole("")
}

function getLogoutRedirectHref() {
  try {
    const context = getSessionContext()
    const school = normalizeSchool(context?.school)
    if (school?.slug) return buildSchoolLoginHref(school)
  } catch {}
  const lastSchoolHref = getLastSchoolLoginHref()
  if (lastSchoolHref) return lastSchoolHref
  return "/"
}

export const ALL_ROLES = ["Profesores", "Preceptores", "Directivos", "Padres", "Alumnos"]

export function getPreviewRole() {
  try {
    return localStorage.getItem("preview_role") || ""
  } catch {
    return ""
  }
}

export function setPreviewRole(role) {
  try {
    if (role) localStorage.setItem("preview_role", role)
    else localStorage.removeItem("preview_role")
    invalidateSessionProfileCache()
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("preview_role_changed", { detail: role }))
    }
  } catch {}
}

export function useRolePreview() {
  const [preview, setPreview] = useState(() => getPreviewRole())

  useEffect(() => {
    const handler = (event) => setPreview(event?.detail ?? getPreviewRole())
    if (typeof window !== "undefined") {
      window.addEventListener("preview_role_changed", handler)
      return () => window.removeEventListener("preview_role_changed", handler)
    }
    return undefined
  }, [])

  return [preview, (role) => {
    setPreviewRole(role)
    setPreview(role)
  }]
}

export function getEffectiveGroups(me) {
  const base = Array.isArray(me?.groups) ? me.groups : []
  const isSuper = !!me?.is_superuser || !!me?.user?.is_superuser
  const preview = getPreviewRole()
  if (isSuper && preview) return [preview]
  return base
}

function normalizeApiPath(path) {
  if (!path) return ""

  const raw = String(path)
  if (/^https?:\/\//i.test(raw)) return raw

  const [beforeHash, hash] = raw.split("#")
  const [pathOnly, query] = String(beforeHash).split("?")

  let normalizedPath = String(pathOnly).replace(/^\/+/, "")
  if (API_BASE_HAS_API) {
    if (normalizedPath === "api") normalizedPath = ""
    if (normalizedPath.startsWith("api/")) normalizedPath = normalizedPath.slice(4)
  }

  let rebuilt = normalizedPath
  if (query != null) rebuilt += `?${query}`
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
    const contentType = (res?.headers?.get?.("content-type") || "").toLowerCase()
    if (!contentType.includes("text/html")) return false
    const url = String(res?.url || "")
    return url.includes("/accounts/login/") || url.includes("/login") || url.includes("next=")
  } catch {
    return false
  }
}

function forceRelogin(reason = "No autenticado") {
  clearTokens()
  if (typeof window !== "undefined") {
    window.location.assign(buildLoginHref(getRelativeLocation()))
  }
  throw new Error(reason)
}

function shouldCaptureSessionContext(path) {
  const normalized = normalizeApiPath(path).replace(/^\/+/, "").replace(/\/+$/, "")
  return normalized === "auth/whoami" || normalized === "perfil_api"
}

function captureSessionContext(path, res) {
  if (!shouldCaptureSessionContext(path) || !res?.ok) return
  try {
    res.clone().json().then((data) => {
      syncSessionContext(data)
    }).catch(() => {})
  } catch {}
}

function applySchoolHeader(headers) {
  const sessionContext = getSessionContext()
  const schoolRef =
    sessionContext?.school?.slug ||
    sessionContext?.school?.id ||
    getRequestedSchoolIdentifierFromWindow()
  if (!sessionContext?.isSuperuser && !schoolRef) return
  if (schoolRef && !headers.has("X-School")) {
    headers.set("X-School", String(schoolRef))
  }
}

export async function authFetch(path, opts = {}) {
  const normalized = normalizeApiPath(path)
  const url = /^https?:\/\//i.test(String(normalized))
    ? String(normalized)
    : buildApiUrl(normalized)

  const headers = new Headers(opts.headers || {})
  if (!headers.has("Accept")) headers.set("Accept", "application/json")

  const preview = getPreviewRole()
  if (preview) headers.set("X-Preview-Role", preview)
  applySchoolHeader(headers)

  const method = (opts.method || "GET").toUpperCase()
  const normalizedPath = String(normalized).replace(/^\/+/, "").replace(/\/+$/, "")
  if (method === "GET" && !opts?.skipProfileCache && normalizedPath === "auth/whoami") {
    const cachedProfile = getCachedSessionProfile()
    if (cachedProfile) {
      syncSessionContext(cachedProfile)
      return buildCachedJsonResponse(cachedProfile)
    }
  }
  let finalUrl = url
  if (preview && method === "GET") {
    const separator = url.includes("?") ? "&" : "?"
    finalUrl = `${url}${separator}view_as=${encodeURIComponent(preview)}`
  }

  if (!headers.has("Content-Type") && opts.body && !(opts.body instanceof FormData)) {
    headers.set("Content-Type", "application/json")
  }

  let res = await fetch(finalUrl, { credentials: "include", ...opts, headers })
  if (looksLikeLoginRedirect(res) || isProbablyLoginHtml(res)) {
    forceRelogin("Sesion invalida o endpoint con redirect a login.")
  }
  captureSessionContext(path, res)
  if (res.status !== 401) return res

  const ok = await tryRefresh()
  if (!ok) forceRelogin("No autenticado")

  const headers2 = new Headers(opts.headers || {})
  if (!headers2.has("Accept")) headers2.set("Accept", "application/json")
  if (preview) headers2.set("X-Preview-Role", preview)
  applySchoolHeader(headers2)
  if (!headers2.has("Content-Type") && opts.body && !(opts.body instanceof FormData)) {
    headers2.set("Content-Type", "application/json")
  }

  res = await fetch(finalUrl, { credentials: "include", ...opts, headers: headers2 })
  if (looksLikeLoginRedirect(res) || isProbablyLoginHtml(res)) {
    forceRelogin("Sesion invalida o endpoint con redirect a login.")
  }
  captureSessionContext(path, res)
  return res
}

export async function tryRefresh() {
  try {
    const res = await fetch(buildApiUrl("/token/refresh/"), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
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
  const redirectHref = getLogoutRedirectHref()
  try {
    try {
      await fetch(buildApiUrl("/token/blacklist/"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "include",
        body: JSON.stringify({}),
      })
    } catch {}

    try {
      await fetch(buildApiUrl("/auth/logout/"), {
        method: "POST",
        credentials: "include",
      })
    } catch {}
  } finally {
    clearTokens()
    if (typeof window !== "undefined") window.location.replace(redirectHref)
  }
}

export function useAuthGuard(options = {}) {
  const enabled = options?.enabled !== false

  useEffect(() => {
    if (!enabled) return

    try {
      const href = (window.location && window.location.href) ? window.location.href : ""
      const pathname = (window.location && window.location.pathname) ? window.location.pathname : ""
      if (
        pathname === "/" ||
        pathname.startsWith("/login") ||
        pathname.startsWith("/forgot-password") ||
        pathname.startsWith("/reset-password") ||
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
        const headers = new Headers({ Accept: "application/json" })
        applySchoolHeader(headers)
        const res = await fetch(buildApiUrl("/auth/whoami/"), {
          method: "GET",
          credentials: "include",
          headers,
        })
        if (!res.ok) throw new Error("unauthorized")
        const data = await res.json().catch(() => ({}))
        setAuthMarker()
        syncSessionContext(data)
      } catch {
        if (!cancelled && typeof window !== "undefined") {
          window.location.href = buildLoginHref(getRelativeLocation())
        }
      }
    }

    verifySession()
    return () => {
      cancelled = true
    }
  }, [enabled])
}
