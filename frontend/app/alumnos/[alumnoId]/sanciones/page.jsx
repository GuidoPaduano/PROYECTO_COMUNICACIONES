"use client"

import { use, useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../../../_lib/auth"
import { Gavel } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"

async function fetchJSON(url, opts) {
  const res = await authFetch(url, {
    ...opts,
    headers: { Accept: "application/json", ...(opts?.headers || {}) },
  })
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, status: res.status, data }
}

function fmtFecha(iso) {
  if (!iso) return "-"
  const d = new Date(iso)
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
}

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
      const arr = Array.isArray(r.data) ? r.data : r.data?.sanciones || r.data?.results || []
      if (Array.isArray(arr)) return arr
    } catch {}
  }
  return []
}

export default function AlumnoSancionesPage({ params }) {
  useAuthGuard()
  const { alumnoId } = use(params)

  const [sanciones, setSanciones] = useState([])
  const [buscar, setBuscar] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError("")
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
    return () => {
      alive = false
    }
  }, [alumnoId])

  const list = useMemo(() => {
    let arr = Array.isArray(sanciones) ? sanciones.slice() : []
    if (buscar.trim()) {
      const q = buscar.trim().toLowerCase()
      arr = arr.filter(
        (s) => (s.asunto || "").toLowerCase().includes(q) || (s.mensaje || "").toLowerCase().includes(q)
      )
    }
    arr.sort((a, b) => {
      const da = new Date(a.fecha || a.creado_en || 0).getTime()
      const db = new Date(b.fecha || b.creado_en || 0).getTime()
      return db - da
    })
    return arr
  }, [sanciones, buscar])

  return (
    <div className="space-y-6">
      {error ? (
        <div className="surface-card surface-card-pad text-red-700">{error}</div>
      ) : (
        <Card>
          <CardContent className="space-y-4">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-indigo-50 rounded-lg flex items-center justify-center flex-shrink-0">
                <Gavel className="h-6 w-6 text-indigo-600" />
              </div>
              <div className="flex-1">
                <h3 className="tile-title">Mis sanciones</h3>
                <p className="tile-subtitle">Listado de sanciones registradas para el alumno</p>
              </div>
            </div>

            <div className="max-w-xs">
              <Label htmlFor="buscar" className="text-xs text-gray-600">
                Buscar
              </Label>
              <Input
                id="buscar"
                className="mt-1"
                placeholder="Asunto o detalle"
                value={buscar}
                onChange={(e) => setBuscar(e.target.value)}
              />
            </div>

            {loading ? (
              <p className="text-sm text-gray-500">Cargando sanciones...</p>
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
                        <td className="py-2 pr-4">{s.asunto || "-"}</td>
                        <td className="py-2 pr-4">{s.mensaje || "-"}</td>
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
  )
}
