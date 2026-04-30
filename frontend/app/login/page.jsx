"use client"

import Image from "next/image"
import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import {
  buildApiUrl,
  clearTokens,
  DEFAULT_SCHOOL_LOGO_URL,
  authFetch,
  getRequestedSchoolIdentifierFromWindow,
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

  const canAccessAdminPath = (me) => {
    if (me?.is_superuser) return true
    if (!nextPath?.startsWith("/admin/colegio")) return false
    const groups = Array.isArray(me?.groups) ? me.groups : []
    return groups.some((group) => {
      const value = String(group || "").toLowerCase()
      return value === "administradores" || value === "administrador"
    })
  }

  const isSchoolAdminUser = (me) => {
    const groups = Array.isArray(me?.groups) ? me.groups : []
    return groups.some((group) => {
      const value = String(group || "").toLowerCase()
      return value === "administradores" || value === "administrador"
    })
  }

  useEffect(() => {
    setLogoSrc(branding.logo_url || DEFAULT_SCHOOL_LOGO_URL)
  }, [branding.logo_url])

  const handleSubmit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError("")

    try {
      const schoolParam = getRequestedSchoolIdentifierFromWindow()
      clearTokens()
      await fetch(buildApiUrl("/auth/logout/"), {
        method: "POST",
        credentials: "include",
      }).catch(() => {})

      const res = await fetch(buildApiUrl("/token/"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(schoolParam ? { "X-School": schoolParam } : {}),
        },
        credentials: "include",
        body: JSON.stringify({ username, password, school: schoolParam }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data?.detail || "Usuario o clave incorrecto")
      } else {
        setTokens()
        try {
          const meRes = await authFetch("/auth/whoami/", {
            headers: schoolParam ? { "X-School": schoolParam } : undefined,
          })
          const me = await meRes.json().catch(() => ({}))
          if (!meRes.ok) {
            clearTokens()
            setError(me?.detail || "El usuario no pertenece al colegio seleccionado.")
            return
          }

          if (isAdminLogin && !canAccessAdminPath(me)) {
            syncSessionContext(me)
            router.replace("/dashboard")
            return
          }

          syncSessionContext(me)
          router.replace(nextPath || (me?.is_superuser || isSchoolAdminUser(me) ? "/admin/colegio" : "/dashboard"))
        } catch {
          clearTokens()
          setError("No se pudo validar el colegio seleccionado.")
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
        <h1 className="text-2xl font-semibold text-center mb-3">Iniciar sesión</h1>
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
              Contraseña
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
                ¿Olvidaste tu contraseña?
              </a>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
