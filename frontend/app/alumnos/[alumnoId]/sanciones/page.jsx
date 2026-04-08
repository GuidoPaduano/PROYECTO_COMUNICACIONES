"use client"

import { use, useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, useSessionContext } from "../../../_lib/auth"
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

const ALUMNO_SANCIONES_RESOURCE_MAX_AGE_MS = 15000
const ALUMNO_DETAIL_CACHE_PREFIX = "alumno_detail_cache:"
const ALUMNO_DETAIL_CACHE_TTL_MS = 5 * 60 * 1000
const SANCIONES_CACHE_PREFIX = "alumno_sanciones_cache:"
const ALUMNO_DATA_CACHE_TTL_MS = 5 * 60 * 1000
const alumnoSancionesResourceCache = new Map()
const alumnoSancionesResourcePromises = new Map()

function fmtFecha(iso) {
  if (!iso) return "-"
  const d = new Date(iso)
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
}

function safeGetLSJson(key) {
  try {
    if (typeof window === "undefined") return null
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function safeSetLSJson(key, value) {
  try {
    if (typeof window === "undefined") return
    localStorage.setItem(key, JSON.stringify(value))
  } catch {}
}

function getCachedAlumnoDetail(idParam) {
  if (!idParam) return null
  const cached = safeGetLSJson(`${ALUMNO_DETAIL_CACHE_PREFIX}${idParam}`)
  if (!cached?.data) return null
  if (cached.ts && Date.now() - cached.ts > ALUMNO_DETAIL_CACHE_TTL_MS) return null
  return cached.data
}

function setCachedAlumnoDetail(idParam, data) {
  if (!idParam || !data) return
  safeSetLSJson(`${ALUMNO_DETAIL_CACHE_PREFIX}${idParam}`, {
    ts: Date.now(),
    data,
  })
}

function getCachedSancionesList(idParam) {
  if (!idParam) return null
  const cached = safeGetLSJson(`${SANCIONES_CACHE_PREFIX}${idParam}`)
  if (!cached?.data) return null
  if (cached.ts && Date.now() - cached.ts > ALUMNO_DATA_CACHE_TTL_MS) return null
  return Array.isArray(cached.data) ? cached.data : null
}

function setCachedSancionesList(idParam, data) {
  if (!idParam || !Array.isArray(data)) return
  safeSetLSJson(`${SANCIONES_CACHE_PREFIX}${idParam}`, {
    ts: Date.now(),
    data,
  })
}

async function loadAlumnoSancionesResource(cacheKey, loader, options = {}) {
  const force = options?.force === true
  const maxAgeMs =
    Number.isFinite(Number(options?.maxAgeMs)) && Number(options?.maxAgeMs) > 0
      ? Number(options.maxAgeMs)
      : ALUMNO_SANCIONES_RESOURCE_MAX_AGE_MS
  const now = Date.now()

  if (!force) {
    const cached = alumnoSancionesResourceCache.get(cacheKey)
    if (cached && cached.expiresAt > now) return cached.data

    const pending = alumnoSancionesResourcePromises.get(cacheKey)
    if (pending) return pending
  }

  const promise = (async () => {
    const data = await loader()
    alumnoSancionesResourceCache.set(cacheKey, {
      data,
      expiresAt: Date.now() + maxAgeMs,
    })
    return data
  })()

  alumnoSancionesResourcePromises.set(cacheKey, promise)

  try {
    return await promise
  } finally {
    if (alumnoSancionesResourcePromises.get(cacheKey) === promise) {
      alumnoSancionesResourcePromises.delete(cacheKey)
    }
  }
}

async function getAlumnoIdsFromAny(idParam) {
  const cached = getCachedAlumnoDetail(idParam)
  if (cached) {
    const pk = cached?.id ?? null
    const code = cached?.id_alumno ?? idParam
    if (pk || code) return { detail: cached, pk, code }
  }
  try {
    const r = await fetchJSON(`/api/alumnos/${encodeURIComponent(idParam)}/`)
    if (r.ok) {
      const obj = r.data || {}
      const pk = obj?.id ?? null
      const code = obj?.id_alumno ?? idParam
      if (pk || code) {
        setCachedAlumnoDetail(idParam, obj)
        return { detail: obj, pk, code }
      }
    }
  } catch {}
  return { detail: null, pk: null, code: idParam }
}

async function getSancionesByPkOrCode(pk, code) {
  const alumnoRef = pk ?? code
  if (alumnoRef == null || String(alumnoRef).trim() === "") return []

  const cached = getCachedSancionesList(alumnoRef)
  if (cached) return cached

  try {
    const r = await fetchJSON(`/api/sanciones/?alumno=${encodeURIComponent(alumnoRef)}`)
    if (r.ok) {
      const results = Array.isArray(r.data?.results) ? r.data.results : []
      setCachedSancionesList(alumnoRef, results)
      return results
    }
  } catch {}
  return []
}

export default function AlumnoSancionesPage({ params }) {
  useAuthGuard()
  const session = useSessionContext()
  const { alumnoId } = use(params)
  const alumnoSancionesScopeKey = useMemo(
    () => `${session?.username || "anon"}:${session?.school?.id || "default"}`,
    [session?.school?.id, session?.username]
  )

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
        const { pk, code } = await loadAlumnoSancionesResource(
          `alumno-sanciones-detail:${alumnoSancionesScopeKey}:${String(alumnoId)}`,
          async () => await getAlumnoIdsFromAny(alumnoId)
        )
        if (!alive) return
        const s = await loadAlumnoSancionesResource(
          `alumno-sanciones-list:${alumnoSancionesScopeKey}:${String(pk ?? code ?? alumnoId)}`,
          async () => await getSancionesByPkOrCode(pk, code)
        )
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
  }, [alumnoId, alumnoSancionesScopeKey])

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
              <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 school-primary-soft-icon">
                <Gavel className="h-6 w-6" />
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
