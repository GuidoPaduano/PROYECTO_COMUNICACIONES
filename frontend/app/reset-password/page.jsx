"use client"

import { useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { DEFAULT_SCHOOL_LOGO_URL, buildApiUrl, usePublicSchoolBranding } from "../_lib/auth"

export default function ResetPasswordPage() {
  const params = useSearchParams()
  const uid = params.get("uid") || ""
  const token = params.get("token") || ""

  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const branding = usePublicSchoolBranding()

  const hasParams = useMemo(() => !!uid && !!token, [uid, token])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError("")
    setMessage("")
    if (!hasParams) {
      setError("El link es inválido o está incompleto.")
      return
    }
    if (!password || password.length < 6) {
      setError("La contraseña debe tener al menos 6 caracteres.")
      return
    }
    if (password !== confirm) {
      setError("Las contraseñas no coinciden.")
      return
    }
    setLoading(true)
    try {
      const res = await fetch(buildApiUrl("/auth/password-reset/confirm/"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ uid, token, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo actualizar la contraseña.")
      } else {
        setMessage(data?.detail || "Contraseña actualizada. Ya podés iniciar sesión.")
      }
    } catch {
      setError("No se pudo conectar con el servidor.")
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
        <div className="mb-4 flex justify-center">
          <img
            src={branding.logo_url}
            alt={branding.name ? `Logo de ${branding.name}` : "Logo de la plataforma"}
            className="h-14 w-auto object-contain"
            onError={(event) => {
              if (event.currentTarget.dataset.fallbackApplied) return
              event.currentTarget.dataset.fallbackApplied = "1"
              event.currentTarget.src = DEFAULT_SCHOOL_LOGO_URL
            }}
          />
        </div>
        <h1 className="mb-6 text-center text-2xl font-semibold">Nueva contraseña</h1>
        <p className="mb-6 text-center text-sm text-gray-600">
          Actualiza el acceso para volver a entrar a {branding.short_name || branding.name}.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              Contraseña nueva
            </label>
            <input
              id="password"
              type="password"
              required
              className="mt-1 w-full rounded-md border px-4 py-2"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
          </div>

          <div>
            <label htmlFor="confirm" className="block text-sm font-medium text-gray-700">
              Repetir contraseña
            </label>
            <input
              id="confirm"
              type="password"
              required
              className="mt-1 w-full rounded-md border px-4 py-2"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {message ? <p className="text-sm text-green-700">{message}</p> : null}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md py-2 text-white disabled:opacity-70"
            style={{ backgroundColor: branding.primary_color }}
          >
            {loading ? "Guardando..." : "Actualizar contraseña"}
          </button>

          <div className="text-center">
            <a href="/login" className="text-sm hover:underline" style={{ color: branding.accent_color }}>
              Volver a iniciar sesión
            </a>
          </div>
        </form>
      </div>
    </div>
  )
}
