"use client"

import { useEffect, useState } from "react"
import { Bell } from "lucide-react"
import { authFetch } from "@/app/_lib/auth"

type Message = { id: number; leido?: boolean; leido_en?: string | null; ultimo_recordatorio_en?: string | null; recordatorio_resuelto_en?: string | null; recordatorio_respondido?: boolean }
export default function MessageReminder({ message, className = "" }: { message: Message; className?: string }) {
  const [state, setState] = useState(message)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState("")
  const [error, setError] = useState("")
  const [now, setNow] = useState(Date.now())
  useEffect(() => { setState(message) }, [message])
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000)
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail
      if (detail.id === message.id) setState((current) => ({ ...current, ...detail }))
    }
    window.addEventListener("message-reminder-updated", handler)
    return () => { clearInterval(timer); window.removeEventListener("message-reminder-updated", handler) }
  }, [message.id])
  const last = state.ultimo_recordatorio_en ? new Date(state.ultimo_recordatorio_en).getTime() : 0
  const cooldown = !!last && now < last + 24 * 60 * 60 * 1000
  const done = !!state.recordatorio_resuelto_en || state.recordatorio_respondido
  async function send() {
    if (busy) return
    setBusy(true); setFeedback(""); setError("")
    try {
      const response = await authFetch(`/mensajes/${message.id}/recordatorio`, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ accion: "recordar" }) })
      const data = await response.json()
      if (data.ultimo_recordatorio_en || data.recordatorio_resuelto_en || data.recordatorio_respondido) {
        window.dispatchEvent(new CustomEvent("message-reminder-updated", { detail: { id: message.id, ...data } }))
      }
      if (!response.ok) throw new Error(data.detail || "No se pudo completar la acción.")
      setFeedback(data.detail)
    } catch (err) { setError(err instanceof Error ? err.message : "No se pudo completar la acción.") }
    finally { setBusy(false); setNow(Date.now()) }
  }
  if (done) return null
  const hint = error || (busy ? "Enviando recordatorio…" : cooldown
    ? "Recordatorio enviado. Podés enviar otro 24 horas después del último."
    : feedback || "Enviar recordatorio")
  return <div className={className} onClick={(e) => e.stopPropagation()}>
    <button
      type="button"
      disabled={busy || cooldown}
      onClick={() => send()}
      title={hint}
      aria-label="Enviar recordatorio"
      className="inline-flex h-7 w-7 items-center justify-center rounded-full opacity-70 transition-opacity hover:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-current disabled:opacity-40"
    >
      <Bell aria-hidden="true" className={"h-4 w-4" + (busy ? " animate-pulse" : "")} />
    </button>
    {feedback && <span role="status" className="sr-only">{feedback}</span>}
    {error && <span role="alert" className="sr-only">{error}</span>}
  </div>
}
