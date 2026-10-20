"use client"

import { FormEvent, useEffect, useRef, useState } from "react"
import { authFetch } from "../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { FileUp } from "lucide-react"

import PpiDocumentCard, { PpiDocument } from "@/components/ppi-document-card"

type Teacher = { id: number; nombre: string }

export default function PpiDocuments({ alumnoId, sendToAllCourseTeachers = false }: { alumnoId: number; sendToAllCourseTeachers?: boolean }) {
  const [documents, setDocuments] = useState<PpiDocument[]>([])
  const [canUpload, setCanUpload] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [title, setTitle] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [requiresSignature, setRequiresSignature] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [previous, setPrevious] = useState<PpiDocument | null>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const [retry, setRetry] = useState(0)
  const fileInput = useRef<HTMLInputElement>(null)
  const endpoint = `/alumnos/${alumnoId}/ppi-documentos`

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError("")
    ;(async () => {
      try {
        const response = await authFetch(endpoint)
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "No se pudo cargar la documentación.")
        if (alive) { setDocuments(data.documents.map((doc: PpiDocument) => ({ ...doc, alumno_id: alumnoId }))); setCanUpload(data.can_upload); setTeachers(data.docentes || []) }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "No se pudo cargar la documentación.")
      } finally { if (alive) setLoading(false) }
    })()
    return () => { alive = false }
  }, [endpoint, retry])

  useEffect(() => {
    if (!documents.length) return
    const target = new URLSearchParams(window.location.search).get("ppi_document")
    if (target && /^\d+$/.test(target)) document.getElementById(`ppi-document-${target}`)?.scrollIntoView?.({ behavior: "smooth", block: "start" })
  }, [documents])

  async function upload(event: FormEvent) {
    event.preventDefault()
    if (saving) return
    setError(""); setSuccess("")
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) { setError("Seleccioná un archivo PDF."); return }
    if (file.size > 20 * 1024 * 1024) { setError("El PDF debe pesar como máximo 20 MB."); return }
    if (!title.trim()) { setError("Ingresá un título."); return }
    if (requiresSignature && !sendToAllCourseTeachers && !selected.length) { setError("Seleccioná al menos un docente."); return }
    if (sendToAllCourseTeachers && requiresSignature && !teachers.length) { setError("Este curso no tiene profesores asignados para recibir el documento."); return }
    setSaving(true)
    try {
      const body = new FormData()
      body.append("titulo", title.trim())
      body.append("archivo", file)
      body.append("requiere_firma", String(requiresSignature))
      if (sendToAllCourseTeachers && requiresSignature) body.append("todos_docentes_curso", "true")
      else body.append("docentes", JSON.stringify(selected))
      if (previous) body.append("version_anterior_id", String(previous.id))
      const response = await authFetch(endpoint, { method: "POST", body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "No se pudo subir el PDF.")
      setDocuments((current) => [{ ...data.document, alumno_id: alumnoId }, ...current.map((doc) => doc.id === previous?.id ? { ...doc, reemplazado: true } : doc)])
      setTitle(""); setFile(null); setPrevious(null); setRequiresSignature(false); setSelected([])
      if (fileInput.current) fileInput.current.value = ""
      setSuccess(sendToAllCourseTeachers ? (requiresSignature ? "PDF enviado a los profesores del curso para su firma." : "PDF guardado en la documentación PPI del alumno.") : "PDF guardado correctamente.")
    } catch (err) { setError(err instanceof Error ? err.message : "No se pudo subir el PDF.") }
    finally { setSaving(false) }
  }

  function newVersion(doc: PpiDocument) {
    setPrevious(doc); setTitle(doc.titulo); setRequiresSignature(!!doc.requiere_firma)
    setSelected((doc.destinatarios || []).map((r) => r.id).filter((id) => teachers.some((teacher) => teacher.id === id)))
    setFile(null); setError(""); setSuccess("")
    if (fileInput.current) fileInput.current.value = ""
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
  }

  return <div className="space-y-5">
    {!sendToAllCourseTeachers && <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">Documentación</h2><p className="text-sm text-slate-600">Informes y documentación de acompañamiento de este alumno.</p></div><Button variant="ghost" disabled={loading || saving} onClick={() => setRetry((value) => value + 1)}>Actualizar</Button></div>}
    {loading && <p role="status">Cargando documentación…</p>}
    {error && <div role="alert" className="text-sm text-red-700"><p>{error}</p><Button variant="outline" onClick={() => setRetry((value) => value + 1)}>Reintentar</Button></div>}
    {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
    {!loading && canUpload && <form ref={formRef} onSubmit={upload} className={`rounded-xl border border-slate-200 bg-white p-4 sm:p-6 ${sendToAllCourseTeachers ? "space-y-5" : "space-y-3"}`}>
      <div className="flex items-center justify-between gap-2"><h3 className="font-semibold">{previous ? `Nueva versión de ${previous.titulo}` : sendToAllCourseTeachers ? "Nuevo documento" : "Subir PDF"}</h3>
      {previous && <Button type="button" variant="ghost" disabled={saving} onClick={() => { setPrevious(null); setTitle(""); setRequiresSignature(false); setSelected([]) }}>Cancelar versión</Button>}</div>
      {previous && <p className="text-sm text-slate-600">Se conservarán el PDF anterior y sus constancias.{previous.requiere_firma ? " Los docentes deberán confirmar la lectura de esta nueva versión." : ""}</p>}
      <fieldset disabled={saving} className={sendToAllCourseTeachers ? "grid gap-5 lg:grid-cols-2 lg:items-start" : "space-y-3"}>
        <div className="space-y-1.5"><Label htmlFor="ppi-document-title">Título</Label><Input id="ppi-document-title" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ej.: Informe de acompañamiento" /></div>
        {sendToAllCourseTeachers ? <div className="space-y-1.5">
          <Label htmlFor="ppi-document-file">Archivo PDF</Label>
          <Input id="ppi-document-file" ref={fileInput} type="file" accept=".pdf,application/pdf" required className="sr-only" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <label htmlFor="ppi-document-file" className="flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-4 transition-colors hover:border-slate-400 hover:bg-slate-100 focus-within:ring-2 focus-within:ring-slate-400">
            <span className="rounded-lg bg-white p-2 text-slate-600 shadow-sm"><FileUp aria-hidden="true" className="h-5 w-5" /></span>
            <span className="min-w-0"><span className="block truncate text-sm font-medium text-slate-900">{file ? file.name : "Seleccionar PDF"}</span><span className="text-xs text-slate-500">Hasta 20 MB</span></span>
          </label>
        </div> : <div><Label htmlFor="ppi-document-file">Archivo PDF</Label><Input id="ppi-document-file" ref={fileInput} type="file" accept=".pdf,application/pdf" required onChange={(e) => setFile(e.target.files?.[0] || null)} /><p className="mt-1 text-xs text-slate-600">Hasta 20 MB por archivo.</p></div>}
        {sendToAllCourseTeachers ? <div className="border-t border-slate-200 pt-4 text-sm lg:col-span-2">
          <label className="flex cursor-pointer items-start gap-3"><input type="checkbox" checked={requiresSignature} disabled={!!previous?.requiere_firma} onChange={(event) => setRequiresSignature(event.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-slate-900" /><span className="font-medium text-slate-900">Enviar a los profesores para que firmen</span></label>
          {requiresSignature && <div className="ml-7 mt-2 text-slate-600">
            {teachers.length ? <details><summary className="cursor-pointer">{teachers.length} {teachers.length === 1 ? "profesor destinatario" : "profesores destinatarios"}</summary><p className="mt-2">{teachers.map((teacher) => teacher.nombre).join(", ")}</p></details> : <p className="text-amber-700">Este curso no tiene profesores asignados.</p>}
          </div>}
        </div> : <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={requiresSignature} disabled={!!previous?.requiere_firma} onChange={(e) => setRequiresSignature(e.target.checked)} />Requiere constancia de lectura</label>}
        {requiresSignature && !sendToAllCourseTeachers && <div className="space-y-2 rounded-lg bg-slate-50 p-3">
          <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">Docentes destinatarios</span><Button type="button" variant="ghost" onClick={() => setSelected(selected.length === teachers.length ? [] : teachers.map((teacher) => teacher.id))}>{selected.length === teachers.length && teachers.length ? "Quitar selección" : "Seleccionar todos"}</Button></div>
          {!teachers.length && <p className="text-sm text-amber-700">Este alumno todavía no tiene docentes asignados a su curso.</p>}
          {teachers.map((teacher) => <label key={teacher.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selected.includes(teacher.id)} onChange={(e) => setSelected((current) => e.target.checked ? [...current, teacher.id] : current.filter((id) => id !== teacher.id))} />{teacher.nombre}</label>)}
        </div>}
        <Button type="submit" className={sendToAllCourseTeachers ? "justify-self-start" : undefined} disabled={sendToAllCourseTeachers && requiresSignature && !teachers.length}>{saving ? "Subiendo…" : sendToAllCourseTeachers ? (requiresSignature ? "Subir y enviar" : "Subir documento") : "Subir PDF"}</Button>
      </fieldset>
    </form>}
    {sendToAllCourseTeachers && !loading && <div className="flex items-center justify-between gap-3 pt-2"><h2 className="text-base font-semibold">Documentos guardados <span className="font-normal text-slate-500">({documents.length})</span></h2><Button variant="ghost" disabled={saving} onClick={() => setRetry((value) => value + 1)}>Actualizar</Button></div>}
    {!loading && !documents.length && !error && <p className="rounded-lg border border-dashed border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">Todavía no hay documentos PPI para este alumno.</p>}
    <div className="space-y-3">{documents.map((doc) => <PpiDocumentCard key={doc.id} document={doc} onNewVersion={canUpload ? newVersion : undefined} />)}</div>
  </div>
}
