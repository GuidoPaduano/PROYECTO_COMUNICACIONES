"use client"

import Link from "next/link"
import { use, useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../../../_lib/auth"
import { ChevronLeft, Bell, Mail, Users, Gavel } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

/* ======================== Helpers HTTP ======================== */
async function fetchJSON(url, opts) {
  const res = await authFetch(url, { ...opts, headers: { Accept: "application/json", ...(opts?.headers || {}) } })
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, status: res.status, data }
}

function fmtFecha(iso) {
  if (!iso) return "—"
  const d = new Date(iso)
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
}

/* ======================== Alumno id helpers ======================== */
async function getAlumnoIdsFromAny(idParam) {
  const tries = [
    `/alumnos/${encodeURIComponent(idParam)}/`,
    `/alumnos/detalle/${encodeURIComponent(idParam)}/`,
    `/alumno/${encodeURIComponent(idParam)}/`,
    `/perfil_alumno/${encodeURIComponent(idParam)}/`,
    `/api/alumnos/${encodeURIComponent(idParam)}/`,
  ]
  for (const url of tries) {
    try {
      const r = await fetchJSON(url)
      if (!r.ok) continue
      const obj = r.data || {}
      const a = obj.alumno || obj
      const pk = a?.id ?? obj?.id
      const code = a?.id_alumno ?? obj?.id_alumno ?? idParam
      if (pk || code) return { detail: obj, pk, code }
    } catch {}
  }
  return { detail: null, pk: null, code: idParam }
}

/* ======================== Sanciones fetch ======================== */
async function getSancionesByPkOrCode(pk, code) {
  const urls = [
    pk && `/alumnos/${pk}/sanciones/`,
    pk && `/sanciones/?alumno=${encodeURIComponent(pk)}`,
    code && `/sanciones/?alumno=${encodeURIComponent(code)}`,
    code && `/api/sanciones/?alumno=${encodeURIComponent(code)}`,
    pk && `/api/alumnos/${encodeURIComponent(pk)}/sanciones/`,
    code && `/alumnos/codigo/${encodeURIComponent(code)}/sanciones/`,
  ].filter(Boolean)

  for (const u of urls) {
    try {
      const r = await fetchJSON(u)
      if (!r.ok) continue
      const arr = Array.isArray(r.data) ? r.data : (r.data?.sanciones || r.data?.results || [])
      if (Array.isArray(arr)) return arr
    } catch {}
  }
  return []
}

/* ======================== Page ======================== */
export default function AlumnoSancionesPage({ params }) {
  useAuthGuard()
  const { alumnoId } = use(params)

  const [me, setMe] = useState(null)
  const [unreadCount, setUnreadCount] = useState(0)

  const [sanciones, setSanciones] = useState([])
  const [buscar, setBuscar] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  // header info
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const r = await fetchJSON("/auth/whoami/")
        if (alive && r.ok) setMe(r.data)
        const mu = await fetchJSON("/mensajes/unread_count/")
        if (alive && mu.ok) setUnreadCount(mu.data?.count ?? 0)
      } catch {}
    })()
    return () => { alive = false }
  }, [])

  // Cargar sanciones
  useEffect(() => {
    let alive = true
    setLoading(true); setError("")
    ;(async () => {
      try {
        const { pk, code } = await getAlumnoIdsFromAny(alumnoId)
        if (!alive) return
        const s = await getSancionesByPkOrCode(pk, code)
        if (!alive) return
        setSanciones(Array.isArray(s) ? s : [])
      } catch (e) {
        if (alive) setError(e?.message || "No se pudieron cargar las sanciones.")
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [alumnoId])

  const list = useMemo(() => {
    let arr = Array.isArray(sanciones) ? sanciones.slice() : []
    if (buscar.trim()) {
      const q = buscar.trim().toLowerCase()
      arr = arr.filter(s =>
        (s.asunto || "").toLowerCase().includes(q) ||
        (s.mensaje || "").toLowerCase().includes(q)
      )
    }
    arr.sort((a,b) => {
      const da = new Date(a.fecha || a.creado_en || 0).getTime()
      const db = new Date(b.fecha || b.creado_en || 0).getTime()
      return db - da
    })
    return arr
  }, [sanciones, buscar])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      <Topbar unreadCount={unreadCount} me={me} />

      <div className="max-w-7xl mx-auto p-6">
        {error ? (
          <div className="p-4 bg-red-50 text-red-700 rounded-lg border border-red-200">{error}</div>
        ) : (
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
            <CardContent className="p-6">
              <div className="flex items-start gap-4 mb-4">
                <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                  <Gavel className="h-6 w-6 text-blue-600" />
                </div>
                <div className="flex-1">
                  <h3 className="tile-title">Mis sanciones</h3>
                  <p className="tile-subtitle">Listado de sanciones registradas para el alumno</p>
                </div>
              </div>

              {/* Buscar */}
              <div className="mb-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <Label htmlFor="buscar" className="text-xs text-gray-600">Buscar</Label>
                  <input
                    id="buscar"
                    className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                    placeholder="Asunto o detalle…"
                    value={buscar}
                    onChange={(e) => setBuscar(e.target.value)}
                  />
                </div>
              </div>

              {/* Tabla / lista */}
              {loading ? (
                <p className="text-sm text-gray-500">Cargando sanciones…</p>
              ) : list.length === 0 ? (
                <div className="text-sm text-gray-600">No hay sanciones registradas.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-600 border-b">
                        <th className="py-2 pr-4">Fecha</th>
                        <th className="py-2 pr-4">Asunto</th>
                        <th className="py-2 pr-4">Detalle</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((s, i) => (
                        <tr key={s.id || i} className="border-b last:border-b-0">
                          <td className="py-2 pr-4">{fmtFecha(s.fecha || s.creado_en)}</td>
                          <td className="py-2 pr-4">{s.asunto || "—"}</td>
                          <td className="py-2 pr-4">{s.mensaje || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

/* ======================== Topbar ======================== */

function Topbar({ unreadCount, me }) {
  const userLabel =
    (me?.full_name && String(me.full_name).trim()) ||
    me?.username ||
    [me?.user?.first_name, me?.user?.last_name].filter(Boolean).join(" ") ||
    "Usuario"

  return (
    <div className="bg-blue-600 text-white px-6 py-4">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center overflow-hidden">
            <img
              src={LOGO_SRC}
              alt="Escuela Santa Teresa"
              className="h-full w-full object-contain"
            />
          </div>
          <h1 className="text-xl font-semibold">Mis sanciones</h1>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/dashboard">
            <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
              <ChevronLeft className="h-4 w-4" />
              Volver al panel
            </Button>
          </Link>

          <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
            <Bell className="h-5 w-5" />
          </Button>

          <div className="relative">
            <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
              <Mail className="h-5 w-5" />
            </Button>
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 text-[10px] leading-none px-1.5 py-0.5 rounded-full bg-red-600 text-white border border-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </div>

          <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
            <Users className="h-4 w-4" />
            {userLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
