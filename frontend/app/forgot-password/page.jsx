"use client"

import { useState } from "react"
import { API_BASE } from "../_lib/auth"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError("")
    setMessage("")
    try {
      const res = await fetch(`${API_BASE.replace(/\/+$/, "")}/auth/password-reset/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ email }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo enviar el correo.")
      } else {
        setMessage(
          data?.detail ||
            "Si el correo existe, te enviaremos un link para restablecer tu contraseña."
        )
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
        <h1 className="text-2xl font-semibold text-center mb-6">Recuperar contraseña</h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              className="w-full mt-1 px-4 py-2 border rounded-md"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>

          {error && <p className="text-red-600 text-sm">{error}</p>}
          {message && <p className="text-green-700 text-sm">{message}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#0c1b3f] text-white py-2 rounded-md hover:bg-[#0a1736] disabled:opacity-70"
          >
            {loading ? "Enviando..." : "Enviar link"}
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
