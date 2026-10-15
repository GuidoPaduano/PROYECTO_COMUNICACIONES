"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { FileText } from "lucide-react"
import { authFetch, useSessionContext } from "@/app/_lib/auth"
import { Card, CardContent } from "@/components/ui/card"

const LAST_PPI_STUDENT_KEY = "integracion_last_alumno_ppi"

type Student = { id: number; nombre: string; apellido: string; curso: string }
type Document = { id: number; titulo: string; creado_en: string; requiere_firma: boolean; version: number }

export default function IntegrationPpiDocumentsDashboardCard() {
  const session = useSessionContext()
  const [students, setStudents] = useState<Student[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [documents, setDocuments] = useState<Document[]>([])
  const [loadingStudents, setLoadingStudents] = useState(true)
  const [loadingDocuments, setLoadingDocuments] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    let active = true
    setLoadingStudents(true)
    setError("")
    setStudents([])
    setSelectedId("")
    ;(async () => {
      try {
        const response = await authFetch("/integracion/alumnos/")
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "No se pudieron cargar tus alumnos PPI.")
        const next: Student[] = Array.isArray(data.alumnos) ? data.alumnos : []
        let stored = ""
        try { stored = localStorage.getItem(LAST_PPI_STUDENT_KEY) || "" } catch {}
        if (active) {
          setStudents(next)
          setSelectedId(next.some((student) => String(student.id) === stored) ? stored : String(next[0]?.id || ""))
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "No se pudieron cargar tus alumnos PPI.")
      } finally { if (active) setLoadingStudents(false) }
    })()
    return () => { active = false }
  }, [session?.username, session?.school?.id])

  useEffect(() => {
    if (!selectedId) { setDocuments([]); return }
    let active = true
    setLoadingDocuments(true)
    setError("")
    try { localStorage.setItem(LAST_PPI_STUDENT_KEY, selectedId) } catch {}
    ;(async () => {
      try {
        const response = await authFetch(`/alumnos/${selectedId}/ppi-documentos`)
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "No se pudieron cargar los documentos.")
        if (active) setDocuments(Array.isArray(data.documents) ? data.documents : [])
      } catch (err) {
        if (active) { setDocuments([]); setError(err instanceof Error ? err.message : "No se pudieron cargar los documentos.") }
      } finally { if (active) setLoadingDocuments(false) }
    })()
    return () => { active = false }
  }, [selectedId])

  return <Card className="surface-card">
    <CardContent className="surface-card-pad space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-700"><FileText className="h-6 w-6" aria-hidden="true" /></div>
        <div><h2 className="tile-title">Documentos PPI</h2><p className="tile-subtitle">Archivos del alumno seleccionado</p></div>
      </div>
      {loadingStudents ? <p className="text-sm text-slate-500">Cargando alumnos…</p> : students.length ? <>
        <label className="block space-y-1 text-sm font-medium text-slate-700" htmlFor="dashboard-ppi-document-student">
          <span>Alumno PPI</span>
          <select id="dashboard-ppi-document-student" value={selectedId} onChange={(event) => setSelectedId(event.target.value)} className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-normal">
            {students.map((student) => <option key={student.id} value={student.id}>{student.apellido}, {student.nombre} · {student.curso}</option>)}
          </select>
        </label>
        {loadingDocuments ? <p className="text-sm text-slate-500">Cargando documentos…</p> : !error && !documents.length ? <p className="text-sm text-slate-500">Este alumno todavía no tiene documentos.</p> : <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
          {documents.map((doc) => <li key={doc.id} className="flex items-center justify-between gap-3 py-3">
            <div className="min-w-0"><p className="truncate text-sm font-medium text-slate-900">{doc.titulo}</p><p className="text-xs text-slate-500">{doc.requiere_firma ? "Para firmar" : "Constancia"} · {new Date(doc.creado_en).toLocaleDateString("es-AR")} · Versión {doc.version || 1}</p></div>
            <Link href={`/documentacion?alumno_id=${selectedId}&ppi_document=${doc.id}#ppi-document-${doc.id}`} className="shrink-0 text-sm font-medium text-blue-700 hover:underline">Ver</Link>
          </li>)}
        </ul>}
      </> : !error ? <p className="text-sm text-slate-500">Todavía no tenés alumnos PPI asignados.</p> : null}
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <Link href="/documentacion" className="btn-school-primary inline-flex h-9 items-center justify-center rounded-lg px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--school-primary-soft-strong)] focus-visible:ring-offset-2">Ir a Documentación</Link>
    </CardContent>
  </Card>
}
