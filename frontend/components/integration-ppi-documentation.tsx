"use client"

import { useEffect, useState } from "react"
import { authFetch, useSessionContext } from "@/app/_lib/auth"
import PpiDocuments from "@/app/alumnos/[alumnoId]/_ppi-documents"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"

type Student = { id: number; nombre: string; apellido: string; legajo: string; curso: string }
const LAST_PPI_STUDENT_KEY = "integracion_last_alumno_ppi"

export default function IntegrationPpiDocumentation() {
  const session = useSessionContext()
  const isEOE = session?.groups?.includes("EOE") || session?.role === "EOE"
  const [students, setStudents] = useState<Student[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError("")
    ;(async () => {
      try {
        const response = await authFetch(isEOE ? "/eoe/alumnos/" : "/integracion/alumnos/")
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "No se pudieron cargar tus alumnos PPI.")
        const next: Student[] = Array.isArray(data.alumnos) ? data.alumnos : []
        if (active) {
          setStudents(next)
          const requested = new URLSearchParams(window.location.search).get("alumno_id") || ""
          let stored = ""
          try { stored = localStorage.getItem(LAST_PPI_STUDENT_KEY) || "" } catch {}
          setSelectedId((current) => [requested, current, stored].find((id) => next.some((student) => String(student.id) === id)) || String(next[0]?.id || ""))
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "No se pudieron cargar tus alumnos PPI.")
      } finally { if (active) setLoading(false) }
    })()
    return () => { active = false }
  }, [isEOE, session?.username, session?.school?.id, retry])

  useEffect(() => {
    if (selectedId) try { localStorage.setItem(LAST_PPI_STUDENT_KEY, selectedId) } catch {}
  }, [selectedId])

  return <section className="mb-8 space-y-5" aria-label="Documentación de alumnos PPI">
    {loading && <p role="status" className="text-sm text-slate-600">Cargando alumnos…</p>}
    {error && <div role="alert" className="text-sm text-red-700">{error} <Button variant="outline" onClick={() => setRetry((value) => value + 1)}>Reintentar</Button></div>}
    {!loading && !error && !students.length && <p className="text-sm text-slate-600">{isEOE ? "Todavía no hay alumnos PPI en este colegio." : "Todavía no tenés alumnos PPI asignados."}</p>}
    {!!students.length && !error && <>
      <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:p-5">
        <Label htmlFor="integration-ppi-document-student" className="shrink-0">Alumno PPI</Label>
        <select id="integration-ppi-document-student" value={selectedId} onChange={(event) => setSelectedId(event.target.value)} className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm sm:max-w-md">
          {students.map((student) => <option key={student.id} value={student.id}>{student.apellido}, {student.nombre} · {student.curso} · {student.legajo}</option>)}
        </select>
      </div>
      {selectedId && <PpiDocuments key={selectedId} alumnoId={Number(selectedId)} sendToAllCourseTeachers={!isEOE} />}
    </>}
  </section>
}
