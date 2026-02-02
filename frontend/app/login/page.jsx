"use client"

import { useEffect, useState } from "react"
import { API_BASE, clearTokens, setTokens } from "../_lib/auth"



export default function LoginPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    try {
      // Forzamos logout al llegar a /login para evitar tokens viejos
      clearTokens()
    } catch {}
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError("")
    try {
      const res = await fetch(`${API_BASE}/token/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data?.detail || "Credenciales inválidas")
      } else {
        const data = await res.json()
        setTokens(data.access, data.refresh)
        window.location.href = "/dashboard"
      }
    } catch {
      setError("No se pudo conectar con el servidor")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow p-8">
        <h1 className="text-2xl font-semibold text-center mb-6">Iniciar sesión</h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700">
              Usuario
            </label>
            <input
              id="username"
              type="text"
              required
              className="w-full mt-1 px-4 py-2 border rounded-md"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
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
              className="w-full mt-1 px-4 py-2 border rounded-md"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>

          {error && <p className="text-red-600 text-sm">{error}</p>}

          <div className="flex flex-row flex-wrap items-center justify-center gap-2 pt-1">
            <button
              type="submit"
              disabled={loading}
              className="bg-[#0c1b3f] text-white px-6 py-2 text-sm rounded-md hover:bg-[#0a1736] disabled:opacity-70 shrink-0"
            >
              {loading ? "Ingresando..." : "Ingresar"}
            </button>
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <span aria-hidden="true">|</span>
              <a
                href="/forgot-password"
                className="text-blue-600 hover:underline whitespace-nowrap"
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
