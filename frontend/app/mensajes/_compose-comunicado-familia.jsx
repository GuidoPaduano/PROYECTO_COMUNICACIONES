"use client"

import { useEffect, useMemo, useState } from "react"
import { authFetch } from "../_lib/auth"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import SuccessMessage from "@/components/ui/success-message"

/** Utilidad para tomar la primera key existente */
function pick(a, ...keys) {
  for (const k of keys) {
    if (a?.[k] !== undefined && a?.[k] !== null) return a[k]
  }
  return undefined
}

function cursoIdOf(c) {
  const id = pick(c, "id", "value", "curso")
  return String(id ?? c ?? "")
}

function cursoLabelOf(c) {
  const label = pick(c, "nombre", "label")
  return String(label ?? cursoIdOf(c))
}

function alumnoIdOf(a) {
  const id = pick(a, "id", "alumno_id", "id_alumno", "pk")
  return id == null ? "" : String(id)
}

function fullName(u) {
  if (!u) return ""
  const name = [u?.last_name, u?.first_name].filter(Boolean).join(", ")
  return (name || u?.username || u?.email || "").trim()
}

/**
 * Modal de “Comunicados / Mensajes” para Preceptores.
 *
 * Soporta 3 modos de envío (selector "Enviar a"):
 *  1) Familia (padre/madre/tutor) de un alumno (modo = "familia")
 *  2) Alumno individual del curso (modo = "alumno")
 *  3) TODOS los alumnos de un curso (modo = "curso_alumnos")
 *
 * Endpoints usados:
 *  - GET  /api/preceptor/cursos/
 *  - GET  /api/alumnos/?curso=ID
 *  - POST /api/mensajes/enviar/        { alumno_id | receptor_id, asunto, contenido, tipo }
 *  - POST /api/mensajes/enviar_grupal/ { curso, asunto, contenido, tipo }
 *
 * Compatibilidad: conserva la API original (props) y el flujo previo para "Familia".
 */
/**
 * ✅ Ahora también lo pueden usar Profesores (y Superusuarios) sin duplicar UI.
 *
 * Props nuevas:
 *  - cursosEndpoint: endpoint que devuelve cursos.
 *      * Preceptor:  GET /api/preceptor/cursos/      => [ {id,nombre}, ... ]
 *      * Profesor:   GET /api/notas/catalogos/       => { cursos:[{id,nombre}], ... }
 */
export default function ComposeComunicadoFamilia({
  open,
  onOpenChange,
  defaultCurso = "",
  cursosEndpoint = "/preceptor/cursos/",
  defaultMode = "familia",
  showModeSelect = true,
}) {
  // Datos base
  const [cursos, setCursos] = useState([])
  const [cursoSel, setCursoSel] = useState(defaultCurso || "")
  const [alumnos, setAlumnos] = useState([])

  // Selecciones
  const [modo, setModo] = useState("familia") // "familia" | "alumno" | "curso_alumnos"
  const [padreSel, setPadreSel] = useState("") // id user
  const [alumnoSel, setAlumnoSel] = useState("") // id alumno

  // Form
  const [asunto, setAsunto] = useState("")
  const [mensaje, setMensaje] = useState("")

  // Loading / estados
  const [loadingCursos, setLoadingCursos] = useState(false)
  const [loadingAlumnos, setLoadingAlumnos] = useState(false)
  const [loadingPadres, setLoadingPadres] = useState(false) // para UX
  const [sending, setSending] = useState(false)
  const [errMsg, setErrMsg] = useState("")
  const [okMsg, setOkMsg] = useState("")

  // Estructura normalizada para “Familia”:
  // [{ alumnoId, alumnoNombre, padreId, padreLabel }]
  const [destinatarios, setDestinatarios] = useState([])

  // Reset suave al abrir/cerrar
  useEffect(() => {
    if (open) {
      setErrMsg("")
      setOkMsg("")
      if (defaultMode) setModo(defaultMode)
      // defaultCurso puede venir como "id" o como "label" (ej: "1A").
      // La normalización final (a id real) se hace cuando cargan los cursos.
      if (defaultCurso) setCursoSel(String(defaultCurso))
    } else {
      setModo("familia")
      setPadreSel("")
      setAlumnoSel("")
      setAsunto("")
      setMensaje("")
      setDestinatarios([])
      setAlumnos([])
    }
  }, [open, defaultCurso])

  // Auto-cierre cuando hay mensaje de éxito
  useEffect(() => {
    if (!open || !okMsg) return
    const t = setTimeout(() => {
      onOpenChange?.(false)
    }, 1500)
    return () => clearTimeout(t)
  }, [open, okMsg, onOpenChange])

  // ----- Cargar cursos asignados al preceptor -----
  useEffect(() => {
    if (!open) return
    let alive = true
    setLoadingCursos(true)
    authFetch(cursosEndpoint)
      .then((r) => r.json())
      .then((data) => {
        if (!alive) return

        // ✅ Soportar ambos formatos:
        //  - preceptor/cursos => [ {id,nombre}, ... ]
        //  - notas/catalogos  => { cursos:[{id,nombre}, ...], ... }
        const list = Array.isArray(data)
          ? data
          : Array.isArray(data?.cursos)
          ? data.cursos
          : []

        setCursos(list)

        // ✅ Normalizar cursoSel para que SIEMPRE matchee el value real del <option>.
        // Caso típico: defaultCurso llega como "1A" (label) pero el value real es un id (ej: "1").
        // Si el value no matchea, el select "parece" seleccionado pero React mantiene cursoSel vacío o inválido,
        // y no dispara la carga de alumnos hasta que el usuario cambia el curso manualmente.
        const wanted = String(cursoSel || defaultCurso || "").trim()
        let next = ""

        if (wanted) {
          // 1) Match por ID
          const byId = list.find((c) => cursoIdOf(c) === wanted)
          if (byId) next = cursoIdOf(byId)
          else {
            // 2) Match por label/nombre (case-insensitive)
            const w = wanted.toLowerCase()
            const byLabel = list.find((c) => cursoLabelOf(c).toLowerCase() === w)
            if (byLabel) next = cursoIdOf(byLabel)
          }
        }

        // 3) Si no hay coincidencias, caer al primer curso disponible
        if (!next && list.length) next = cursoIdOf(list[0])

        if (next && String(cursoSel || "") !== next) {
          setCursoSel(next)
        }
      })
      .catch(() => {
        if (alive) setErrMsg("No se pudieron cargar los cursos.")
      })
      .finally(() => alive && setLoadingCursos(false))
    return () => { alive = false }
  }, [open, defaultCurso, cursosEndpoint])

  // ----- Cargar alumnos del curso -----
  useEffect(() => {
    if (!open || !cursoSel) { setAlumnos([]); setDestinatarios([]); setAlumnoSel(""); setPadreSel(""); return }
    let alive = true
    setLoadingAlumnos(true)
    authFetch(`/alumnos/?curso=${encodeURIComponent(cursoSel)}`)
      .then((r) => r.json())
      .then((data) => {
        if (!alive) return
        const al = Array.isArray(data?.alumnos) ? data.alumnos : []
        setAlumnos(al)

        // Para modo “Familia”, pre-armamos opciones {padreId, alumnoId, labels}
        setLoadingPadres(true)
        Promise.all(
          al.map((a) => {
            try {
              const alumnoId = Number(a?.id ?? a?.alumno_id ?? a?.pk ?? 0)
              if (!alumnoId) return null
              const padre = a?.padre || null
              const padreId = padre?.id ?? null
              const alumnoNombre =
                [a?.apellido, a?.nombre].filter(Boolean).join(", ")
                || a?.nombre
                || a?.nombre_completo
                || `Alumno ${alumnoId}`
              const padreLabel = padre ? fullName(padre) : "Padre/Madre"
              return {
                alumnoId,
                alumnoNombre,
                padreId,
                padreLabel,
              }
            } catch { return null }
          })
        ).then((detalles) => {
          if (!alive) return
          setDestinatarios((detalles || []).filter(Boolean))
        }).finally(() => alive && setLoadingPadres(false))

        // autoseleccionar si hay uno solo
        if (al.length === 1) {
          const onlyId = alumnoIdOf(al[0])
          if (onlyId) setAlumnoSel(onlyId)
        }
      })
      .catch(() => {
        if (alive) {
          setErrMsg("No se pudieron cargar los alumnos del curso.")
          setAlumnos([]); setDestinatarios([])
        }
      })
      .finally(() => alive && setLoadingAlumnos(false))
    return () => { alive = false }
  }, [open, cursoSel])

  // En modo "alumno", aseguramos que haya una seleccion valida si hay alumnos cargados.
  useEffect(() => {
    if (modo !== "alumno") return
    if (!alumnos.length) {
      if (alumnoSel) setAlumnoSel("")
      return
    }
    const ids = alumnos.map(alumnoIdOf).filter(Boolean)
    if (!ids.length) {
      if (alumnoSel) setAlumnoSel("")
      return
    }
    const current = String(alumnoSel || "")
    if (!current || !ids.includes(current)) {
      setAlumnoSel(ids[0])
    }
  }, [modo, alumnos, alumnoSel])

  // ===== Opciones para selects =====
  const opcionesFamilia = useMemo(() => {
    // value: `${padreId}::${alumnoId}`
    return destinatarios.map((d) => ({
      value: `${d.padreId ?? ""}::${d.alumnoId}`,
      label: `${d.padreLabel} (Hijo/a: ${d.alumnoNombre})`,
    }))
  }, [destinatarios])

  const opcionesAlumnos = useMemo(() => {
    return alumnos
      .map((a) => {
        const id = alumnoIdOf(a)
        return {
          value: id,
          label: [a?.apellido, a?.nombre].filter(Boolean).join(", ")
            || a?.nombre
            || a?.nombre_completo
            || (id ? `Alumno ${id}` : "Alumno"),
        }
      })
      .filter((opt) => opt.value)
  }, [alumnos])

  function onChangeDestFamilia(v) {
    const [pid, aid] = String(v || "").split("::")
    setPadreSel(pid || "")
    setAlumnoSel(aid || "")
  }

  const canSend = useMemo(() => {
    // asunto y mensaje siempre requeridos
    if (!asunto.trim() || !mensaje.trim()) return false
    if (!cursoSel) return false
    if (modo === "familia") return !!(padreSel && alumnoSel)
    if (modo === "alumno") return !!alumnoSel
    if (modo === "curso_alumnos") return true
    return false
  }, [modo, asunto, mensaje, cursoSel, padreSel, alumnoSel])

  async function enviar() {
    setErrMsg(""); setOkMsg(""); setSending(true)
    try {
      if (modo === "familia") {
        // Envío idéntico al flujo anterior: a receptor_id (padre)
        const body = {
          receptor_id: Number(padreSel),
          alumno_id: Number(alumnoSel), // por trazabilidad en backend
          asunto,
          contenido: mensaje,
          tipo: "comunicado",
        }
        const res = await authFetch("/mensajes/enviar/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data?.detail || "No se pudo enviar el comunicado.")
        setOkMsg("Comunicado enviado a la familia correctamente.")
      } else if (modo === "alumno") {
        // Envío a un alumno: dejamos que la API resuelva receptor = alumno.usuario
        const res = await authFetch("/mensajes/enviar/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            alumno_id: Number(alumnoSel),
            asunto,
            contenido: mensaje,
            tipo: "mensaje",
          }),
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data?.detail || "No se pudo enviar el mensaje al alumno.")
        setOkMsg("Mensaje enviado al alumno correctamente.")
      } else {
        // Envío grupal a TODOS los alumnos del curso
        const res = await authFetch("/mensajes/enviar_grupal/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            curso: cursoSel,
            asunto,
            contenido: mensaje,
            tipo: "mensaje", // => alumno.usuario (no padres)
          }),
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data?.detail || "No se pudo enviar el mensaje grupal.")
        setOkMsg(`Mensaje enviado a ${data?.creados ?? 0} alumnos de ${cursoSel} correctamente.`)
      }
    } catch (e) {
      setErrMsg(e?.message || "Error al enviar.")
    } finally {
      setSending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => onOpenChange?.(v)}>
      <DialogContent className="sm:max-w-[720px]">
        <DialogHeader>
          <DialogTitle>
            {modo === "familia" ? "Comunicado a familias" : (modo === "alumno" ? "Mensaje a alumno" : "Mensaje a curso (alumnos)")}
          </DialogTitle>
          {errMsg && <p className="text-sm text-red-600 mt-1">{errMsg}</p>}
            {okMsg && <SuccessMessage className="mt-1">{okMsg}</SuccessMessage>}
        </DialogHeader>

        {/* Modo */}
        {showModeSelect && (
          <div className="grid gap-1.5">
            <Label htmlFor="modo">Enviar a</Label>
            <select
              id="modo"
              className="border rounded-md px-3 py-2"
              value={modo}
              onChange={(e) => setModo(e.target.value)}
              disabled={sending}
            >
              <option value="familia">Familia (padre/madre) de un alumno</option>
              <option value="alumno">Alumno individual</option>
              <option value="curso_alumnos">Todos los alumnos del curso</option>
            </select>
          </div>
        )}

        {/* Curso */}
        <div className="grid gap-1.5">
          <Label htmlFor="curso">Curso</Label>
          <select
            id="curso"
            className="border rounded-md px-3 py-2"
            value={cursoSel}
            onChange={(e) => setCursoSel(e.target.value)}
            disabled={loadingCursos || sending}
          >
            {!cursos.length && <option value="">{loadingCursos ? "Cargando…" : "Sin cursos"}</option>}
            {cursos.map((c) => {
              const id = pick(c, "id", "value", "curso") ?? c
              const label = pick(c, "nombre", "label") ?? String(id)
              return (
                <option key={id} value={id}>{label}</option>
              )
            })}
          </select>
        </div>

        {/* Destinatario según modo */}
        {modo === "familia" && (
          <div className="grid gap-1.5">
            <Label htmlFor="dest">Destinatario (Padre/Madre/Tutor)</Label>
            <select
              id="dest"
              className="border rounded-md px-3 py-2"
              value={padreSel && alumnoSel ? `${padreSel}::${alumnoSel}` : ""}
              onChange={(e) => onChangeDestFamilia(e.target.value)}
              disabled={loadingAlumnos || !alumnos.length || sending}
            >
              {!alumnos.length && <option value="">{cursoSel ? "Sin alumnos" : "Elegí un curso…"}</option>}
              {opcionesFamilia.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            {loadingPadres && <p className="text-xs text-gray-500">Cargando familias…</p>}
          </div>
        )}

        {modo === "alumno" && (
          <div className="grid gap-1.5">
            <Label htmlFor="alumno">Alumno</Label>
            <select
              id="alumno"
              className="border rounded-md px-3 py-2"
              value={alumnoSel}
              onChange={(e) => setAlumnoSel(e.target.value)}
              disabled={loadingAlumnos || !alumnos.length || sending}
            >
              {!alumnos.length && <option value="">{cursoSel ? "Sin alumnos" : "Elegí un curso…"}</option>}
              {opcionesAlumnos.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        )}

        {/* Asunto + Mensaje */}
        <div className="grid gap-1.5">
          <Label htmlFor="asunto">Asunto</Label>
          <Input
            id="asunto"
            value={asunto}
            onChange={(e) => setAsunto(e.target.value)}
            disabled={sending}
            maxLength={100}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="msg">Mensaje</Label>
          <Textarea
            id="msg"
            rows={6}
            value={mensaje}
            onChange={(e) => setMensaje(e.target.value)}
            disabled={sending}
          />
        </div>

        <DialogFooter className="mt-4">
          <Button onClick={() => onOpenChange?.(false)} disabled={sending}>
            Cancelar
          </Button>
          <Button onClick={enviar} disabled={sending || !canSend}>
            {sending ? "Enviando…" : (modo === "curso_alumnos" ? "Enviar al curso" : "Enviar")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

