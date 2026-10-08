"use client"

import { FormEvent, useEffect, useRef, useState } from "react"
import { authFetch } from "../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import PpiDocumentCard, { PpiDocument } from "@/components/ppi-document-card"

type Teacher = { id: number; nombre: string }

export default function PpiDocuments({ alumnoId }: { alumnoId: number }) {
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

  async function upload(event: FormEvent) {
    event.preventDefault()
    if (saving) return
    setError(""); setSuccess("")
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) { setError("Seleccioná un archivo PDF."); return }
    if (file.size > 20 * 1024 * 1024) { setError("El PDF debe pesar como máximo 20 MB."); return }
    if (!title.trim()) { setError("Ingresá un título."); return }
    if (requiresSignature && !selected.length) { setError("Seleccioná al menos un docente."); return }
    setSaving(true)
    try {
      const body = new FormData()
      body.append("titulo", title.trim())
      body.append("archivo", file)
      body.append("requiere_firma", String(requiresSignature))
      body.append("docentes", JSON.stringify(selected))
      if (previous) body.append("version_anterior_id", String(previous.id))
      const response = await authFetch(endpoint, { method: "POST", body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "No se pudo subir el PDF.")
      setDocuments((current) => [{ ...data.document, alumno_id: alumnoId }, ...current.map((doc) => doc.id === previous?.id ? { ...doc, reemplazado: true } : doc)])
      setTitle(""); setFile(null); setPrevious(null); setRequiresSignature(false); setSelected([])
      if (fileInput.current) fileInput.current.value = ""
      setSuccess("PDF guardado correctamente.")
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
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">Documentación</h2><p className="text-sm text-slate-600">Informes y documentación de acompañamiento de este alumno.</p></div><Button variant="ghost" disabled={loading || saving} onClick={() => setRetry((value) => value + 1)}>Actualizar</Button></div>
    {loading && <p role="status">Cargando documentación…</p>}
    {error && <div role="alert" className="text-sm text-red-700"><p>{error}</p><Button variant="outline" onClick={() => setRetry((value) => value + 1)}>Reintentar</Button></div>}
    {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
    {!loading && canUpload && <form ref={formRef} onSubmit={upload} className="space-y-3 rounded-xl border border-slate-200 p-4">
      <div className="flex items-center justify-between gap-2"><h3 className="font-semibold">{previous ? `Nueva versión de ${previous.titulo}` : "Subir PDF"}</h3>
      {previous && <Button type="button" variant="ghost" disabled={saving} onClick={() => { setPrevious(null); setTitle(""); setRequiresSignature(false); setSelected([]) }}>Cancelar versión</Button>}</div>
      {previous && <p className="text-sm text-slate-600">Se conservarán el PDF anterior y sus constancias. Los docentes deberán confirmar la lectura de esta nueva versión.</p>}
      <fieldset disabled={saving} className="space-y-3">
        <div><Label htmlFor="ppi-document-title">Título</Label><Input id="ppi-document-title" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Por ejemplo: informe de acompañamiento" /></div>
        <div><Label htmlFor="ppi-document-file">Archivo PDF</Label><Input id="ppi-document-file" ref={fileInput} type="file" accept=".pdf,application/pdf" required onChange={(e) => setFile(e.target.files?.[0] || null)} /><p className="mt-1 text-xs text-slate-600">Hasta 20 MB por archivo.</p></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={requiresSignature} disabled={!!previous?.requiere_firma} onChange={(e) => setRequiresSignature(e.target.checked)} />Requiere constancia de lectura</label>
        {requiresSignature && <div className="space-y-2 rounded-lg bg-slate-50 p-3">
          <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">Docentes destinatarios</span><Button type="button" variant="ghost" onClick={() => setSelected(selected.length === teachers.length ? [] : teachers.map((teacher) => teacher.id))}>{selected.length === teachers.length && teachers.length ? "Quitar selección" : "Seleccionar todos"}</Button></div>
          {!teachers.length && <p className="text-sm text-amber-700">Este alumno todavía no tiene docentes asignados a su curso.</p>}
          {teachers.map((teacher) => <label key={teacher.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selected.includes(teacher.id)} onChange={(e) => setSelected((current) => e.target.checked ? [...current, teacher.id] : current.filter((id) => id !== teacher.id))} />{teacher.nombre}</label>)}
        </div>}
        <Button type="submit">{saving ? "Subiendo…" : "Subir PDF"}</Button>
      </fieldset>
    </form>}
    {!loading && !documents.length && !error && <p className="text-sm text-slate-600">Todavía no hay documentos para este alumno.</p>}
    <div className="space-y-3">{documents.map((doc) => <PpiDocumentCard key={doc.id} document={doc} onNewVersion={canUpload ? newVersion : undefined} />)}</div>
  </div>
}
