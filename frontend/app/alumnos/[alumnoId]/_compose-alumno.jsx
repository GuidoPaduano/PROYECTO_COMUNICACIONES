"use client"

import { useEffect, useMemo, useState } from "react"
import { Send, Mail } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"

import { authFetch } from "../../_lib/auth"

/* ------------------------------------------------------------
   Helpers HTTP
------------------------------------------------------------ */
async function fetchJSON(url, opts) {
  const res = await authFetch(url, opts)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

/**
 * Composer de mensaje DESDE el perfil de un alumno.
 * En este contexto el destinatario se infiere del alumno:
 * - Si el alumno tiene `usuario`, se envía a ese usuario
 * - Sino, se envía al `padre` (si existe)
 *
 * Esto lo resuelve el backend en /api/mensajes/enviar/ recibiendo `alumno_id` o `id_alumno`.
 */
export default function ComposeMensajeAlumno({
  cursoSugerido = "",
  alumnoPk = null,
  alumnoCode = "",
  alumnoNombre = "",
  onSent,
}) {
  const [open, setOpen] = useState(false)
  const [asunto, setAsunto] = useState("")
  const [contenido, setContenido] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState("")
  const [okMsg, setOkMsg] = useState("")

  // ✅ Mostrar SOLO el nombre (sin "Alumno:" ni "Familia de")
  const destinatarioLabel = useMemo(() => {
    const base = String(alumnoNombre || "").trim()
    return base
  }, [alumnoNombre])

  const canSend = useMemo(() => {
    const hasAlumno = alumnoPk != null || String(alumnoCode || "").trim() !== ""
    return hasAlumno && String(asunto || "").trim() && String(contenido || "").trim()
  }, [alumnoPk, alumnoCode, asunto, contenido])

  useEffect(() => {
    if (!open) return
    setError("")
    setOkMsg("")
  }, [open])

  async function handleSend() {
    if (!canSend || sending) return

    setSending(true)
    setError("")
    setOkMsg("")

    try {
      const payload = {
        // Preferimos PK si está
        ...(alumnoPk != null ? { alumno_id: alumnoPk } : { id_alumno: alumnoCode }),
        curso: cursoSugerido || undefined,
        asunto: String(asunto).trim(),
        contenido: String(contenido).trim(),
        tipo: "mensaje",
      }

      const r = await fetchJSON("/mensajes/enviar/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })

      if (!r.ok) {
        const msg =
          r.data?.detail ||
          r.data?.error ||
          `No se pudo enviar (HTTP ${r.status}).`
        throw new Error(msg)
      }

      setOkMsg("Mensaje enviado ✅")
      setAsunto("")
      setContenido("")

      try {
        onSent?.(r.data)
      } catch {}

      // cerramos después de un toque para que se vea el ok
      setTimeout(() => setOpen(false), 650)
    } catch (e) {
      setError(e?.message || "Error al enviar.")
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <Button
        onClick={() => setOpen(true)}
        className="bg-blue-600 hover:bg-blue-700 text-white gap-2"
      >
        <Mail className="w-4 h-4" />
        Enviar mensaje
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          {/* ✅ DialogContent ya trae la X de cierre, no agregamos otra */}
          <div>
            <h2 className="text-lg font-semibold">Nuevo mensaje</h2>
            <p className="text-sm text-gray-600">
              Destinatario preseleccionado según el perfil del alumno.
            </p>
          </div>

          <div className="grid gap-4 mt-2">
            <div>
              <Label className="text-sm">Destinatario</Label>
              <div className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-gray-50 text-gray-800">
                {destinatarioLabel}
              </div>
              {alumnoPk == null && !String(alumnoCode || "").trim() && (
                <p className="text-xs text-red-600 mt-1">
                  Falta identificar el alumno. Probá recargar el perfil.
                </p>
              )}
            </div>

            <div>
              <Label className="text-sm">Asunto</Label>
              <Input
                className="mt-1"
                value={asunto}
                onChange={(e) => setAsunto(e.target.value)}
                placeholder="Ej: Consulta sobre la tarea"
              />
            </div>

            <div>
              <Label className="text-sm">Mensaje</Label>
              <Textarea
                className="mt-1 min-h-[140px]"
                value={contenido}
                onChange={(e) => setContenido(e.target.value)}
                placeholder="Escribí el mensaje…"
              />
            </div>

            {error && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-3">
                {error}
              </div>
            )}
            {okMsg && (
              <div className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md p-3">
                {okMsg}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cancelar
              </Button>
              <Button
                onClick={handleSend}
                disabled={!canSend || sending}
                className="bg-blue-600 hover:bg-blue-700 text-white gap-2"
              >
                <Send className="w-4 h-4" />
                {sending ? "Enviando…" : "Enviar"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
