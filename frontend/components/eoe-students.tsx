"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { authFetch } from "@/app/_lib/auth"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

type Student = { id: number; nombre: string; apellido: string; legajo: string; curso: string; school_course_id: number }

export default function EoeStudents({ integration = false }: { integration?: boolean }) {
  const endpoint = integration ? "/integracion/alumnos" : "/eoe/alumnos"
  const [students, setStudents] = useState<Student[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true); setError("")
    ;(async () => {
      try {
        const response = await authFetch(endpoint)
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'No se pudieron cargar los alumnos PPI.')
        if (active) setStudents(data.alumnos)
      } catch (err) { if (active) setError(err instanceof Error ? err.message : 'No se pudieron cargar los alumnos PPI.') }
      finally { if (active) setLoading(false) }
    })()
    return () => { active = false }
  }, [retry, endpoint])
  const visible = students.filter((student) => `${student.apellido} ${student.nombre} ${student.legajo} ${student.curso}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  return <section className="space-y-5">
    <div><h2 className="text-xl font-semibold">{integration ? "Mis alumnos PPI" : "Alumnos PPI del colegio"}</h2><p className="mt-1 text-sm text-slate-600">{integration ? "Alumnos que tenés asignados para acompañamiento de integración." : "El gabinete acompaña a todos los estudiantes PPI del colegio."}</p></div>
    <Input aria-label="Buscar alumno PPI" placeholder="Buscar por nombre, legajo o curso" value={query} onChange={(event) => setQuery(event.target.value)} />
    {loading ? <p role="status">Cargando alumnos PPI…</p> : error ? <div role="alert">{error} <Button variant="outline" onClick={() => setRetry((value) => value + 1)}>Reintentar</Button></div> : <>
      {!visible.length && <p className="text-sm text-slate-600">No hay alumnos PPI para mostrar con este filtro.</p>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{visible.map((student) => <Link key={student.id} href={`/alumnos/${student.id}?school_course_id=${student.school_course_id}&from=%2Fmis-cursos&tab=documentacion`} className="surface-card block p-5 hover:shadow-md">
        <h3 className="font-semibold">{student.apellido}, {student.nombre}</h3><p className="mt-1 text-sm text-slate-600">{student.curso} · Legajo: {student.legajo}</p><span className="mt-2 inline-block text-xs font-medium text-violet-700">PPI</span>
      </Link>)}</div>
    </>}
  </section>
}
