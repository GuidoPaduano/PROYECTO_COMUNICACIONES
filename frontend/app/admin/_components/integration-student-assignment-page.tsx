"use client"

import Link from "next/link"
import { ReactNode, useEffect, useState } from "react"
import { authFetch, useAuthGuard, useSessionContext } from "../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

type Student = { id: number; nombre: string; apellido: string; legajo: string; curso: string; maestra_ids: number[] }
type Teacher = { id: number; nombre: string; email: string; disponible: boolean }
const name = (student: Student) => `${student.apellido}, ${student.nombre}`

export default function IntegrationStudentAssignmentPage({ navigation }: { navigation: ReactNode }) {
  useAuthGuard()
  const session = useSessionContext()
  const allowed = !!session?.isSuperuser || !!session?.groups?.some((g) => ['administradores', 'administrador'].includes(g.toLowerCase()))
  const [students, setStudents] = useState<Student[]>([])
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [drafts, setDrafts] = useState<Record<number, number[]>>({})
  const [studentQuery, setStudentQuery] = useState("")
  const [teacherQuery, setTeacherQuery] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [loadError, setLoadError] = useState("")
  const [success, setSuccess] = useState("")
  const [retry, setRetry] = useState(0)
  const schoolRef = session?.school?.slug || session?.school?.id
  useEffect(() => {
    if (!allowed) return
    let active = true
    setLoading(true); setLoadError(""); setError(""); setSuccess("")
    setStudents([]); setTeachers([]); setDrafts({}); setSelectedId("")
    ;(async () => {
      try {
        const response = await authFetch('/admin/integracion/alumnos', { headers: schoolRef ? { 'X-School': String(schoolRef) } : undefined })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'No se pudieron cargar las asignaciones.')
        if (active) { setStudents(data.alumnos); setTeachers(data.maestras); setSelectedId(data.alumnos[0] ? String(data.alumnos[0].id) : '') }
      } catch (err) { if (active) setLoadError(err instanceof Error ? err.message : 'No se pudieron cargar las asignaciones.') }
      finally { if (active) setLoading(false) }
    })()
    return () => { active = false }
  }, [allowed, schoolRef, retry])
  const student = students.find((item) => String(item.id) === selectedId)
  const selected = student ? drafts[student.id] ?? student.maestra_ids : []
  const filteredStudents = students.filter((item) => `${name(item)} ${item.legajo} ${item.curso}`.toLocaleLowerCase().includes(studentQuery.toLocaleLowerCase()))
  const filteredTeachers = teachers.filter((item) => `${item.nombre} ${item.email}`.toLocaleLowerCase().includes(teacherQuery.toLocaleLowerCase()))
  function toggle(id: number) {
    if (!student || saving) return
    setDrafts((current) => ({ ...current, [student.id]: selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id] }))
    setError(''); setSuccess('')
  }
  async function save() {
    if (!student || saving) return
    const id = student.id
    setSaving(true); setError(''); setSuccess('')
    try {
      const response = await authFetch(`/admin/integracion/alumnos/${id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json', ...(schoolRef ? { 'X-School': String(schoolRef) } : {}) },
        body: JSON.stringify({ maestra_ids: selected }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'No se pudo guardar la asignación.')
      setStudents((current) => current.map((item) => item.id === id ? { ...item, maestra_ids: data.maestra_ids } : item))
      setDrafts((current) => { const next = { ...current }; delete next[id]; return next })
      setSuccess(`Asignación de ${name(student)} guardada.`)
    } catch (err) { setError(err instanceof Error ? err.message : 'No se pudo guardar la asignación.') }
    finally { setSaving(false) }
  }
  if (!session) return <p>Cargando herramienta…</p>
  if (!allowed) return <p>Solo los administradores del colegio pueden modificar asignaciones.</p>
  return <div className="mx-auto max-w-6xl space-y-6">
    <header><Link href="/admin/colegio" className="text-sm text-slate-600">← Volver a admin colegio</Link><h2 className="mt-3 text-3xl font-semibold">EOE e Integración</h2><p className="mt-2 text-sm text-slate-600">Asigná maestras de integración a cada alumno PPI del colegio.</p></header>
    {navigation}
    {loading ? <p role="status">Cargando alumnos y maestras…</p> : loadError ? <div role="alert" className="surface-card space-y-3 p-5"><p className="text-red-700">{loadError}</p><Button variant="outline" onClick={() => setRetry((n) => n + 1)}>Reintentar</Button></div> : <>
      <section className="surface-card space-y-4 p-5">
        <h3 className="font-semibold">Alumno PPI</h3>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2"><Label htmlFor="integration-student-search">Buscar alumno</Label><Input id="integration-student-search" disabled={saving} value={studentQuery} onChange={(event) => setStudentQuery(event.target.value)} placeholder="Nombre, legajo o curso" /></div>
          <div className="space-y-2"><Label htmlFor="integration-student">Alumno</Label><select id="integration-student" disabled={saving || !students.length} value={selectedId} onChange={(event) => { setSelectedId(event.target.value); setError(''); setSuccess(''); setTeacherQuery('') }} className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">
            <option value="">Seleccioná un alumno</option>
            {student && !filteredStudents.some((item) => item.id === student.id) && <option value={student.id}>{name(student)} · {student.curso} · {student.legajo}</option>}
            {filteredStudents.map((item) => <option key={item.id} value={item.id}>{name(item)} · {item.curso} · {item.legajo}</option>)}
          </select></div>
        </div>
        {!students.length && <p className="text-sm text-slate-600">Todavía no hay alumnos marcados como PPI en este colegio.</p>}
        {!!students.length && !filteredStudents.length && <p className="text-sm text-slate-600">No hay alumnos que coincidan con la búsqueda.</p>}
      </section>
      {student && <section className="surface-card space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{name(student)}</h3><p className="text-sm text-slate-600">{student.curso} · Legajo: {student.legajo}</p></div><Button disabled={saving} onClick={save}>{saving ? 'Guardando…' : 'Guardar asignación'}</Button></div>
        <p className="text-sm text-slate-600">Seleccioná las maestras que acompañan a este alumno. Los cambios se aplican al guardar.</p>
        <Input aria-label="Buscar maestra de integración" placeholder="Buscar maestra por nombre o email" value={teacherQuery} onChange={(event) => setTeacherQuery(event.target.value)} />
        <p className="text-sm font-medium">Maestras seleccionadas: {selected.length}</p>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
        {!teachers.length ? <p className="text-sm text-slate-600">No hay maestras de integración en el colegio. <Link href="/admin/colegio/nuevo-usuario" className="underline">Crear usuario de Integración</Link></p> : !filteredTeachers.length ? <p className="text-sm text-slate-600">No hay maestras que coincidan con la búsqueda.</p> : <div className="grid gap-3 sm:grid-cols-2">{filteredTeachers.map((teacher) => <label key={teacher.id} className={`flex items-start gap-3 rounded-xl border p-4 ${selected.includes(teacher.id) ? 'border-slate-700 bg-slate-50' : 'border-slate-200'}`}>
          <input type="checkbox" checked={selected.includes(teacher.id)} disabled={saving || (!teacher.disponible && !selected.includes(teacher.id))} onChange={() => toggle(teacher.id)} className="mt-1" />
          <span><span className="block text-sm font-medium">{teacher.nombre}</span><span className="block text-xs text-slate-500">{teacher.email}</span>{!teacher.disponible && <span className="block text-xs text-amber-700">No disponible. Quitá esta asignación para guardar.</span>}</span>
        </label>)}</div>}
      </section>}
    </>}
  </div>
}
