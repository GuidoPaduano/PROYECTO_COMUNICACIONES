"use client"

import { FormEvent, useEffect, useRef, useState } from "react"
import { authFetch } from "../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

type Document = { id: number; titulo: string; nombre_archivo: string; tamano: number; creado_en: string; subido_por: string }

export default function PpiDocuments({ alumnoId }: { alumnoId: number }) {
  const [documents, setDocuments] = useState<Document[]>([])
  const [canUpload, setCanUpload] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [title, setTitle] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)
  const [downloading, setDownloading] = useState<number | null>(null)
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
        if (alive) { setDocuments(data.documents); setCanUpload(data.can_upload) }
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
    setSaving(true)
    try {
      const body = new FormData()
      body.append("titulo", title.trim())
      body.append("archivo", file)
      const response = await authFetch(endpoint, { method: "POST", body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "No se pudo subir el PDF.")
      setDocuments((current) => [data.document, ...current])
      setTitle(""); setFile(null)
      if (fileInput.current) fileInput.current.value = ""
      setSuccess("PDF guardado correctamente.")
    } catch (err) { setError(err instanceof Error ? err.message : "No se pudo subir el PDF.") }
    finally { setSaving(false) }
  }

  async function download(doc: Document) {
    if (downloading !== null) return
    setDownloading(doc.id); setError("")
    try {
      const response = await authFetch(`${endpoint}/${doc.id}/archivo`)
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || "No se pudo descargar el PDF.")
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement("a")
      link.href = url; link.download = doc.nombre_archivo
      document.body.appendChild(link); link.click(); link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) { setError(err instanceof Error ? err.message : "No se pudo descargar el PDF.") }
    finally { setDownloading(null) }
  }

  return <div className="space-y-5">
    <div><h2 className="text-xl font-semibold">Documentación</h2><p className="text-sm text-slate-600">Informes y documentación de acompañamiento de este alumno.</p></div>
    {loading && <p role="status">Cargando documentación…</p>}
    {error && <div role="alert" className="text-sm text-red-700"><p>{error}</p><Button variant="outline" onClick={() => setRetry((value) => value + 1)}>Reintentar</Button></div>}
    {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
    {!loading && canUpload && <form onSubmit={upload} className="space-y-3 rounded-xl border border-slate-200 p-4">
      <h3 className="font-semibold">Subir PDF</h3>
      <fieldset disabled={saving} className="space-y-3">
        <div><Label htmlFor="ppi-document-title">Título</Label><Input id="ppi-document-title" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Por ejemplo: informe de acompañamiento" /></div>
        <div><Label htmlFor="ppi-document-file">Archivo PDF</Label><Input id="ppi-document-file" ref={fileInput} type="file" accept=".pdf,application/pdf" required onChange={(e) => setFile(e.target.files?.[0] || null)} /><p className="mt-1 text-xs text-slate-600">Hasta 20 MB por archivo.</p></div>
        <Button type="submit">{saving ? "Subiendo…" : "Subir PDF"}</Button>
      </fieldset>
    </form>}
    {!loading && !documents.length && !error && <p className="text-sm text-slate-600">Todavía no hay documentos para este alumno.</p>}
    <ul className="space-y-3">{documents.map((doc) => <li key={doc.id} className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0"><h3 className="break-words font-semibold">{doc.titulo}</h3><p className="text-sm text-slate-600">{new Date(doc.creado_en).toLocaleDateString("es-AR")} · {doc.subido_por}</p><p className="break-all text-xs text-slate-500">{doc.nombre_archivo} · {(doc.tamano / 1024).toFixed(0)} KB</p></div>
      <Button variant="outline" disabled={downloading !== null} onClick={() => download(doc)}>{downloading === doc.id ? "Descargando…" : "Descargar PDF"}</Button>
    </li>)}</ul>
  </div>
}
