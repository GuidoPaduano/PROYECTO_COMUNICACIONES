// @ts-nocheck
"use client"

import { useEffect, useState } from "react"
import { ArrowLeft } from "lucide-react"
import Link from "next/link"
import { authFetch, useAuthGuard, useSessionContext } from "../../../_lib/auth"

type NotaCuatri = {
  calificacion: string
  nota_numerica: string | null
  resultado: string | null
}

type AlumnoHistorico = {
  id: number
  nombre: string
  apellido: string
  id_alumno: string
  notas: Record<string, Record<string, NotaCuatri>>
}

type Course = { id: number; code: string; nombre: string; school_course_id: number }

function displayCalificacion(nota: NotaCuatri | undefined): string {
  if (!nota) return "—"
  if (nota.resultado) return nota.resultado
  if (nota.nota_numerica) return nota.nota_numerica
  return nota.calificacion || "—"
}

function cellClass(nota: NotaCuatri | undefined): string {
  if (!nota) return "text-slate-300"
  if (nota.resultado === "TEA") return "text-green-700 font-medium"
  if (nota.resultado === "TEP") return "text-red-600 font-medium"
  if (nota.resultado === "TED") return "text-amber-600 font-medium"
  const num = parseFloat(nota.nota_numerica || nota.calificacion || "")
  if (!isNaN(num)) {
    if (num >= 7) return "text-green-700 font-medium"
    if (num >= 4) return "text-amber-600 font-medium"
    return "text-red-600 font-medium"
  }
  return "text-slate-700"
}

export default function NotasHistoricasPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const isSuper = !!sessionContext?.isSuperuser
  const groups = Array.isArray(sessionContext?.groups) ? sessionContext.groups : []
  const isAdmin = isSuper || groups.some((g: string) => ["administradores", "administrador"].includes(String(g).toLowerCase()))

  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: 5 }, (_, i) => currentYear - i)
  const [courses, setCourses] = useState<Course[]>([])
  const [selectedYear, setSelectedYear] = useState<string>(String(currentYear))
  const [selectedCourse, setSelectedCourse] = useState<string>("")
  const [data, setData] = useState<{ materias: string[]; alumnos: AlumnoHistorico[] } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!isAdmin) return
    authFetch("/alumnos/cursos/")
      .then((r) => r.json())
      .then((d) => setCourses(d.cursos || []))
      .catch(() => {})
  }, [isAdmin])

  async function buscar() {
    if (!selectedYear) { setError("Seleccioná un año."); return }
    setError("")
    setLoading(true)
    setData(null)
    try {
      const params = new URLSearchParams({ anio_lectivo: selectedYear })
      if (selectedCourse) params.set("school_course_id", selectedCourse)
      const res = await authFetch(`/calificaciones/notas/historicas/?${params}`)
      const json = await res.json()
      if (!res.ok) { setError(json.detail || "Error al cargar."); return }
      setData(json)
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setLoading(false)
    }
  }

  if (!sessionContext) return <div className="p-8 text-sm text-slate-500">Cargando...</div>
  if (!isAdmin) return <div className="p-8 text-sm text-red-600">Acceso restringido.</div>

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8">
      <div className="flex items-center gap-3">
        <Link href="/admin/colegio" className="text-slate-400 hover:text-slate-600">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Notas históricas</h1>
          <p className="text-sm text-slate-500">Notas finales de cuatrimestre por año y curso</p>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-600">Año lectivo</label>
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <option value="">Seleccioná un año</option>
            {years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-600">Curso (opcional)</label>
          <select
            value={selectedCourse}
            onChange={(e) => setSelectedCourse(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <option value="">Todos los cursos</option>
            {courses.map((c) => (
              <option key={c.school_course_id} value={c.school_course_id}>{c.nombre || c.code}</option>
            ))}
          </select>
        </div>

        <div className="flex items-end">
          <button
            onClick={buscar}
            disabled={loading}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {loading ? "Buscando..." : "Buscar"}
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* Tabla */}
      {data && (
        data.alumnos.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
            No hay notas finales registradas para los filtros seleccionados.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="px-4 py-3 text-left font-semibold text-slate-700" rowSpan={2}>Alumno</th>
                  {data.materias.map((m) => (
                    <th key={m} colSpan={2} className="border-l border-slate-200 px-4 py-3 text-center font-semibold text-slate-700">
                      {m}
                    </th>
                  ))}
                </tr>
                <tr className="border-b border-slate-200 bg-slate-50">
                  {data.materias.map((m) => (
                    <>
                      <th key={`${m}-1`} className="border-l border-slate-200 px-3 py-2 text-center text-xs font-medium text-slate-500">1° C</th>
                      <th key={`${m}-2`} className="px-3 py-2 text-center text-xs font-medium text-slate-500">2° C</th>
                    </>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.alumnos.map((alumno, i) => (
                  <tr key={alumno.id} className={i % 2 === 0 ? "bg-white" : "bg-slate-50"}>
                    <td className="px-4 py-2 font-medium text-slate-800">
                      {alumno.apellido}, {alumno.nombre}
                    </td>
                    {data.materias.map((m) => (
                      <>
                        <td key={`${alumno.id}-${m}-1`} className={`border-l border-slate-100 px-3 py-2 text-center ${cellClass(alumno.notas[m]?.["1"])}`}>
                          {displayCalificacion(alumno.notas[m]?.["1"])}
                        </td>
                        <td key={`${alumno.id}-${m}-2`} className={`px-3 py-2 text-center ${cellClass(alumno.notas[m]?.["2"])}`}>
                          {displayCalificacion(alumno.notas[m]?.["2"])}
                        </td>
                      </>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
