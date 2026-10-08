"use client"

import { useState } from "react"
import { authFetch } from "../../_lib/auth"

type Props = {
  alumnoId: number
  value: boolean
  canEdit: boolean
  onSaved: (data: { es_ppi: boolean; can_edit_ppi: boolean }) => void
}

export default function StudentPpi({ alumnoId, value, canEdit, onSaved }: Props) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState(false)

  async function updatePpi(checked: boolean) {
    if (saving || !canEdit) return
    setSaving(true)
    setSaved(false)
    setError("")
    try {
      const response = await authFetch(`/alumnos/${alumnoId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ es_ppi: checked }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data?.detail || "No se pudo guardar PPI.")
      onSaved(data)
      setSaved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar PPI.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-3 space-y-1">
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          className="h-4 w-4 rounded accent-blue-700"
          checked={value}
          disabled={!canEdit || saving}
          onChange={(event) => updatePpi(event.target.checked)}
        />
        <span><strong>PPI</strong> — acompañamiento psicopedagógico</span>
      </label>
      <p role="status" className="text-xs text-slate-600">
        {saving ? "Guardando…" : saved ? "Cambio guardado." : ""}
      </p>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    </div>
  )
}
