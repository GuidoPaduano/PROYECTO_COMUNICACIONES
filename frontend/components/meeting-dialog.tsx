"use client"

import { useEffect, useState } from "react"
import { CalendarPlus } from "lucide-react"
import { authFetch } from "@/app/_lib/auth"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

type Staff = { id: number; nombre: string; roles: string[] }
type Options = { alumno: { id: number; nombre: string }; familiar: { id: number; nombre: string } | null; personal: Staff[] }

export default function MeetingDialog({ alumnoId, onCreated }: {
  alumnoId: number | string
  onCreated?: (data: { id: number; mensaje_id: number }) => void
}) {
  const [open, setOpen] = useState(false)
  const [options, setOptions] = useState<Options | null>(null)
  const [fecha, setFecha] = useState("")
  const [hora, setHora] = useState("")
  const [duracion, setDuracion] = useState("30")
  const [modalidad, setModalidad] = useState("presencial")
  const [lugar, setLugar] = useState("")
  const [motivo, setMotivo] = useState("")
  const [search, setSearch] = useState("")
  const [staffIds, setStaffIds] = useState<number[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!open || !alumnoId) return
    let active = true
    setLoading(true)
    setError("")
    authFetch(`/reuniones/opciones/?alumno_id=${encodeURIComponent(String(alumnoId))}`)
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data.detail || "No se pudieron cargar los invitados.")
        if (active) setOptions(data)
      })
      .catch((cause) => { if (active) setError(cause.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [open, alumnoId])

  async function create() {
    setError("")
    if (!fecha || !hora || (modalidad === "virtual" && !lugar.trim()) || !motivo.trim()) {
      setError("Completá fecha, hora, motivo y, si es virtual, el enlace.")
      return
    }
    const inicio = new Date(`${fecha}T${hora}`)
    if (Number.isNaN(inicio.getTime()) || inicio <= new Date()) {
      setError("Elegí una fecha y hora futuras.")
      return
    }
    setSaving(true)
    try {
      const response = await authFetch("/reuniones/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          alumno_id: alumnoId, inicio: inicio.toISOString(), duracion_minutos: Number(duracion),
          modalidad, lugar: modalidad === "virtual" ? lugar.trim() : "", motivo: motivo.trim(), invitados_ids: staffIds,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || "No se pudo programar la reunión.")
      setOpen(false)
      setFecha(""); setHora(""); setLugar(""); setMotivo(""); setStaffIds([])
      onCreated?.(data)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo programar la reunión.")
    } finally {
      setSaving(false)
    }
  }

  const staff = (options?.personal || []).filter((person) =>
    `${person.nombre} ${person.roles.join(" ")}`.toLowerCase().includes(search.toLowerCase())
  )

  return <>
    <Button type="button" onClick={() => setOpen(true)} className="gap-2">
      <CalendarPlus className="h-4 w-4" /> Programar reunión
    </Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Programar reunión</DialogTitle>
          <DialogDescription>La familia recibirá la invitación en su hilo de mensajes.</DialogDescription>
        </DialogHeader>
        {loading ? <p>Cargando…</p> : <div className="space-y-4">
          <div className="rounded-lg bg-slate-50 p-3 text-sm">
            <div>Alumno: <strong>{options?.alumno?.nombre || "—"}</strong></div>
            <div>Familiar invitado: <strong>{options?.familiar?.nombre || "Sin familiar vinculado"}</strong></div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div><Label htmlFor="meeting-date">Fecha</Label><Input id="meeting-date" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} /></div>
            <div><Label htmlFor="meeting-time">Hora</Label><Input id="meeting-time" type="time" value={hora} onChange={(e) => setHora(e.target.value)} /></div>
            <div><Label htmlFor="meeting-duration">Duración</Label>
              <select id="meeting-duration" className="h-10 w-full rounded-md border px-3" value={duracion} onChange={(e) => setDuracion(e.target.value)}>
                {[15, 30, 45, 60, 90, 120].map((minutes) => <option key={minutes} value={minutes}>{minutes} min</option>)}
              </select>
            </div>
          </div>
          <div><Label htmlFor="meeting-modality">Modalidad</Label>
            <select id="meeting-modality" className="h-10 w-full rounded-md border px-3" value={modalidad} onChange={(e) => setModalidad(e.target.value)}>
              <option value="presencial">Presencial</option><option value="virtual">Virtual</option>
            </select>
          </div>
          {modalidad === "virtual" && <div><Label htmlFor="meeting-place">Enlace</Label><Input id="meeting-place" value={lugar} onChange={(e) => setLugar(e.target.value)} maxLength={255} /></div>}
          <div><Label htmlFor="meeting-reason">Motivo breve</Label><Input id="meeting-reason" value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={500} /></div>
          <div className="space-y-2">
            <Label htmlFor="meeting-staff">Invitar personal del colegio (opcional)</Label>
            <Input id="meeting-staff" placeholder="Buscar por nombre o rol" value={search} onChange={(e) => setSearch(e.target.value)} />
            <div className="max-h-32 space-y-1 overflow-y-auto rounded-md border p-2">
              {staff.length ? staff.map((person) => <label key={person.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={staffIds.includes(person.id)} onChange={(e) => setStaffIds((current) => e.target.checked ? [...current, person.id] : current.filter((id) => id !== person.id))} />
                {person.nombre} <span className="text-slate-500">· {person.roles.join(", ")}</span>
              </label>) : <p className="text-sm text-slate-500">No hay personal con ese filtro.</p>}
            </div>
          </div>
          {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button type="button" disabled={saving || !options?.familiar} onClick={create}>{saving ? "Enviando…" : "Enviar invitación"}</Button>
          </div>
        </div>}
      </DialogContent>
    </Dialog>
  </>
}
