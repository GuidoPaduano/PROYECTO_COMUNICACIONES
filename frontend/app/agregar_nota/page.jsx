"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Save } from "lucide-react"

import { authFetch, useAuthGuard } from "../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import SuccessMessage from "@/components/ui/success-message"

const ESTADOS_CALIFICACION = new Set(["TEA", "TEP", "TED"])

function buildCalificacionOptions() {
  const values = ["TEA", "TEP", "TED"]
  for (let value = 1; value <= 10; value += 1) {
    values.push(String(value))
  }
  return values.map((value) => ({ id: value, label: value }))
}

function hoyISO() {
  const d = new Date()
  const z = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`
}

function parseNotaNumerica(value) {
  const text = String(value ?? "").trim().replace(",", ".")
  if (!text) return null
  const num = Number(text)
  if (!Number.isFinite(num)) return null
  if (num < 1 || num > 10) return null
  return Number(num.toFixed(2))
}

function normalizeCalificacionValue(value) {
  return String(value ?? "").trim().replace(",", ".").toUpperCase()
}

function pickId(a) {
  return a?.id ?? a?.pk ?? a?.id_alumno ?? null
}

export default function CargarNotasRapidas() {
  useAuthGuard()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [okMsg, setOkMsg] = useState("")

  const [me, setMe] = useState(null)

  const [cursos, setCursos] = useState([])
  const [cursoSel, setCursoSel] = useState("")

  const [materias, setMaterias] = useState([])
  const [tipos, setTipos] = useState([])
  const [cuatris, setCuatris] = useState([1, 2])
  const [calificaciones, setCalificaciones] = useState(buildCalificacionOptions())
  const [rows, setRows] = useState([])
  const [fill, setFill] = useState({
    materia: "",
    tipo: "",
    calificacion: "",
    cuatrimestre: "",
    fecha: "",
    reemplazarTodo: false,
  })

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        setLoading(true)
        setError("")

        const meRes = await authFetch("/auth/whoami/")
        const meData = await meRes.json().catch(() => ({}))
        if (!meRes.ok) throw new Error(meData?.detail || `HTTP ${meRes.status}`)

        const groups = Array.isArray(meData?.groups) ? meData.groups : []
        const isProfesor = groups.includes("Profesores")
        const isSuper = !!meData?.is_superuser
        if (!(isProfesor || isSuper)) {
          window.location.href = "/dashboard"
          return
        }

        const initRes = await authFetch("/calificaciones/nueva-nota/datos/")
        const initData = await initRes.json().catch(() => ({}))
        if (!initRes.ok) throw new Error(initData?.detail || `HTTP ${initRes.status}`)

        if (!alive) return

        setMe(meData)
        setMaterias(Array.isArray(initData?.materias) ? initData.materias : [])
        setTipos(Array.isArray(initData?.tipos) ? initData.tipos : [])
        setCuatris(Array.isArray(initData?.cuatrimestres) ? initData.cuatrimestres : [1, 2])
        setCalificaciones(buildCalificacionOptions())
        const alumnos = Array.isArray(initData?.alumnos) ? initData.alumnos : []
        const cursosSet = new Set()
        for (const a of alumnos) {
          if (a?.curso) cursosSet.add(String(a.curso))
        }
        const cursosSorted = Array.from(cursosSet).sort()
        setCursos(cursosSorted)
        if (cursosSorted.length) setCursoSel(cursosSorted[0])
      } catch (e) {
        if (!alive) return
        setError(e?.message || "No se pudo cargar la pantalla")
      } finally {
        if (alive) setLoading(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      if (!cursoSel) return
      try {
        setError("")
        const res = await authFetch(`/calificaciones/nueva-nota/datos/?curso=${encodeURIComponent(cursoSel)}`)
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)

        const alumnos = Array.isArray(data?.alumnos) ? data.alumnos : []
        const mapped = alumnos
          .map((a) => ({
            id: pickId(a),
            nombre: String(a?.nombre || "Alumno"),
            materia: "",
            tipo: "",
            calificacion: "",
            cuatrimestre: cuatris?.[0] ?? 1,
            fecha: hoyISO(),
            incluir: true,
          }))
          .filter((r) => r.id != null)

        if (!alive) return
        setRows(mapped)
      } catch (e) {
        if (!alive) return
        setRows([])
        setError(e?.message || "No se pudieron cargar los alumnos")
      }
    })()

    return () => {
      alive = false
    }
  }, [cursoSel, cuatris])

  const seleccionadas = useMemo(() => rows.filter((r) => r.incluir), [rows])

  function applyFill() {
    setRows((prev) =>
      prev.map((r) => {
        const next = { ...r }
        const canSet = (v, cur) => (fill.reemplazarTodo || !cur ? v : cur)
        if (fill.materia) next.materia = canSet(fill.materia, r.materia)
        if (fill.tipo) next.tipo = canSet(fill.tipo, r.tipo)
        if (fill.calificacion) next.calificacion = canSet(fill.calificacion, r.calificacion)
        if (fill.cuatrimestre) next.cuatrimestre = Number(canSet(fill.cuatrimestre, r.cuatrimestre))
        if (fill.fecha) next.fecha = canSet(fill.fecha, r.fecha)
        return next
      })
    )
  }

  async function guardarSeleccionadas() {
    setError("")
    setOkMsg("")

    const invalid = seleccionadas.filter((r) => {
      if (!r.id || !r.materia || !r.tipo || !r.cuatrimestre) return true
      const calificacion = normalizeCalificacionValue(r.calificacion)
      if (!calificacion) return true
      if (!ESTADOS_CALIFICACION.has(calificacion) && parseNotaNumerica(calificacion) == null) return true
      return false
    })

    if (invalid.length) {
      setError("Completa materia, tipo, cuatrimestre y una calificacion valida en cada fila.")
      return
    }

    setSaving(true)
    try {
      const notas = seleccionadas.map((r) => {
        const calificacion = normalizeCalificacionValue(r.calificacion)
        const isEstado = ESTADOS_CALIFICACION.has(calificacion)
        const num = isEstado ? null : parseNotaNumerica(calificacion)
        const resultado = isEstado ? calificacion : ""
        const calificacionLegacy = resultado || (num != null ? String(num) : "")
        return {
          alumno_id: r.id,
          materia: String(r.materia).trim(),
          tipo: String(r.tipo).trim(),
          resultado: resultado || null,
          nota_numerica: num,
          calificacion: calificacionLegacy,
          cuatrimestre: Number(r.cuatrimestre),
          fecha: r.fecha || hoyISO(),
        }
      })

      const res = await authFetch("/calificaciones/notas/masivo/", {
        method: "POST",
        body: JSON.stringify({ notas }),
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(payload?.detail || payload?.error || `HTTP ${res.status}`)
      }

      const creadas = Array.isArray(payload?.created) ? payload.created.length : notas.length
      setOkMsg(`Guardadas ${creadas} notas.`)
    } catch (e) {
      setError(e?.message || "Fallo al guardar")
    } finally {
      setSaving(false)
    }
  }

  const isLoading = loading

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Carga de notas</h1>
        <Link href="/dashboard">
          <Button variant="outline" className="inline-flex items-center">
            <ArrowLeft className="mr-2 h-4 w-4" /> Volver
          </Button>
        </Link>
      </div>

      {okMsg ? <SuccessMessage>{okMsg}</SuccessMessage> : null}
      {error ? (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-4 text-sm text-red-700">{error}</CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="p-4 space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Curso</label>
            <select
              className="w-full rounded border px-3 py-2"
              value={cursoSel}
              onChange={(e) => setCursoSel(e.target.value)}
              disabled={isLoading}
            >
              {cursos.length === 0 ? <option value="">Sin cursos</option> : null}
              {cursos.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
            <select className="rounded border px-3 py-2" value={fill.materia} onChange={(e) => setFill((f) => ({ ...f, materia: e.target.value }))}>
              <option value="">Materia</option>
              {materias.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
            <select className="rounded border px-3 py-2" value={fill.tipo} onChange={(e) => setFill((f) => ({ ...f, tipo: e.target.value }))}>
              <option value="">Tipo</option>
              {(tipos.length ? tipos : ["Examen", "Trabajo Practico", "Participacion", "Tarea"]).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <select className="rounded border px-3 py-2" value={fill.calificacion} onChange={(e) => setFill((f) => ({ ...f, calificacion: e.target.value }))}>
              <option value="">Calificacion</option>
              {calificaciones.map((r) => (
                <option key={r.id} value={r.id}>{r.label}</option>
              ))}
            </select>
            <select className="rounded border px-3 py-2" value={fill.cuatrimestre} onChange={(e) => setFill((f) => ({ ...f, cuatrimestre: e.target.value }))}>
              <option value="">Cuatrimestre</option>
              {cuatris.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <input type="date" className="rounded border px-3 py-2" value={fill.fecha} onChange={(e) => setFill((f) => ({ ...f, fecha: e.target.value }))} />
          </div>

          <div className="flex items-center gap-3">
            <label className="text-sm">
              <input
                type="checkbox"
                checked={fill.reemplazarTodo}
                onChange={(e) => setFill((f) => ({ ...f, reemplazarTodo: e.target.checked }))}
                className="mr-2"
              />
              Reemplazar campos ya cargados
            </label>
            <Button variant="outline" onClick={applyFill}>Aplicar a todas</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-left">
                <th className="border-b px-3 py-2">Incluir</th>
                <th className="border-b px-3 py-2">Alumno</th>
                <th className="border-b px-3 py-2">Materia</th>
                <th className="border-b px-3 py-2">Tipo</th>
                <th className="border-b px-3 py-2">Calificacion</th>
                <th className="border-b px-3 py-2">Cuatr.</th>
                <th className="border-b px-3 py-2">Fecha</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => (
                <tr key={`${r.id}-${idx}`} className="border-b">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={!!r.incluir}
                      onChange={(e) => setRows((prev) => prev.map((x, j) => (j === idx ? { ...x, incluir: e.target.checked } : x)))}
                    />
                  </td>
                  <td className="px-3 py-2">{r.nombre}</td>
                  <td className="px-3 py-2">
                    <select className="w-full rounded border px-2 py-1" value={r.materia} onChange={(e) => setRows((prev) => prev.map((x, j) => (j === idx ? { ...x, materia: e.target.value } : x)))}>
                      <option value=""></option>
                      {materias.map((m) => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <select className="w-full rounded border px-2 py-1" value={r.tipo} onChange={(e) => setRows((prev) => prev.map((x, j) => (j === idx ? { ...x, tipo: e.target.value } : x)))}>
                      <option value=""></option>
                      {(tipos.length ? tipos : ["Examen", "Trabajo Practico", "Participacion", "Tarea"]).map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <select className="w-full rounded border px-2 py-1" value={r.calificacion} onChange={(e) => setRows((prev) => prev.map((x, j) => (j === idx ? { ...x, calificacion: e.target.value } : x)))}>
                      <option value=""></option>
                      {calificaciones.map((opt) => <option key={opt.id} value={opt.id}>{opt.label}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <select className="w-full rounded border px-2 py-1" value={r.cuatrimestre} onChange={(e) => setRows((prev) => prev.map((x, j) => (j === idx ? { ...x, cuatrimestre: Number(e.target.value) } : x)))}>
                      <option value=""></option>
                      {cuatris.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <input type="date" className="w-full rounded border px-2 py-1" value={r.fecha || ""} onChange={(e) => setRows((prev) => prev.map((x, j) => (j === idx ? { ...x, fecha: e.target.value } : x)))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex items-center gap-3 p-4">
            <Button onClick={guardarSeleccionadas} disabled={saving || isLoading} className="inline-flex items-center">
              <Save className="mr-2 h-4 w-4" /> {saving ? "Guardando..." : "Guardar seleccionadas"}
            </Button>
            <div className="text-xs text-slate-500">
              Debes completar una calificacion valida en cada fila seleccionada.
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="text-xs text-slate-500">
        Usuario: {me?.username || "-"}
      </div>
    </div>
  )
}
