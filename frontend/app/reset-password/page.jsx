"use client"

import { useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { API_BASE } from "../_lib/auth"

export default function ResetPasswordPage() {
  const params = useSearchParams()
  const uid = params.get("uid") || ""
  const token = params.get("token") || ""

  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")

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
      const res = await fetch(
        `${API_BASE.replace(/\/+$/, "")}/auth/password-reset/confirm/`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ uid, token, password }),
        }
      )
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
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow p-8">
        <h1 className="text-2xl font-semibold text-center mb-6">Nueva contraseña</h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              Contraseña nueva
            </label>
            <input
              id="password"
              type="password"
              required
              className="w-full mt-1 px-4 py-2 border rounded-md"
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
              className="w-full mt-1 px-4 py-2 border rounded-md"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </div>

          {error && <p className="text-red-600 text-sm">{error}</p>}
          {message && <p className="text-green-700 text-sm">{message}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#0c1b3f] text-white py-2 rounded-md hover:bg-[#0a1736] disabled:opacity-70"
          >
            {loading ? "Guardando..." : "Actualizar contraseña"}
          </button>

          <div className="text-center">
            <a href="/login" className="text-sm text-blue-600 hover:underline">
              Volver a iniciar sesión
            </a>
          </div>
        </form>
      </div>
    </div>
  )
}
