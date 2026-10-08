"use client"

import { useEffect, useState } from "react"
import { Bell, CheckCircle, FileText } from "lucide-react"
import { authFetch } from "@/app/_lib/auth"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"

export type PpiRecipient = { id: number; nombre: string; firmado_en?: string | null; ultimo_recordatorio_en?: string | null }
export type PpiDocument = {
  id: number; alumno_id: number; alumno_nombre?: string; titulo: string; nombre_archivo: string;
  tamano: number; creado_en: string; subido_por: string; requiere_firma?: boolean;
  version?: number; reemplazado?: boolean; consultado_en?: string | null; firmado_en?: string | null;
  puede_firmar?: boolean; puede_gestionar?: boolean; destinatarios?: PpiRecipient[];
}
const date = (value: string) => new Date(value).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" })

export default function PpiDocumentCard({ document: initial, onNewVersion, onSigned, showStudent = false }: {
  document: PpiDocument; onNewVersion?: (doc: PpiDocument) => void; onSigned?: () => void; showStudent?: boolean
}) {
  const [doc, setDoc] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [pdfUrl, setPdfUrl] = useState("")
  const [confirm, setConfirm] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const [now, setNow] = useState(Date.now())
  const endpoint = `/alumnos/${doc.alumno_id}/ppi-documentos/${doc.id}`
  useEffect(() => { setDoc(initial) }, [initial])
  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl) }, [pdfUrl])
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 60000); return () => clearInterval(timer) }, [])

  async function openPdf(download: boolean) {
    if (busy) return
    setBusy(true); setError(""); setSuccess("")
    try {
      const response = await authFetch(`${endpoint}/archivo`)
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || "No se pudo abrir el PDF.")
      }
      const url = URL.createObjectURL(await response.blob())
      setDoc((current) => ({ ...current, consultado_en: current.consultado_en || new Date().toISOString() }))
      if (download) {
        const link = document.createElement("a")
        link.href = url; link.download = doc.nombre_archivo
        document.body.appendChild(link); link.click(); link.remove()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      } else setPdfUrl(url)
    } catch (err) { setError(err instanceof Error ? err.message : "No se pudo abrir el PDF.") }
    finally { setBusy(false) }
  }
  async function sign() {
    if (busy || !accepted) return
    setBusy(true); setError(""); setSuccess("")
    try {
      const response = await authFetch(`${endpoint}/firmar`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmo_lectura: true }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "No se pudo registrar la lectura.")
      setDoc((current) => ({ ...current, firmado_en: data.firmado_en, puede_firmar: false }))
      setConfirm(false); setAccepted(false); setSuccess("Lectura confirmada."); onSigned?.()
    } catch (err) { setError(err instanceof Error ? err.message : "No se pudo registrar la lectura.") }
    finally { setBusy(false) }
  }
  async function remind(recipient: PpiRecipient) {
    if (busy) return
    setBusy(true); setError(""); setSuccess("")
    try {
      const response = await authFetch(`${endpoint}/recordar/${recipient.id}`, { method: "POST" })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "No se pudo enviar el recordatorio.")
      setDoc((current) => ({ ...current, destinatarios: current.destinatarios?.map((r) => r.id === recipient.id ? { ...r, ultimo_recordatorio_en: data.ultimo_recordatorio_en } : r) }))
      setSuccess(`Recordatorio enviado a ${recipient.nombre}.`); setNow(Date.now())
    } catch (err) { setError(err instanceof Error ? err.message : "No se pudo enviar el recordatorio.") }
    finally { setBusy(false) }
  }
  return <article id={`ppi-document-${doc.id}`} className="scroll-mt-8 space-y-3 rounded-xl border border-slate-200 bg-white p-4">
    <div className="flex items-start gap-3">
      <FileText aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-violet-600" />
      <div className="min-w-0 flex-1">
        <h3 className="break-words font-semibold">{doc.titulo}</h3>
        {showStudent && <p className="text-sm font-medium text-slate-700">{doc.alumno_nombre}</p>}
        <p className="text-xs text-slate-500">Versión {doc.version || 1} · {date(doc.creado_en)} · {doc.subido_por}</p>
        <p className="break-all text-xs text-slate-500">{doc.nombre_archivo} · {(doc.tamano / 1024).toFixed(0)} KB</p>
      </div>
      {doc.reemplazado && <span className="text-xs text-slate-500">Versión anterior</span>}
    </div>
    {doc.firmado_en ? <p className="flex items-center gap-1 text-sm text-emerald-700"><CheckCircle className="h-4 w-4" />Lectura confirmada · {date(doc.firmado_en)}</p>
      : doc.puede_firmar && <p className="text-sm text-amber-700">Pendiente de firma</p>}
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" disabled={busy} onClick={() => openPdf(false)}>Ver PDF</Button>
      <Button variant="outline" disabled={busy} onClick={() => openPdf(true)}>Descargar PDF</Button>
      {doc.puede_firmar && <Button disabled={busy || !doc.consultado_en} title={!doc.consultado_en ? "Consultá el PDF antes de firmar" : undefined} onClick={() => { setError(""); setAccepted(false); setConfirm(true) }}>Firmar lectura</Button>}
      {onNewVersion && doc.puede_gestionar && !doc.reemplazado && <Button variant="ghost" onClick={() => onNewVersion(doc)}>Nueva versión</Button>}
    </div>
    {doc.puede_firmar && !doc.consultado_en && <p className="text-xs text-slate-500">Abrí o descargá el PDF para habilitar la confirmación de lectura.</p>}
    {doc.puede_gestionar && doc.requiere_firma && <details className="rounded-lg bg-slate-50 p-3">
      <summary className="cursor-pointer text-sm font-medium">Lecturas confirmadas: {doc.destinatarios?.filter((r) => r.firmado_en).length || 0} de {doc.destinatarios?.length || 0}</summary>
      <ul className="mt-3 divide-y divide-slate-200">{doc.destinatarios?.map((recipient) => {
        const cooldown = !!recipient.ultimo_recordatorio_en && now < new Date(recipient.ultimo_recordatorio_en).getTime() + 86400000
        return <li key={recipient.id} className="flex items-center justify-between gap-3 py-2 text-sm">
          <span>{recipient.nombre}</span>
          <div className="flex items-center gap-2">
            <span className={recipient.firmado_en ? "text-emerald-700" : "text-slate-500"}>{recipient.firmado_en ? date(recipient.firmado_en) : "Pendiente"}</span>
            {!recipient.firmado_en && !doc.reemplazado && <button type="button" disabled={busy || cooldown} onClick={() => remind(recipient)} aria-label={`Recordar a ${recipient.nombre}`} title={cooldown ? "Podés enviar otro recordatorio después de 24 horas" : "Enviar recordatorio"} className="rounded-full p-1.5 text-slate-500 hover:text-slate-900 disabled:opacity-40"><Bell aria-hidden="true" className="h-4 w-4" /></button>}
          </div>
        </li>
      })}</ul>
    </details>}
    {error && !confirm && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
    <Dialog open={!!pdfUrl} onOpenChange={(open) => { if (!open) setPdfUrl("") }}>
      <DialogContent className="max-w-4xl">
        <DialogHeader><DialogTitle>{doc.titulo}</DialogTitle><DialogDescription>Versión {doc.version || 1} · {doc.nombre_archivo}</DialogDescription></DialogHeader>
        {pdfUrl && <iframe src={pdfUrl} title={`PDF: ${doc.titulo}`} className="h-[65vh] w-full rounded border" />}
        {doc.puede_firmar && <Button onClick={() => { setPdfUrl(""); setAccepted(false); setError(""); setConfirm(true) }}>Firmar lectura</Button>}
      </DialogContent>
    </Dialog>
    <Dialog open={confirm} onOpenChange={(open) => { if (!busy) setConfirm(open) }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Firmar lectura</DialogTitle><DialogDescription>{doc.titulo} · Versión {doc.version || 1}. La constancia quedará registrada con tu usuario, fecha y hora.</DialogDescription></DialogHeader>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} className="mt-1" />Confirmo que leí las recomendaciones de este documento.</label>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <Button disabled={busy || !accepted} onClick={sign}>{busy ? "Guardando…" : "Confirmar lectura"}</Button>
      </DialogContent>
    </Dialog>
  </article>
}
