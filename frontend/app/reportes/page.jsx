"use client"

import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react"

import { authFetch, useAuthGuard } from "../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

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
  if (typeof item === "string") return { id: item, label: item }
  const id = item?.id || item?.curso || item?.value
  if (!id) return null
  return { id: String(id), label: String(item?.nombre || item?.label || id) }
}

function dedupeCursos(items) {
  const out = []
  const seen = new Set()
  for (const it of items || []) {
    const parsed = normalizeCursoItem(it)
    if (!parsed || seen.has(parsed.id)) continue
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

function KpiCard({ icon, title, value, helper }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription className="flex items-center gap-2 text-slate-600">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
            {icon}
          </span>
          {title}
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
    { key: "TEP", label: "TEP", color: "bg-rose-500", value: Number(conteos?.TEP || 0) },
    { key: "TED", label: "TED", color: "bg-amber-500", value: Number(conteos?.TED || 0) },
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
                    <div className="bg-rose-500" style={{ width: `${(tep / total) * 100}%` }} />
                    <div className="bg-amber-500" style={{ width: `${(ted / total) * 100}%` }} />
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
  const usaCurso = isProfesor || isPreceptor || isSuper

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        setProfileLoading(true)
        setError("")
        const meRes = await authFetch("/auth/whoami/")
        const me = await meRes.json().catch(() => ({}))
        if (!meRes.ok) throw new Error(me?.detail || `HTTP ${meRes.status}`)
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
  }, [])

  useEffect(() => {
    if (!usaCurso) return
    let alive = true
    ;(async () => {
      try {
        const urls = isPreceptor
          ? ["/preceptor/cursos/"]
          : ["/notas/catalogos/", "/alumnos/cursos/"]

        let found = []
        for (const url of urls) {
          const res = await authFetch(url)
          if (!res.ok) continue
          const payload = await res.json().catch(() => ({}))
          found = parseCursosPayload(payload)
          if (found.length) break
        }

        if (!alive) return
        setCursos(found)
        if (found.length && !cursoSel) setCursoSel(found[0].id)
      } catch {
        if (!alive) return
        setCursos([])
      }
    })()
    return () => {
      alive = false
    }
  }, [usaCurso, isPreceptor, cursoSel])

  useEffect(() => {
    if (profileLoading) return
    if (!(isPadre || isAlumno || isProfesor || isPreceptor || isSuper)) return
    if (usaCurso && !cursoSel) return

    let alive = true
    ;(async () => {
      try {
        setReportLoading(true)
        setError("")

        const params = new URLSearchParams()
        if (cuatrimestre !== "all") params.set("cuatrimestre", cuatrimestre)
        if (isPadre && alumnoSel) params.set("alumno_id", alumnoSel)

        const qs = params.toString()
        const path = isPadre || isAlumno
          ? `/reportes/mis-estadisticas/${qs ? `?${qs}` : ""}`
          : `/reportes/curso/${encodeURIComponent(cursoSel)}/${qs ? `?${qs}` : ""}`

        const res = await authFetch(path)
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
        if (!alive) return

        setReport(data)

        if (isPadre) {
          const hijos = Array.isArray(data?.alumnos) ? data.alumnos : []
          setAlumnos(hijos)
          const activo = data?.alumno_activo
          const active = String(activo?.id || activo?.id_alumno || "")
          if (active && active !== String(alumnoSel || "")) {
            setAlumnoSel(active)
          } else if (!alumnoSel && hijos.length > 0) {
            setAlumnoSel(String(hijos[0]?.id || hijos[0]?.id_alumno || ""))
          }
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
  }, [profileLoading, isPadre, isAlumno, isProfesor, isPreceptor, isSuper, usaCurso, cursoSel, alumnoSel, cuatrimestre])

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
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
              </div>
            ) : null}

            {isPadre ? (
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">Alumno</label>
                <select className="w-full rounded border border-slate-300 px-3 py-2 text-sm" value={alumnoSel} onChange={(e) => setAlumnoSel(e.target.value)}>
                  {alumnos.length === 0 ? <option value="">Sin alumnos</option> : null}
                  {alumnos.map((a) => (
                    <option key={a.id || a.id_alumno} value={a.id || a.id_alumno}>{a.nombre} ({a.curso})</option>
                  ))}
                </select>
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
            <KpiCard icon={<CheckCircle2 className="h-4 w-4" />} title="% TEA (Aprobacion)" value={fmtPct(resumen?.porcentajes_por_estado?.TEA)} />
            <KpiCard icon={<XCircle className="h-4 w-4" />} title="% TEP (Desaprobacion)" value={fmtPct(resumen?.porcentajes_por_estado?.TEP)} />
            <KpiCard icon={<AlertTriangle className="h-4 w-4" />} title="% TED (Aplazos)" value={fmtPct(resumen?.porcentajes_por_estado?.TED)} />
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
                      <TableHead>Materia</TableHead>
                      <TableHead className="text-right">TEA</TableHead>
                      <TableHead className="text-right">TEP</TableHead>
                      <TableHead className="text-right">TED</TableHead>
                      <TableHead className="text-right">%TEA</TableHead>
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
