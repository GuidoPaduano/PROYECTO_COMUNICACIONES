"use client"

import { useEffect, useState } from "react"
import { authFetch } from "@/app/_lib/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

type Meeting = {
  id: number
  inicio: string
  duracion_minutos: number
  modalidad: string
  lugar: string
  motivo: string
  estado: string
  alumno_nombre?: string
  organizador?: string
  familiar?: string
  respuesta_familiar_en?: string | null
  confirmado_en?: string | null
  nota_familiar?: string
  puede_editar?: boolean
  puede_responder?: boolean
  es_familiar?: boolean
  invitados?: { id: number; nombre: string; confirmado_en: string | null }[]
}

export default function MeetingCard({ id, onChanged }: { id: number; onChanged?: () => void }) {
  const [meeting, setMeeting] = useState<Meeting | null>(null)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState(false)
  const [changeRequest, setChangeRequest] = useState(false)
  const [note, setNote] = useState("")
  const [editing, setEditing] = useState(false)
  const [inicio, setInicio] = useState("")
  const [lugar, setLugar] = useState("")
  const [motivo, setMotivo] = useState("")

  useEffect(() => {
    let active = true
    authFetch(`/reuniones/${id}/`).then(async (response) => {
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || "No se pudo cargar la reunión.")
      if (active) setMeeting(data)
    }).catch((cause) => { if (active) setError(cause.message) })
    return () => { active = false }
  }, [id])

  async function submit(path: string, body: Record<string, unknown> = {}, method = "POST") {
    setBusy(true); setError(""); setNotice("")
    try {
      const response = await authFetch(`/reuniones/${id}/${path}`, {
        method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || "No se pudo actualizar la reunión.")
      if (data.id) setMeeting(data)
      if (typeof data.enviados === "number") setNotice(data.enviados ? `Se enviaron ${data.enviados} recordatorio(s).` : "No hay confirmaciones pendientes.")
      setChangeRequest(false); setEditing(false); setNote("")
      onChanged?.()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo actualizar la reunión.")
    } finally { setBusy(false) }
  }

  if (!meeting) return <div className="rounded-lg border bg-white p-3 text-sm text-slate-600">{error || "Cargando reunión…"}</div>
  const date = new Date(meeting.inicio)
  const dateLabel = new Intl.DateTimeFormat("es-AR", { dateStyle: "full", timeStyle: "short" }).format(date)
  const localInput = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  const status = { pendiente: "Pendiente", confirmada: "Confirmada", cambio_solicitado: "Cambio solicitado", cancelada: "Cancelada" }[meeting.estado] || meeting.estado

  return <div className="rounded-xl border border-blue-200 bg-white p-4 text-sm text-slate-900 shadow-sm">
    <div className="font-semibold">Reunión por {meeting.alumno_nombre || "el alumno"}</div>
    <div className="mt-1 capitalize">{dateLabel} · {meeting.duracion_minutos} min</div>
    <div>{meeting.modalidad === "virtual" ? `Virtual · ${meeting.lugar}` : "Presencial"}</div>
    <div className="mt-1">{meeting.motivo}</div>
    <div className="mt-2 font-medium">Estado de la familia: {status}</div>
    {meeting.nota_familiar && <div className="mt-1">Solicitud: {meeting.nota_familiar}</div>}
    {meeting.puede_editar && meeting.invitados?.length ? <div className="mt-2 border-t pt-2">
      Invitados: {meeting.invitados.map((person) => `${person.nombre} (${person.confirmado_en ? "confirmó" : "pendiente"})`).join(", ")}
    </div> : null}
    {meeting.estado !== "cancelada" && <div className="mt-3 flex flex-wrap gap-2">
      {meeting.puede_responder && !meeting.puede_editar && !meeting.confirmado_en && <Button type="button" disabled={busy} onClick={() => submit("responder/", { accion: "confirmar" })}>Confirmar</Button>}
      {meeting.es_familiar && !changeRequest && <Button type="button" variant="outline" disabled={busy} onClick={() => setChangeRequest(true)}>Solicitar otro horario</Button>}
      {meeting.puede_editar && <>
        <Button type="button" variant="outline" disabled={busy} onClick={() => { setInicio(localInput); setLugar(meeting.lugar); setMotivo(meeting.motivo); setEditing(true) }}>Cambiar horario</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => submit("recordatorio/", {})}>Recordar pendientes</Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => submit("", { cancelar: true }, "PATCH")}>Cancelar reunión</Button>
      </>}
    </div>}
    {changeRequest && <div className="mt-3 space-y-2">
      <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Comentá qué horario te conviene (opcional)" maxLength={500} />
      <div className="flex gap-2"><Button type="button" disabled={busy} onClick={() => submit("responder/", { accion: "solicitar_cambio", nota: note })}>Enviar solicitud</Button><Button type="button" variant="outline" onClick={() => setChangeRequest(false)}>Volver</Button></div>
    </div>}
    {editing && <div className="mt-3 space-y-2">
      <label className="block">Nueva fecha y hora<Input type="datetime-local" value={inicio} onChange={(e) => setInicio(e.target.value)} /></label>
      {meeting.modalidad === "virtual" && <label className="block">Enlace<Input value={lugar} onChange={(e) => setLugar(e.target.value)} /></label>}
      <label className="block">Motivo<Input value={motivo} onChange={(e) => setMotivo(e.target.value)} /></label>
      <div className="flex gap-2"><Button type="button" disabled={busy} onClick={() => {
        const date = new Date(inicio)
        if (Number.isNaN(date.getTime())) { setError("Fecha y hora inválidas."); return }
        submit("", { inicio: date.toISOString(), duracion_minutos: meeting.duracion_minutos, modalidad: meeting.modalidad, lugar, motivo }, "PATCH")
      }}>Guardar cambio</Button><Button type="button" variant="outline" onClick={() => setEditing(false)}>Volver</Button></div>
    </div>}
    {error && <p className="mt-2 text-red-600" role="alert">{error}</p>}
    {notice && <p className="mt-2 text-green-700" role="status">{notice}</p>}
  </div>
}
