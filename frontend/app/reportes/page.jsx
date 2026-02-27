"use client"

import { useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  BookOpenText,
  Percent,
  TrendingUp,
} from "lucide-react"

import { authFetch, useAuthGuard } from "../_lib/auth"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function normalizeRole(me) {
  const groups = Array.isArray(me?.groups) ? me.groups : []
  if (me?.is_superuser) return "Superuser"
  if (groups.includes("Padres")) return "Padres"
  if (groups.includes("Alumnos")) return "Alumnos"
  if (groups.includes("Profesores")) return "Profesores"
  if (groups.includes("Preceptores")) return "Preceptores"
  return "SinRol"
}

function normalizeCursoItem(item) {
  if (!item) return null
  if (typeof item === "string") {
    return { id: item, label: item }
  }
  const id = item.id || item.curso || item.codigo || item.value
  if (!id) return null
  return {
    id: String(id),
    label: String(item.nombre || item.label || item.curso || id),
  }
}

function dedupeCursos(items) {
  const out = []
  const seen = new Set()
  for (const raw of items || []) {
    const parsed = normalizeCursoItem(raw)
    if (!parsed) continue
    if (seen.has(parsed.id)) continue
    seen.add(parsed.id)
    out.push(parsed)
  }
  return out
}

function parseCursosPayload(payload) {
  if (Array.isArray(payload)) return dedupeCursos(payload)
  if (Array.isArray(payload?.cursos)) return dedupeCursos(payload.cursos)
  if (Array.isArray(payload?.results)) return dedupeCursos(payload.results)
  return []
}

function toMateriaRows(report) {
  const raw = report?.notas?.promedios_por_materia || {}
  return Object.entries(raw)
    .map(([materia, promedio]) => ({ materia, promedio }))
    .filter((x) => x.promedio != null)
    .sort((a, b) => Number(a.promedio) - Number(b.promedio))
}

function toNotasEvolution(report) {
  const source = report?.notas?.evolucion_mensual || {}
  return Object.entries(source)
    .map(([mes, promedio]) => ({ mes, value: Number(promedio) }))
    .filter((x) => Number.isFinite(x.value))
    .sort((a, b) => a.mes.localeCompare(b.mes))
}

function toAsistenciaEvolution(report) {
  const source = report?.asistencias?.evolucion_mensual || {}
  return Object.entries(source)
    .map(([mes, obj]) => {
      const ausentes = Number(obj?.ausentes || 0)
      const tardes = Number(obj?.tardes || 0)
      return { mes, value: ausentes + tardes }
    })
    .filter((x) => Number.isFinite(x.value))
    .sort((a, b) => a.mes.localeCompare(b.mes))
}

function formatValueNumber(value, suffix = "") {
  if (value == null || Number.isNaN(Number(value))) return "N/D"
  const n = Number(value)
  return `${n.toFixed(2)}${suffix}`
}

function formatShortMonth(isoMonth) {
  const text = String(isoMonth || "")
  const [year, month] = text.split("-")
  if (!year || !month) return text
  return `${month}/${year.slice(2)}`
}

function EmptyHint({ text }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-600">
      {text}
    </div>
  )
}

function KpiCard({ icon, title, value, helper }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription className="flex items-center gap-2 text-slate-600">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
            {icon}
          </span>
          {title}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold text-slate-900">{value}</div>
        {helper ? <p className="mt-1 text-xs text-slate-500">{helper}</p> : null}
      </CardContent>
    </Card>
  )
}

function LineChartCard({ title, subtitle, data }) {
  const width = 680
  const height = 240
  const pad = 26
  const max = Math.max(...data.map((d) => d.value), 1)
  const min = Math.min(...data.map((d) => d.value), 0)
  const range = Math.max(max - min, 1)

  const points = data.map((d, idx) => {
    const x =
      data.length <= 1
        ? width / 2
        : pad + (idx * (width - pad * 2)) / (data.length - 1)
    const y = height - pad - ((d.value - min) / range) * (height - pad * 2)
    return { ...d, x, y }
  })
  const pointString = points.map((p) => `${p.x},${p.y}`).join(" ")

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{subtitle}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.length === 0 ? (
          <EmptyHint text="No hay datos para graficar en este periodo." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <svg
                viewBox={`0 0 ${width} ${height}`}
                className="min-w-[640px]"
                role="img"
                aria-label={title}
              >
                <line
                  x1={pad}
                  y1={height - pad}
                  x2={width - pad}
                  y2={height - pad}
                  stroke="#CBD5E1"
                  strokeWidth="1.5"
                />
                <polyline
                  fill="none"
                  stroke="#0F172A"
                  strokeWidth="3"
                  points={pointString}
                />
                {points.map((p) => (
                  <circle key={`${p.mes}-${p.value}`} cx={p.x} cy={p.y} r="4" fill="#0F172A" />
                ))}
              </svg>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 sm:grid-cols-4">
              {points.map((p) => (
                <div key={`${p.mes}-legend`} className="rounded-md bg-slate-100 px-2 py-1">
                  <div className="font-medium">{formatShortMonth(p.mes)}</div>
                  <div>{Number(p.value).toFixed(2)}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function BarsCard({ data }) {
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Distribucion de notas</CardTitle>
        <CardDescription>Rangos 1-3, 4-6 y 7-10</CardDescription>
      </CardHeader>
      <CardContent>
        {data.every((d) => d.value === 0) ? (
          <EmptyHint text="No hay notas numericas para calcular la distribucion." />
        ) : (
          <div className="space-y-3">
            {data.map((d) => {
              const width = `${Math.max((d.value / max) * 100, 4)}%`
              return (
                <div key={d.label}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-slate-700">{d.label}</span>
                    <span className="text-slate-500">{d.value}</span>
                  </div>
                  <div className="h-3 rounded-full bg-slate-100">
                    <div
                      className="h-3 rounded-full bg-slate-800 transition-all"
                      style={{ width }}
                    />
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

export default function ReportesPage() {
  useAuthGuard()

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
  const isPreceptor = role === "Preceptores"
  const isSuper = role === "Superuser"
  const requiresCurso = isProfesor || isPreceptor || isSuper

  useEffect(() => {
    let alive = true
    ;(async () => {
      setProfileLoading(true)
      setError("")
      try {
        const meRes = await authFetch("/auth/whoami/")
        const me = await meRes.json().catch(() => ({}))
        if (!meRes.ok) {
          throw new Error(me?.detail || `Error ${meRes.status}`)
        }
        if (!alive) return
        const userRole = normalizeRole(me)
        setRole(userRole)
      } catch (err) {
        if (!alive) return
        setError(err?.message || "No se pudo cargar el perfil.")
      } finally {
        if (alive) setProfileLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (!requiresCurso) return
    let alive = true
    ;(async () => {
      try {
        const urls =
          isPreceptor
            ? ["/preceptor/asistencias/cursos/", "/preceptor/cursos/"]
            : ["/notas/catalogos/", "/alumnos/cursos/"]
        let parsed = []
        for (const url of urls) {
          const res = await authFetch(url)
          if (!res.ok) continue
          const payload = await res.json().catch(() => ({}))
          parsed = parseCursosPayload(payload)
          if (parsed.length > 0) break
        }
        if (!alive) return
        setCursos(parsed)
        if (parsed.length > 0 && !cursoSel) {
          setCursoSel(parsed[0].id)
        }
      } catch {
        if (!alive) return
        setCursos([])
      }
    })()
    return () => {
      alive = false
    }
  }, [requiresCurso, isPreceptor, cursoSel])

  useEffect(() => {
    if (profileLoading) return
    if (role === "SinRol") return
    if (!(isPadre || isAlumno || isProfesor || isPreceptor || isSuper)) return
    if (requiresCurso && !cursoSel) return

    let alive = true
    ;(async () => {
      setReportLoading(true)
      setError("")
      try {
        const params = new URLSearchParams()
        if (cuatrimestre !== "all") params.set("cuatrimestre", cuatrimestre)
        if (isPadre && alumnoSel) params.set("alumno_id", alumnoSel)
        const qs = params.toString()

        const path = isPadre || isAlumno
          ? `/reportes/mis-estadisticas/${qs ? `?${qs}` : ""}`
          : `/reportes/curso/${encodeURIComponent(cursoSel)}/${qs ? `?${qs}` : ""}`

        const res = await authFetch(path)
        const payload = await res.json().catch(() => ({}))
        if (!res.ok) {
          throw new Error(payload?.detail || `Error ${res.status}`)
        }
        if (!alive) return

        setReport(payload)

        if (isPadre) {
          const hijos = Array.isArray(payload?.alumnos) ? payload.alumnos : []
          setAlumnos(hijos)
          const activo = payload?.alumno_activo
          const activeId = String(activo?.id || activo?.id_alumno || "")
          if (activeId && activeId !== String(alumnoSel || "")) {
            setAlumnoSel(activeId)
          } else if (!alumnoSel && hijos.length > 0) {
            setAlumnoSel(String(hijos[0]?.id || hijos[0]?.id_alumno || ""))
          }
        }
      } catch (err) {
        if (!alive) return
        setReport(null)
        setError(err?.message || "No se pudo cargar el reporte.")
      } finally {
        if (alive) setReportLoading(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [
    role,
    isPadre,
    isAlumno,
    isProfesor,
    isPreceptor,
    isSuper,
    profileLoading,
    requiresCurso,
    cursoSel,
    alumnoSel,
    cuatrimestre,
  ])

  const materiaRows = useMemo(() => toMateriaRows(report), [report])
  const worstMateria = useMemo(() => (materiaRows.length ? materiaRows[0] : null), [materiaRows])

  const notasEvolution = useMemo(() => toNotasEvolution(report), [report])
  const asistEvolution = useMemo(() => toAsistenciaEvolution(report), [report])
  const evolutionData = notasEvolution.length ? notasEvolution : asistEvolution

  const distribucion = useMemo(() => {
    const dist = report?.notas?.distribucion_notas || {}
    return [
      { label: "1-3", value: Number(dist?.rango_1_3 || 0) },
      { label: "4-6", value: Number(dist?.rango_4_6 || 0) },
      { label: "7-10", value: Number(dist?.rango_7_10 || 0) },
    ]
  }, [report])

  const promedioGeneral = report?.notas?.promedio_general
  const inasistencias = Number(report?.asistencias?.totales?.ausente || 0)
  const porcentajeAsistencia = report?.asistencias?.porcentaje_asistencia

  const reportIsEmpty = useMemo(() => {
    if (!report) return false
    const notasEmpty =
      promedioGeneral == null &&
      materiaRows.length === 0 &&
      distribucion.every((x) => x.value === 0)
    const asisTotals = report?.asistencias?.totales || {}
    const asisEmpty =
      Number(asisTotals?.presente || 0) === 0 &&
      Number(asisTotals?.ausente || 0) === 0 &&
      Number(asisTotals?.tarde || 0) === 0
    return notasEmpty && asisEmpty
  }, [report, promedioGeneral, materiaRows, distribucion])

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Cuatrimestre
              </label>
              <select
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                value={cuatrimestre}
                onChange={(e) => setCuatrimestre(e.target.value)}
              >
                <option value="all">Todos</option>
                <option value="1">1</option>
                <option value="2">2</option>
              </select>
            </div>

            {requiresCurso ? (
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Curso
                </label>
                <select
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                  value={cursoSel}
                  onChange={(e) => setCursoSel(e.target.value)}
                >
                  {cursos.length === 0 ? (
                    <option value="">Sin cursos</option>
                  ) : (
                    cursos.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))
                  )}
                </select>
              </div>
            ) : null}

            {isPadre ? (
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Alumno
                </label>
                <select
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                  value={alumnoSel}
                  onChange={(e) => setAlumnoSel(e.target.value)}
                >
                  {alumnos.length === 0 ? (
                    <option value="">Sin alumnos</option>
                  ) : (
                    alumnos.map((a) => (
                      <option key={a.id || a.id_alumno} value={a.id || a.id_alumno}>
                        {a.nombre} ({a.curso})
                      </option>
                    ))
                  )}
                </select>
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {profileLoading || reportLoading ? (
        <EmptyHint text="Cargando reportes..." />
      ) : null}

      {error ? (
        <Card className="border-red-200">
          <CardContent className="flex items-start gap-3 pt-6 text-sm text-red-700">
            <AlertTriangle className="mt-0.5 h-4 w-4" />
            <div className="flex-1">
              <div>{error}</div>
              <Button
                className="mt-3"
                variant="outline"
                onClick={() => {
                  setReport(null)
                  setError("")
                  setProfileLoading(true)
                  window.location.reload()
                }}
              >
                Reintentar
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {!profileLoading && !reportLoading && !error && reportIsEmpty ? (
        <EmptyHint text="No hay datos suficientes para generar reportes todavia." />
      ) : null}

      {!profileLoading && !reportLoading && !error && report ? (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              icon={<TrendingUp className="h-4 w-4" />}
              title="Promedio general"
              value={formatValueNumber(promedioGeneral)}
            />
            <KpiCard
              icon={<AlertTriangle className="h-4 w-4" />}
              title="Inasistencias"
              value={String(inasistencias)}
              helper="Total de ausentes"
            />
            <KpiCard
              icon={<Percent className="h-4 w-4" />}
              title="% asistencia"
              value={formatValueNumber(porcentajeAsistencia, "%")}
            />
            <KpiCard
              icon={<BookOpenText className="h-4 w-4" />}
              title="Materia mas floja"
              value={worstMateria ? `${worstMateria.materia} (${Number(worstMateria.promedio).toFixed(2)})` : "N/D"}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <LineChartCard
              title="Evolucion mensual"
              subtitle={
                notasEvolution.length
                  ? "Promedio mensual de notas numericas"
                  : "Ausentes + tardes por mes"
              }
              data={evolutionData}
            />
            <BarsCard data={distribucion} />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Promedios por materia</CardTitle>
              <CardDescription>Ordenado de menor a mayor promedio</CardDescription>
            </CardHeader>
            <CardContent>
              {materiaRows.length === 0 ? (
                <EmptyHint text="No hay promedios por materia para mostrar." />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Materia</TableHead>
                      <TableHead className="text-right">Promedio</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {materiaRows.map((row) => (
                      <TableRow key={row.materia}>
                        <TableCell className="font-medium text-slate-800">{row.materia}</TableCell>
                        <TableCell className="text-right">{Number(row.promedio).toFixed(2)}</TableCell>
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
