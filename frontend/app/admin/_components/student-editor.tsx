"use client"

import Link from "next/link"
import { FormEvent, useEffect, useState } from "react"
import { authFetch } from "../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"

type LinkedUser = { username: string; full_name: string; email: string; is_active: boolean }
type Student = { linked_user?: LinkedUser | null; parent_user?: LinkedUser | null; id: number; nombre: string; apellido: string; id_alumno: string; es_ppi: boolean; school_course_id: number; school_course_name: string; nivel: string }
type Course = { id: number; name: string; nivel: string; is_active: boolean }
type Payload = { courses: Course[] }
const levelLabel = (value: string) => value === "primaria" ? "Primaria" : "Secundaria"

export default function StudentEditor({ schoolId, studentId, onClose, onSaved }: { schoolId: string; studentId: number; onClose: () => void; onSaved: () => void }) {
  const [payload, setPayload] = useState<Payload>({ courses: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [selected, setSelected] = useState<Student | null>(null)
  const [draft, setDraft] = useState<Student | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState("")
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError("")
    ;(async () => {
      try {
        const response = await authFetch(`/admin/students/${studentId}`, { headers: { "X-School": schoolId } })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "No se pudo cargar el alumno.")
        if (alive) { setPayload(data); setSelected(data.student); setDraft(data.student) }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "No se pudo cargar el alumno.")
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [schoolId, studentId, retry])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!draft || !selected || saving) return
    setSaving(true)
    setSaveError("")
    try {
      const response = await authFetch(`/admin/students/${selected.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-School": schoolId },
        body: JSON.stringify({ nombre: draft.nombre.trim(), apellido: draft.apellido.trim(), id_alumno: draft.id_alumno.trim(), es_ppi: draft.es_ppi, school_course_id: draft.school_course_id }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "No se pudo guardar el alumno.")
      onSaved()
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "No se pudo guardar el alumno.")
    } finally {
      setSaving(false)
    }
  }

  const chosenCourse = payload.courses.find((course) => course.id === draft?.school_course_id)
  return (
    <Dialog open onOpenChange={(open) => { if (!open && !saving) onClose() }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Información del alumno</DialogTitle>
            <DialogDescription>Consultá y editá los datos del alumno del colegio activo.</DialogDescription>
          </DialogHeader>
          {loading && <p role="status">Cargando información…</p>}
          {error && <div role="alert"><p>{error}</p><Button variant="outline" onClick={() => setRetry((value) => value + 1)}>Reintentar</Button></div>}
          {!loading && !error && selected && <section className="space-y-3 rounded-xl bg-slate-50 p-3 text-sm">
            <div><h3 className="font-semibold">Cuenta del alumno</h3>
              {selected.linked_user ? <><p>{selected.linked_user.username} · {selected.linked_user.is_active ? "Activa" : "Inactiva"}</p><p>{selected.linked_user.email || "Sin correo registrado"}</p></> : <p>Sin cuenta vinculada</p>}
            </div>
            <div><h3 className="font-semibold">Padre, madre o tutor</h3>
              {selected.parent_user ? <><p>{selected.parent_user.full_name} ({selected.parent_user.username})</p><p>{selected.parent_user.email || "Sin correo registrado"}</p></> : <p>Sin tutor vinculado</p>}
            </div>
            <Link href={`/alumnos/${selected.id}`} className="inline-block text-blue-700 underline">Abrir ficha académica</Link>
          </section>}
          {!loading && !error && draft && <form onSubmit={save} className="space-y-4">
            <fieldset disabled={saving} className="space-y-4">
              <div className="space-y-1"><Label htmlFor="student-name">Nombre</Label><Input id="student-name" required maxLength={100} value={draft.nombre} onChange={(e) => setDraft({ ...draft, nombre: e.target.value })} /></div>
              <div className="space-y-1"><Label htmlFor="student-lastname">Apellido</Label><Input id="student-lastname" required maxLength={100} value={draft.apellido} onChange={(e) => setDraft({ ...draft, apellido: e.target.value })} /></div>
              <div className="space-y-1"><Label htmlFor="student-record">Legajo</Label><Input id="student-record" required maxLength={20} value={draft.id_alumno} onChange={(e) => setDraft({ ...draft, id_alumno: e.target.value })} /></div>
              <div className="space-y-1">
                <Label htmlFor="student-course">Curso</Label>
                <select id="student-course" required className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" value={draft.school_course_id} onChange={(e) => setDraft({ ...draft, school_course_id: Number(e.target.value) })}>
                  {payload.courses.filter((course) => course.is_active || course.id === selected?.school_course_id).map((course) => <option key={course.id} value={course.id}>{course.name} · {levelLabel(course.nivel)}{!course.is_active ? " (inactivo)" : ""}</option>)}
                </select>
                <p className="text-sm text-slate-600">Nivel: <strong>{levelLabel(chosenCourse?.nivel || draft.nivel)}</strong>. Se determina por el curso elegido.</p>
              </div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-blue-700" checked={draft.es_ppi} onChange={(e) => setDraft({ ...draft, es_ppi: e.target.checked })} /><span><strong>PPI</strong> — acompañamiento psicopedagógico</span></label>
            </fieldset>
            {saveError && <p role="alert" className="text-sm text-red-700">{saveError}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" disabled={saving} onClick={onClose}>Cancelar</Button>
              <Button type="submit" disabled={saving}>{saving ? "Guardando…" : "Guardar cambios"}</Button>
            </div>
          </form>}
        </DialogContent>
    </Dialog>
  )
}
