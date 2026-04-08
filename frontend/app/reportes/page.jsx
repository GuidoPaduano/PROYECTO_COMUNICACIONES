"use client"

import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react"

import { authFetch, getSessionProfile, useAuthGuard, useSessionContext } from "../_lib/auth"
import {
  getCourseDisplayName,
  getCourseLabel,
  getCourseSchoolCourseId,
  loadCourseCatalog,
} from "../_lib/courses"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

function buildReportesSessionProfile(session) {
  const groups = Array.isArray(session?.groups) ? session.groups : []
  const username = String(session?.username || "").trim()
  const fullName = String(session?.userLabel || "").trim()
  const hasRoleData = groups.length > 0 || !!session?.isSuperuser || !!username || !!fullName
  if (!hasRoleData) return null
  return {
    username,
    full_name: fullName,
    groups,
    is_superuser: !!session?.isSuperuser,
    rol: String(session?.role || "").trim(),
    school: session?.school || null,
  }
}

function normalizeRole(me) {
  const groups = Array.isArray(me?.groups) ? me.groups : []
  if (me?.is_superuser) return "Superuser"
  if (groups.includes("Padres")) return "Padres"
  if (groups.includes("Alumnos") || groups.includes("Alumno")) return "Alumnos"
  if (groups.includes("Profesores")) return "Profesores"
  if (groups.includes("Directivos") || groups.includes("Directivo")) return "Directivos"
  if (groups.includes("Preceptores") || groups.includes("Preceptor")) return "Preceptores"
  return "SinRol"
}

function fmtPct(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return "0.00%"
  return `${n.toFixed(2)}%`
}

function EmptyHint({ text }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-600">
      {text}
    </div>
  )
}

function KpiCard({ icon, title, value, helper, accentClass = "bg-slate-100 text-slate-700" }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription className="flex items-center gap-3 text-slate-700">
          <span className={`inline-flex h-8 w-8 items-center justify-center rounded-lg ${accentClass}`}>
            {icon}
          </span>
          <span className="text-xl font-extrabold tracking-tight text-slate-900">{title}</span>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold text-slate-900">{value}</div>
        {helper ? <div className="mt-1 text-xs text-slate-500">{helper}</div> : null}
      </CardContent>
    </Card>
  )
}

function DistribucionEstados({ conteos }) {
  const total = Math.max(
    Number(conteos?.TEA || 0) + Number(conteos?.TEP || 0) + Number(conteos?.TED || 0),
    1
  )
  const rows = [
    { key: "TEA", label: "TEA", color: "bg-emerald-500", value: Number(conteos?.TEA || 0) },
    { key: "TEP", label: "TEP", color: "bg-amber-500", value: Number(conteos?.TEP || 0) },
    { key: "TED", label: "TED", color: "bg-rose-500", value: Number(conteos?.TED || 0) },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Distribucion general</CardTitle>
        <CardDescription>Conteo por estado TEA/TEP/TED</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {rows.map((row) => (
          <div key={row.key}>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="font-medium text-slate-700">{row.label}</span>
              <span className="text-slate-600">{row.value}</span>
            </div>
            <div className="h-3 rounded bg-slate-100">
              <div className={`h-3 rounded ${row.color}`} style={{ width: `${(row.value / total) * 100}%` }} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function EvolucionMensual({ rows }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Evolucion mensual</CardTitle>
        <CardDescription>Barras apiladas por TEA / TEP / TED</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <EmptyHint text="No hay datos mensuales para mostrar." />
        ) : (
          <div className="space-y-3">
            {rows.map((row) => {
              const total = Math.max(Number(row.total || 0), 1)
              const tea = Number(row.TEA_count || 0)
              const tep = Number(row.TEP_count || 0)
              const ted = Number(row.TED_count || 0)
              return (
                <div key={row.mes}>
                  <div className="mb-1 flex items-center justify-between text-xs text-slate-600">
                    <span>{row.mes}</span>
                    <span>Total: {row.total}</span>
                  </div>
                  <div className="flex h-4 overflow-hidden rounded bg-slate-100">
                    <div className="bg-emerald-500" style={{ width: `${(tea / total) * 100}%` }} />
                    <div className="bg-amber-500" style={{ width: `${(tep / total) * 100}%` }} />
                    <div className="bg-rose-500" style={{ width: `${(ted / total) * 100}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

const REPORTES_RESOURCE_MAX_AGE_MS = 30000
const REPORTES_DYNAMIC_RESOURCE_MAX_AGE_MS = 15000
const reportesResourceCache = new Map()
const reportesResourcePromises = new Map()

async function loadReportesResource(cacheKey, loader, maxAgeMs = REPORTES_RESOURCE_MAX_AGE_MS) {
  const key = String(cacheKey || "").trim()
  if (!key || typeof loader !== "function") {
    return await loader()
  }

  const cached = reportesResourceCache.get(key)
  if (cached && cached.expiresAt > Date.now()) {
    return cached.data
  }

  if (reportesResourcePromises.has(key)) {
    return await reportesResourcePromises.get(key)
  }

  const promise = (async () => {
    const data = await loader()
    reportesResourceCache.set(key, {
      data,
      expiresAt: Date.now() + maxAgeMs,
    })
    return data
  })()

  reportesResourcePromises.set(key, promise)

  try {
    return await promise
  } finally {
    if (reportesResourcePromises.get(key) === promise) {
      reportesResourcePromises.delete(key)
    }
  }
}

export default function ReportesPage() {
  useAuthGuard()
  const session = useSessionContext()

  const [profileLoading, setProfileLoading] = useState(true)
  const [reportLoading, setReportLoading] = useState(false)
  const [error, setError] = useState("")

  const [role, setRole] = useState("SinRol")
  const [cursos, setCursos] = useState([])
  const [cursoSel, setCursoSel] = useState("")
  const [alumnos, setAlumnos] = useState([])
  const [alumnoSel, setAlumnoSel] = useState("")
  const [cuatrimestre, setCuatrimestre] = useState("all")
  const [report, setReport] = useState(null)

  const isPadre = role === "Padres"
  const isAlumno = role === "Alumnos"
  const isProfesor = role === "Profesores"
  const isDirectivo = role === "Directivos"
  const isPreceptor = role === "Preceptores"
  const isSuper = role === "Superuser"
  const usaCurso = isProfesor || isPreceptor || isDirectivo || isSuper
  const cursoSelSchoolCourseId = useMemo(
    () => (cursoSel ? getCourseSchoolCourseId(cursoSel, cursos) : null),
    [cursoSel, cursos]
  )
  const reportesScopeKey = useMemo(
    () =>
      `${session?.username || "anon"}:${session?.school?.id || "default"}:${role || "base"}`,
    [role, session?.school?.id, session?.username]
  )
  const sessionBootstrapProfile = useMemo(
    () => buildReportesSessionProfile(session),
    [session?.groups, session?.isSuperuser, session?.role, session?.school, session?.userLabel, session?.username]
  )
  const courseCatalogCacheKey = useMemo(
    () => `reportes-cursos:${reportesScopeKey}`,
    [reportesScopeKey]
  )

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        setProfileLoading(true)
        setError("")
        const me = sessionBootstrapProfile || (await getSessionProfile())
        if (!alive) return
        setRole(normalizeRole(me))
      } catch (e) {
        if (!alive) return
        setError(e?.message || "No se pudo cargar el perfil")
      } finally {
        if (alive) setProfileLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [sessionBootstrapProfile])

  useEffect(() => {
    if (!usaCurso) return
    let alive = true
    ;(async () => {
      try {
        const urls = isProfesor || isPreceptor
          ? ["/cursos/mis-cursos/", "/preceptor/cursos/"]
          : ["/notas/catalogos/", "/alumnos/cursos/"]
        const found = await loadCourseCatalog({
          fetcher: authFetch,
          urls,
          cacheKey: courseCatalogCacheKey,
        })

        if (!alive) return
        setCursos(found)
        if (found.length && !cursoSel) {
          setCursoSel(found[0].value)
        } else if (!found.length) {
          setCursoSel("")
        }
      } catch {
        if (!alive) return
        setCursos([])
        setCursoSel("")
      }
    })()
    return () => {
      alive = false
    }
  }, [usaCurso, isProfesor, isPreceptor, courseCatalogCacheKey, cursoSel])

  useEffect(() => {
    if (profileLoading || !isPadre) return
    let alive = true
    ;(async () => {
      try {
        const hijos = await loadReportesResource(
          `reportes-hijos:${reportesScopeKey}`,
          async () => {
            const res = await authFetch("/padres/mis-hijos/")
            const data = await res.json().catch(() => ({}))
            if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
            return Array.isArray(data?.results) ? data.results : []
          }
        )
        if (!alive) return
        setAlumnos(hijos)

        const current = String(alumnoSel || "")
        const hasCurrent = hijos.some((a) => String(a?.id || a?.id_alumno || "") === current)
        if (hasCurrent) return

        const next = String(hijos[0]?.id || hijos[0]?.id_alumno || "")
        if (next) setAlumnoSel(next)
      } catch (e) {
        if (!alive) return
        setAlumnos([])
        setError(e?.message || "No se pudieron cargar los hijos asociados.")
      }
    })()
    return () => {
      alive = false
    }
  }, [profileLoading, isPadre, alumnoSel, reportesScopeKey])

  useEffect(() => {
    if (profileLoading) return
    if (!(isPadre || isAlumno || isProfesor || isPreceptor || isDirectivo || isSuper)) return
    if (usaCurso && !cursoSel) return
    if (usaCurso && cursoSelSchoolCourseId == null) return
    if (isPadre && !alumnoSel) return

    let alive = true
    ;(async () => {
      try {
        setReportLoading(true)
        setError("")

        const params = new URLSearchParams()
        if (cuatrimestre !== "all") params.set("cuatrimestre", cuatrimestre)
        if (isPadre) params.set("alumno_id", alumnoSel)

        const qs = params.toString()
        const path = isPadre || isAlumno
          ? `/reportes/mis-estadisticas/${qs ? `?${qs}` : ""}`
          : `/reportes/curso/${encodeURIComponent(String(cursoSelSchoolCourseId))}/${qs ? `?${qs}` : ""}`
        const data = await loadReportesResource(
          `reportes-data:${reportesScopeKey}:${path}`,
          async () => {
            const res = await authFetch(path)
            const payload = await res.json().catch(() => ({}))
            if (!res.ok) throw new Error(payload?.detail || `HTTP ${res.status}`)
            return payload
          },
          REPORTES_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
        if (!alive) return

        setReport(data)

        if (isPadre) {
          const hijos = Array.isArray(data?.alumnos) ? data.alumnos : []
          if (hijos.length) setAlumnos(hijos)
        }
      } catch (e) {
        if (!alive) return
        setReport(null)
        setError(e?.message || "No se pudo cargar el reporte")
      } finally {
        if (alive) setReportLoading(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [profileLoading, isPadre, isAlumno, isProfesor, isPreceptor, isDirectivo, isSuper, usaCurso, cursoSel, cursoSelSchoolCourseId, alumnoSel, cuatrimestre])

  const resumen = report?.resumen_notas || { total_evaluaciones: 0, conteos_por_estado: { TEA: 0, TEP: 0, TED: 0 }, porcentajes_por_estado: { TEA: 0, TEP: 0, TED: 0 } }
  const porMateria = Array.isArray(report?.por_materia) ? report.por_materia : []
  const evolucionNotas = Array.isArray(report?.evolucion_mensual_notas) ? report.evolucion_mensual_notas : []
  const empty = useMemo(() => {
    if (!report) return false
    return Number(resumen?.total_evaluaciones || 0) === 0
  }, [report, resumen])

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Cuatrimestre</label>
              <select className="w-full rounded border border-slate-300 px-3 py-2 text-sm" value={cuatrimestre} onChange={(e) => setCuatrimestre(e.target.value)}>
                <option value="all">Todos</option>
                <option value="1">1</option>
                <option value="2">2</option>
              </select>
            </div>

            {usaCurso ? (
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Curso</label>
                <select className="w-full rounded border border-slate-300 px-3 py-2 text-sm" value={cursoSel} onChange={(e) => setCursoSel(e.target.value)}>
                  {cursos.length === 0 ? <option value="">Sin cursos</option> : null}
                  {cursos.map((c) => (
                    <option key={c.value} value={c.value}>{getCourseLabel(c)}</option>
                  ))}
                </select>
              </div>
            ) : null}

            {isPadre && alumnos.length > 1 ? (
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Hijo</label>
                <select className="w-full rounded border border-slate-300 px-3 py-2 text-sm" value={alumnoSel} onChange={(e) => setAlumnoSel(e.target.value)}>
                  {alumnos.map((a) => (
                    <option key={a.id || a.id_alumno} value={a.id || a.id_alumno}>
                      {a.nombre} ({getCourseDisplayName(a) || "Curso s/d"})
                    </option>
                  ))}
                </select>
              </div>
            ) : null}

            {isPadre && alumnos.length === 1 ? (
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Hijo</label>
                <div className="w-full rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                  {alumnos[0]?.nombre} ({getCourseDisplayName(alumnos[0]) || "Curso s/d"})
                </div>
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {profileLoading || reportLoading ? <EmptyHint text="Cargando reportes..." /> : null}

      {error ? (
        <Card className="border-red-200">
          <CardContent className="flex items-start gap-3 pt-6 text-sm text-red-700">
            <AlertTriangle className="mt-0.5 h-4 w-4" />
            <div className="flex-1">
              <div>{error}</div>
              <Button className="mt-3" variant="outline" onClick={() => window.location.reload()}>Reintentar</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {!profileLoading && !reportLoading && !error && empty ? (
        <EmptyHint text="No hay datos para generar este reporte." />
      ) : null}

      {!profileLoading && !reportLoading && !error && report ? (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            <KpiCard
              icon={<CheckCircle2 className="h-4 w-4" />}
              title="TEA"
              value={fmtPct(resumen?.porcentajes_por_estado?.TEA)}
              accentClass="bg-emerald-100 text-emerald-700"
            />
            <KpiCard
              icon={<XCircle className="h-4 w-4" />}
              title="TEP"
              value={fmtPct(resumen?.porcentajes_por_estado?.TEP)}
              accentClass="bg-amber-100 text-amber-700"
            />
            <KpiCard
              icon={<AlertTriangle className="h-4 w-4" />}
              title="TED"
              value={fmtPct(resumen?.porcentajes_por_estado?.TED)}
              accentClass="bg-rose-100 text-rose-700"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <EvolucionMensual rows={evolucionNotas} />
            <DistribucionEstados conteos={resumen?.conteos_por_estado} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Por materia</CardTitle>
              <CardDescription>Resumen TEA/TEP/TED por materia</CardDescription>
            </CardHeader>
            <CardContent>
              {porMateria.length === 0 ? (
                <EmptyHint text="No hay materias para mostrar en este filtro." />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-base font-extrabold text-slate-900">Materia</TableHead>
                      <TableHead className="text-right text-base font-extrabold text-slate-900">TEA</TableHead>
                      <TableHead className="text-right text-base font-extrabold text-slate-900">TEP</TableHead>
                      <TableHead className="text-right text-base font-extrabold text-slate-900">TED</TableHead>
                      <TableHead className="text-right text-base font-extrabold text-slate-900">%TEA</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {porMateria.map((row) => (
                      <TableRow key={`${row.materia_id}-${row.materia_nombre}`}>
                        <TableCell className="font-medium text-slate-800">{row.materia_nombre}</TableCell>
                        <TableCell className="text-right">{row.TEA_count}</TableCell>
                        <TableCell className="text-right">{row.TEP_count}</TableCell>
                        <TableCell className="text-right">{row.TED_count}</TableCell>
                        <TableCell className="text-right">{fmtPct(row.TEA_pct)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

        </>
      ) : null}

      {!profileLoading && !reportLoading && role === "SinRol" ? (
        <Card>
          <CardContent className="pt-6 text-sm text-slate-600">
            Tu usuario no tiene un rol compatible para ver reportes.
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
