"use client"

import { useEffect, useMemo, useState } from "react"
import { ArrowLeftRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import SuccessMessage from "@/components/ui/success-message"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Label } from "@/components/ui/label"

import { authFetch } from "../../_lib/auth"
import {
  getCourseCode,
  getCourseLabel,
  getCourseSchoolCourseId,
  normalizeCourseList,
} from "../../_lib/courses"

async function fetchJSON(url, opts) {
  const res = await authFetch(url, opts)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

function normalizeCursos(data) {
  const list = Array.isArray(data)
    ? data
    : Array.isArray(data?.cursos)
    ? data.cursos
    : []
  return normalizeCourseList(list)
}

export default function TransferAlumno({
  alumnoPk = null,
  alumnoCode = "",
  cursoActual = "",
  onTransferred,
}) {
  const [open, setOpen] = useState(false)
  const [cursos, setCursos] = useState([])
  const [cursoSel, setCursoSel] = useState("")
  const [loadingCursos, setLoadingCursos] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState("")
  const [okMsg, setOkMsg] = useState("")

  const currentCurso = getCourseCode(cursoActual) || String(cursoActual || "").trim()
  const cursoSelId = useMemo(() => getCourseSchoolCourseId(cursoSel, cursos), [cursoSel, cursos])

  useEffect(() => {
    if (!open) return
    let alive = true
    setError("")
    setOkMsg("")
    setCursos([])
    setCursoSel("")
    setLoadingCursos(true)

    ;(async () => {
      const tries = ["/alumnos/cursos/", "/notas/catalogos/", "/preceptor/cursos/"]
      let found = []
      for (const url of tries) {
        try {
          const r = await fetchJSON(url)
          if (!r.ok) continue
          const list = normalizeCursos(r.data)
          if (list.length) {
            found = list
            break
          }
        } catch {}
      }
      if (!alive) return
      setCursos(found)
    })().finally(() => alive && setLoadingCursos(false))

    return () => {
      alive = false
    }
  }, [open])

  useEffect(() => {
    if (!open || !cursos.length) return
    const preferred = cursos.find((c) => c.value && c.courseCode !== currentCurso) || cursos[0]
    if (preferred?.value) setCursoSel(preferred.value)
  }, [open, cursos, currentCurso])

  const canTransfer = useMemo(() => {
    const hasAlumno =
      alumnoPk != null || String(alumnoCode || "").trim() !== ""
    if (!hasAlumno) return false
    if (!cursoSel) return false
    if (cursoSelId == null) return false
    return String(getCourseCode(cursoSel, cursos) || cursoSel) !== String(currentCurso || "")
  }, [alumnoPk, alumnoCode, cursoSel, cursoSelId, currentCurso, cursos])

  async function handleTransfer() {
    if (!canTransfer || sending) return
    setSending(true)
    setError("")
    setOkMsg("")

    try {
      if (cursoSelId == null) {
        throw new Error("No se pudo resolver el curso seleccionado.")
      }
      const payload = {
        ...(alumnoPk != null ? { alumno_id: alumnoPk } : { id_alumno: alumnoCode }),
        school_course_id: cursoSelId,
      }

      const r = await fetchJSON("/alumnos/transferir/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })

      if (!r.ok) {
        const msg =
          r.data?.detail ||
          `No se pudo transferir (HTTP ${r.status}).`
        throw new Error(msg)
      }

      setOkMsg("Alumno transferido correctamente.")
      try {
        onTransferred?.(r.data)
      } catch {}

      setTimeout(() => setOpen(false), 800)
    } catch (e) {
      setError(e?.message || "Error al transferir.")
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <Button onClick={() => setOpen(true)} className="gap-2 primary-button">
        <ArrowLeftRight className="w-4 h-4" />
        Transferir alumno
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Transferir alumno</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4">
            <div className="text-sm text-gray-600">
              Curso actual: <b>{currentCurso || "—"}</b>
            </div>

            <div>
              <Label className="text-sm">Nuevo curso</Label>
              <Select
                value={cursoSel}
                onValueChange={setCursoSel}
                disabled={loadingCursos || sending}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue
                    placeholder={
                      loadingCursos ? "Cargando..." : "Seleccionar curso"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {cursos.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {getCourseLabel(c)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {error && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-3">
                {error}
              </div>
            )}
            {okMsg && <SuccessMessage className="mt-1">{okMsg}</SuccessMessage>}
          </div>

          <DialogFooter className="mt-4">
            <Button onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleTransfer}
              disabled={!canTransfer || sending}
              className="gap-2"
            >
              {sending ? "Transfiriendo..." : "Transferir"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

