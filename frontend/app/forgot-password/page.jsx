"use client"

import { useState } from "react"
import { API_BASE, DEFAULT_SCHOOL_LOGO_URL, usePublicSchoolBranding } from "../_lib/auth"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const branding = usePublicSchoolBranding()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError("")
    setMessage("")
    try {
      const res = await fetch(`${API_BASE.replace(/\/+$/, "")}/auth/password-reset/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo enviar el correo.")
      } else {
        setMessage(
          data?.detail ||
            "Si el correo existe, te enviaremos un link para restablecer tu contrasena."
        )
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
        <h1 className="mb-6 text-center text-2xl font-semibold">Recuperar contrasena</h1>
        <p className="mb-6 text-center text-sm text-gray-600">
          Te enviaremos un enlace para restablecer el acceso a {branding.short_name || branding.name}.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              className="mt-1 w-full rounded-md border px-4 py-2"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
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
            {loading ? "Enviando..." : "Enviar link"}
          </button>

          <div className="text-center">
            <a href="/login" className="text-sm hover:underline" style={{ color: branding.accent_color }}>
              Volver a iniciar sesion
            </a>
          </div>
        </form>
      </div>
    </div>
  )
}
