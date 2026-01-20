"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"
import { useAuthGuard, authFetch } from "../../../_lib/auth"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, Send, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

async function fetchJSON(url, opts) {
  const res = await authFetch(url, {
    ...opts,
    headers: { Accept: "application/json", ...(opts?.headers || {}) },
  })
  const ct = res.headers.get("content-type") || ""
  if (ct.includes("application/json")) {
    const data = await res.json().catch(() => ({}))
    return { ok: res.ok, status: res.status, data }
  }
  const text = await res.text()
  return { ok: res.ok, status: res.status, text }
}

function fmtFecha(input) {
  if (!input) return "—"
  try {
    const d = new Date(input)
    return d.toLocaleString()
  } catch {
    return String(input)
  }
}

function isUUID(v) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(v || ""))
}

/* === Helper local para notificar cambios en la bandeja (badge/contador) === */
function notifyInboxChanged() {
  try {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("inbox-changed"))
    }
  } catch {}
}

export default function HiloMensajesPage() {
  useAuthGuard()
  const router = useRouter()
  const params = useParams()
  const threadIdParam = Array.isArray(params?.threadId) ? params.threadId[0] : params?.threadId

  const [me, setMe] = useState(null)
  const [mensajes, setMensajes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [refreshTs, setRefreshTs] = useState(0) // solo para botón "Actualizar" y post-envío

  // Respuesta rápida
  const [replyText, setReplyText] = useState("")
  const [replyAsunto, setReplyAsunto] = useState("")
  const [replyToId, setReplyToId] = useState(null)
  const [sending, setSending] = useState(false)
  const [sendMsg, setSendMsg] = useState("")

  // autoscroll
  const listRef = useRef(null)

  // Guard per-hilo para auto-marcado
  const didAutoMarkRef = useRef(false)
  useEffect(() => { didAutoMarkRef.current = false }, [threadIdParam])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        setLoading(true)
        setError("")

        const who = await fetchJSON("/auth/whoami/")
        if (alive && who.ok) setMe(who.data)

        // Cargar por thread_id (UUID) o por mensaje_id (numérico)
        let got = null
        if (isUUID(threadIdParam)) {
          for (const url of [
            `/api/mensajes/conversacion/thread/${threadIdParam}/`,
            `/mensajes/conversacion/thread/${threadIdParam}/`,
            `/api/mensajes/conversacion/thread/${threadIdParam}`,
            `/mensajes/conversacion/thread/${threadIdParam}`,
          ]) {
            const r = await fetchJSON(url)
            if (r.ok && Array.isArray(r.data?.mensajes)) { got = r; break }
          }
        } else if (/^\d+$/.test(String(threadIdParam || ""))) {
          for (const url of [
            `/api/mensajes/conversacion/${threadIdParam}/`,
            `/mensajes/conversacion/${threadIdParam}/`,
            `/api/mensajes/conversacion/${threadIdParam}`,
            `/mensajes/conversacion/${threadIdParam}`,
          ]) {
            const r = await fetchJSON(url)
            if (r.ok && Array.isArray(r.data?.mensajes)) { got = r; break }
          }
        }

        if (!got?.ok) {
          setError("No se pudo cargar el hilo.")
          return
        }

        const msgs = Array.isArray(got.data?.mensajes) ? got.data.mensajes : []
        const myId = who?.data?.id ?? who?.data?.user?.id

        // Elegir por defecto: último que YO recibí
        const recvd = msgs.filter(m => m.receptor_id && myId && m.receptor_id === myId)
        const base = recvd.length ? recvd[recvd.length - 1] : (msgs.length ? msgs[msgs.length - 1] : null)

        if (alive) {
          setMensajes(msgs)
          setReplyToId(base?.id ?? null)
          setReplyAsunto(base?.asunto ? `Re: ${base.asunto}` : "Re:")
        }

        // Auto-marcado: SOLO si el backend expone flags y SOLO una vez por hilo.
        if (!didAutoMarkRef.current && myId && msgs.length) {
          const toMark = msgs.filter(m => {
            const hasLeido = Object.prototype.hasOwnProperty.call(m, "leido")
            const hasLeidoEn = Object.prototype.hasOwnProperty.call(m, "leido_en")
            const hasFlags = hasLeido || hasLeidoEn
            if (!hasFlags) return false
            const isMine = m.receptor_id === myId
            const isUnread =
              (hasLeido && m.leido === false) ||
              (hasLeidoEn && (m.leido_en === null || m.leido_en === undefined))
            return isMine && isUnread
          })

          if (toMark.length) {
            didAutoMarkRef.current = true
            const ids = toMark.map(c => c.id).filter(Boolean)

            // Marcamos en backend (best-effort) y actualizamos UI local sin refrescar
            Promise.allSettled(
              ids.map((id) =>
                fetchJSON(`/mensajes/${id}/marcar_leido/`, { method: "POST" })
                  .then(r => (r.ok ? r : fetchJSON(`/api/mensajes/${id}/marcar_leido/`, { method: "POST" })))
              )
            ).finally(() => {
              setMensajes(prev =>
                prev.map(m =>
                  ids.includes(m.id)
                    ? { ...m, leido: true, leido_en: m.leido_en || new Date().toISOString() }
                    : m
                )
              )
              // Avisar al dashboard para refrescar el badge
              notifyInboxChanged()
            })
          }
        }
      } catch (e) {
        if (alive) setError(e?.message || "Error inesperado.")
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [threadIdParam, refreshTs])

  // autoscroll al final
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [mensajes])

  async function enviarRespuesta() {
    if (!replyToId) {
      setSendMsg("No hay un mensaje de referencia para responder todavía.")
      return
    }
    if (!replyText.trim()) {
      setSendMsg("Escribí un mensaje.")
      return
    }
    setSending(true)
    setSendMsg("")
    const payload = { mensaje_id: replyToId, asunto: replyAsunto || "Re:", contenido: replyText.trim() }
    let ok = false, lastErr = ""
    for (const url of ["/api/mensajes/responder/", "/mensajes/responder/"]) {
      const r = await fetchJSON(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (r.ok) { ok = true; break }
      lastErr = r?.data?.detail || r?.text || `HTTP ${r?.status}`
    }
    setSending(false)
    if (ok) {
      setReplyText("")
      setSendMsg("✅ Enviado. Actualizando hilo…")
      // (enviar respuesta no reduce tus no-leídos, pero invalidamos para que otros badges se sincronicen)
      notifyInboxChanged()
      setTimeout(() => setRefreshTs(ts => ts + 1), 400) // refresco solo tras enviar
    } else {
      setSendMsg(`No se pudo enviar: ${lastErr}`)
    }
  }

  const myId = me?.id ?? me?.user?.id

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <Button variant="outline" onClick={() => router.back()} className="gap-2">
            <ArrowLeft className="h-4 w-4" /> Volver
          </Button>
          <div className="text-sm text-gray-600">Hilo</div>
          <Button variant="ghost" className="ml-auto gap-2" onClick={() => setRefreshTs(ts => ts + 1)}>
            <RefreshCcw className="h-4 w-4" /> Actualizar
          </Button>
        </div>

        <Card>
          <CardContent className="p-6">
            {loading ? (
              <div className="text-sm text-gray-600">Cargando hilo…</div>
            ) : error ? (
              <div className="text-sm text-red-600">{error}</div>
            ) : mensajes.length === 0 ? (
              <div className="text-sm text-gray-600">No hay mensajes en este hilo.</div>
            ) : (
              <div ref={listRef} className="space-y-4 max-h-[55vh] overflow-auto pr-1">
                {mensajes.map((m) => {
                  const mine = m.emisor_id && myId && m.emisor_id === myId
                  const canReplyToThis = m.receptor_id && myId && m.receptor_id === myId
                  const isReplyTarget = m.id === replyToId
                  return (
                    <div key={m.id} className={"flex " + (mine ? "justify-end" : "justify-start")}>
                      <div
                        className={
                          (mine ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-900")
                          + " max-w-[80%] rounded-2xl px-4 py-2 shadow-sm border "
                          + (isReplyTarget ? (mine ? "border-white/70" : "border-blue-300") : "border-transparent")
                        }
                      >
                        <div className="text-xs opacity-80 mb-1 flex items-center justify-between gap-3">
                          <span className="truncate">{mine ? "Vos" : (m.emisor || "—")}</span>
                          <span className="truncate">{fmtFecha(m.fecha || m.fecha_envio)}</span>
                        </div>
                        <div className="font-medium break-words">{m.asunto || "Sin asunto"}</div>
                        <div className="mt-1 whitespace-pre-wrap break-words">{m.contenido || m.body || ""}</div>

                        {canReplyToThis && (
                          <div className={"mt-2 text-[12px] " + (mine ? "text-white/80" : "text-gray-600")}>
                            <button
                              className={"underline hover:opacity-80 " + (isReplyTarget ? "font-semibold" : "")}
                              onClick={() => {
                                setReplyToId(m.id)
                                setReplyAsunto(m.asunto ? `Re: ${m.asunto}` : "Re:")
                              }}
                            >
                              {isReplyTarget ? "Respondiendo a este" : "Responder a este"}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Responder */}
        <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm mt-4">
          <CardContent className="p-6 space-y-3">
            <div className="text-sm text-gray-700">
              Estás respondiendo dentro de este hilo. Por defecto se responde al último que recibiste.
            </div>
            <div>
              <Label htmlFor="asunto">Asunto</Label>
              <Input
                id="asunto"
                value={replyAsunto}
                onChange={(e) => setReplyAsunto(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="mensaje">Mensaje</Label>
              <Textarea
                id="mensaje"
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                rows={5}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                    e.preventDefault()
                    enviarRespuesta()
                  }
                }}
              />
              <div className="text-[11px] text-gray-500 mt-1">Tip: Ctrl/⌘ + Enter para enviar</div>
            </div>
            {sendMsg && (
              <div className={"text-sm " + (sendMsg.startsWith("✅") ? "text-green-700" : "text-red-600")}>
                {sendMsg}
              </div>
            )}
            <div className="flex items-center justify-end">
              <Button onClick={enviarRespuesta} disabled={sending || !replyToId} className="gap-2">
                <Send className="h-4 w-4" />
                {sending ? "Enviando…" : "Enviar respuesta"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
