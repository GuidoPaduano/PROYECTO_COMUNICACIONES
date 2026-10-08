"use client"

import { useEffect, useState } from "react"
import { authFetch } from "@/app/_lib/auth"
import PpiDocumentCard, { PpiDocument } from "./ppi-document-card"
import { Button } from "./ui/button"

export default function PpiDocumentInbox() {
  const [docs, setDocs] = useState<PpiDocument[]>([])
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true); setError("")
    ;(async () => {
      try {
        const response = await authFetch('/ppi-documentos/recibidos')
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "No se pudieron cargar las recomendaciones PPI.")
        if (active) setDocs(data.documents || [])
      } catch (err) { if (active) setError(err instanceof Error ? err.message : "No se pudieron cargar las recomendaciones PPI.") }
      finally { if (active) setLoading(false) }
    })()
    return () => { active = false }
  }, [retry])
  useEffect(() => {
    if (loading) return
    const id = new URLSearchParams(window.location.search).get('ppi_document')
    if (id && /^\d+$/.test(id)) document.getElementById(`ppi-document-${id}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }, [loading])
  if (loading) return <p role="status" className="mb-4 text-sm text-slate-500">Cargando recomendaciones PPI…</p>
  if (error) return <div role="alert" className="mb-4 text-sm text-red-700">{error} <Button variant="outline" onClick={() => setRetry((n) => n + 1)}>Reintentar</Button></div>
  if (!docs.length) return null
  const pending = docs.filter((doc) => doc.puede_firmar)
  const history = docs.filter((doc) => !doc.puede_firmar)
  const card = (doc: PpiDocument) => <PpiDocumentCard key={doc.id} document={doc} showStudent onSigned={() => setRetry((n) => n + 1)} />
  return <section className="mb-8 space-y-4" aria-label="Recomendaciones PPI">
    <h2 className="text-lg font-semibold">Recomendaciones PPI</h2>
    <h3 className="text-sm font-medium text-slate-600">Pendientes de firma ({pending.length})</h3>
    {pending.length ? pending.map(card) : <p className="text-sm text-emerald-700">No tenés lecturas pendientes.</p>}
    {!!history.length && <><h3 className="pt-2 text-sm font-medium text-slate-600">Lecturas confirmadas y versiones anteriores</h3>{history.map(card)}</>}
  </section>
}
