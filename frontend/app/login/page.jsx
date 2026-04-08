"use client"

import Image from "next/image"
import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import {
  API_BASE,
  DEFAULT_SCHOOL_LOGO_URL,
  authFetch,
  getRequestedSchoolIdentifierFromWindow,
  clearTokens,
  sanitizePostLoginPath,
  setTokens,
  syncSessionContext,
  usePublicSchoolBranding,
} from "../_lib/auth"

export default function LoginPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const branding = usePublicSchoolBranding({ clearSession: true })
  const [logoSrc, setLogoSrc] = useState(branding.logo_url || DEFAULT_SCHOOL_LOGO_URL)
  const nextPath = sanitizePostLoginPath(searchParams?.get("next") || "")
  const isAdminLogin = nextPath === "/admin" || nextPath.startsWith("/admin/")

  useEffect(() => {
    setLogoSrc(branding.logo_url || DEFAULT_SCHOOL_LOGO_URL)
  }, [branding.logo_url])

  const clearServerSession = async () => {
    try {
      await fetch(`${API_BASE}/auth/logout/`, {
        method: "POST",
        credentials: "include",
      })
    } catch {}
    clearTokens()
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError("")

    try {
      const res = await fetch(`${API_BASE}/token/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data?.detail || "Usuario o clave incorrecto")
      } else {
        setTokens()
        try {
          const schoolParam = getRequestedSchoolIdentifierFromWindow()
          const meRes = await authFetch("/auth/whoami/", {
            headers: schoolParam ? { "X-School": schoolParam } : undefined,
          })
          const me = await meRes.json().catch(() => ({}))

          if (isAdminLogin && !me?.is_superuser) {
            await clearServerSession()
            setError("Este acceso es solo para administradores.")
            return
          }

          syncSessionContext(me)
          router.replace(nextPath || (me?.is_superuser ? "/admin" : "/dashboard"))
        } catch {
          router.replace(nextPath || "/dashboard")
        }
      }
    } catch {
      setError("No se pudo conectar con el servidor")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center bg-gray-50 px-4"
      style={{
        backgroundImage: `linear-gradient(160deg, ${branding.primary_color}12 0%, #f8fafc 42%, ${branding.accent_color}10 100%)`,
      }}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-8 shadow"
        style={{ borderTop: `4px solid ${branding.primary_color}` }}
      >
        <div className="flex justify-center mb-4">
          <Image
            src={logoSrc}
            alt={branding.name ? `Logo de ${branding.name}` : "Logo de la plataforma"}
            className="h-16 w-auto object-contain"
            width={160}
            height={64}
            unoptimized
            onError={() => {
              if (logoSrc === DEFAULT_SCHOOL_LOGO_URL) return
              setLogoSrc(DEFAULT_SCHOOL_LOGO_URL)
            }}
          />
        </div>
        <h1 className="text-2xl font-semibold text-center mb-3">Iniciar sesion</h1>
        <p className="text-sm text-center text-gray-600 mb-6">
          Accede con tu usuario para entrar a {branding.short_name || branding.name}.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700">
              Usuario
            </label>
            <input
              id="username"
              type="text"
              required
              className="w-full mt-1 rounded-md border px-4 py-2"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              Contrasena
            </label>
            <input
              id="password"
              type="password"
              required
              className="w-full mt-1 rounded-md border px-4 py-2"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          <div className="flex flex-row flex-wrap items-center justify-center gap-2 pt-1">
            <button
              type="submit"
              disabled={loading}
              className="shrink-0 rounded-md px-6 py-2 text-sm text-white disabled:opacity-70"
              style={{
                backgroundColor: branding.primary_color,
              }}
            >
              {loading ? "Ingresando..." : "Ingresar"}
            </button>
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <span aria-hidden="true">|</span>
              <a
                href="/forgot-password"
                className="whitespace-nowrap hover:underline"
                style={{ color: branding.accent_color }}
              >
                Olvidaste tu contrasena?
              </a>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
