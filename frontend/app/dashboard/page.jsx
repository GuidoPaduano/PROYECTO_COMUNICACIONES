"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../_lib/auth"
import { INBOX_EVENT } from "../_lib/inbox"

import {
  Calendar,
  Plus,
  CheckSquare,
  User,
  BookOpen,
  Users,
  ClipboardList,
  Inbox,
  Gavel,
  Pencil,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import SuccessMessage from "@/components/ui/success-message"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

import ComposeComunicadoFamilia from "../mensajes/_compose-comunicado-familia"

const ROLES = ["Profesores", "Alumnos", "Padres", "Preceptores"]
const PREVIEW_KEY = "preview_role"
const LAST_CURSO_KEY = "ultimo_curso_seleccionado"
const LAST_HIJO_KEY = "mis_hijos_last_alumno"

function hoyISO() {
  const d = new Date()
  const z = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`
}

function addDaysISO(baseISO, days) {
  const d = new Date(`${baseISO}T00:00:00`)
  d.setDate(d.getDate() + days)
  const z = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`
}

function formatFechaCorta(raw) {
  if (!raw) return ""
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return String(raw)
  return d.toLocaleDateString("es-AR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  })
}

function parseEventosPayload(raw) {
  const list = Array.isArray(raw)
    ? raw
    : raw?.eventos || raw?.results || []
  const parsed = Array.isArray(list)
    ? list
        .map((e) => ({
          title: e?.title ?? e?.titulo ?? "",
          date: e?.start ?? e?.fecha ?? e?.date ?? "",
          id: String(e?.id ?? ""),
        }))
        .filter((e) => e.title && e.date)
    : []
  parsed.sort((a, b) => new Date(a.date) - new Date(b.date))
  return parsed
}

function getStoredCurso() {
  try {
    return localStorage.getItem(LAST_CURSO_KEY) || ""
  } catch {
    return ""
  }
}

function setStoredCurso(value) {
  try {
    if (value) localStorage.setItem(LAST_CURSO_KEY, value)
  } catch {}
}

function getStoredHijo() {
  try {
    return localStorage.getItem(LAST_HIJO_KEY) || ""
  } catch {
    return ""
  }
}

function setStoredHijo(value) {
  try {
    if (value) localStorage.setItem(LAST_HIJO_KEY, value)
  } catch {}
}

function hijoRouteId(h) {
  return h?.id_alumno ?? h?.alumno_id ?? h?.legajo ?? h?.id ?? h?.pk ?? null
}

function hijoDisplayName(h) {
  const nombre = String(h?.nombre || "").trim()
  const apellido = String(h?.apellido || "").trim()
  const full = [apellido, nombre].filter(Boolean).join(" ")
  if (full) return full
  return nombre || String(h?.id_alumno ?? h?.alumno_id ?? h?.legajo ?? "").trim()
}

function asistenciaTipoFromAny(a) {
  const candidates = [
    a?.tipo_asistencia,
    a?.tipo,
    a?.categoria,
    a?.materia,
    a?.asignatura,
    a?.area,
    a?.seccion,
    a?.clase,
  ]
  for (const c of candidates) {
    const t = String(c ?? "").trim()
    if (t) return t
  }
  return ""
}

function normalizeAsistenciaTipo(raw) {
  const s = String(raw ?? "").trim().toLowerCase()
  if (!s) return ""
  if (s === "clases" || s === "informatica" || s === "catequesis") return s
  if (s.includes("info")) return "informatica"
  if (s.includes("cateq")) return "catequesis"
  if (s.includes("clase")) return "clases"
  return s
}

function esNoLeido(m, myId) {
  const hasLeido = Object.prototype.hasOwnProperty.call(m, "leido")
  const hasLeidoEn = Object.prototype.hasOwnProperty.call(m, "leido_en")
  if (!hasLeido && !hasLeidoEn) return false

  const isUnread =
    (hasLeido && m.leido === false) ||
    (hasLeidoEn && (m.leido_en === null || m.leido_en === undefined))

  if (m?.receptor_id && myId) return isUnread && m.receptor_id === myId
  if (m?.receptor && myId) return isUnread && m.receptor === myId
  return isUnread
}

function estadoTexto(v) {
  if (v === true) return "Presente"
  if (v === false) return "Ausente"
  const s = String(v ?? "").trim().toLowerCase()
  if (!s) return ""
  if (["tarde", "llego tarde", "llegó tarde", "retardo", "late", "l"].includes(s)) {
    return "Tarde"
  }
  if (["presente", "p", "si", "sí", "1", "true", "y", "yes", "on", "ok"].includes(s)) {
    return "Presente"
  }
  if (["ausente", "a", "no", "0", "false", "f", "n", "inasistente"].includes(s)) {
    return "Ausente"
  }
  return s
}

function asistenciaEstadoFromAny(a) {
  if (!a || typeof a !== "object") return a
  const raw = a.estado ?? a.status ?? a.estado_asistencia
  if (raw != null && String(raw).trim() !== "") return raw
  const tarde = a.tarde ?? a.llego_tarde ?? a.llegó_tarde ?? a.is_tarde
  const pres = a.presente ?? a.asistio ?? a.asistió ?? a.pres
  if (a.inasistente === true) return "ausente"
  if (a.inasistente === false) return "presente"
  if (pres === false) return "ausente"
  if (tarde === true) return "tarde"
  if (pres === true) return "presente"
  return a.asistencia ?? pres
}

function isJustificadaFromAny(a) {
  if (!a) return false
  const v =
    a.justificada ??
    a.justificado ??
    a.justify ??
    a.is_justificada ??
    a.isJustificada ??
    false
  return v === true || v === 1 || v === "1" || v === "true"
}

/* ======================== Helpers “Mis notas / sanciones” ======================== */

function alumnoRouteIdFromMe(me) {
  if (!me || typeof me !== "object") return null

  const legajoPaths = [
    ["alumno", "id_alumno"],
    ["alumno_id"],
    ["id_alumno"],
    ["user", "alumno", "id_alumno"],
    ["user", "alumno_id"],
    ["user", "id_alumno"],
    ["profile", "alumno_id"],
    ["user", "profile", "alumno_id"],
  ]
  for (const path of legajoPaths) {
    let cur = me
    for (const k of path) cur = cur?.[k]
    if (cur != null && cur !== "") return cur
  }

  const pkPaths = [
    ["alumno", "id"],
    ["alumno", "pk"],
    ["user", "alumno", "id"],
    ["user", "alumno", "pk"],
  ]
  for (const path of pkPaths) {
    let cur = me
    for (const k of path) cur = cur?.[k]
    if (cur != null && cur !== "") return cur
  }

  return null
}

async function fetchAlumnoIdSelfFallback(previewRole) {
  const candidates = ["/perfil_api/"]

  for (const url of candidates) {
    try {
      const res = await authFetch(url.endsWith("/") ? url : `${url}/`, {
        headers: previewRole ? { "X-Preview-Role": previewRole } : undefined,
      })
      if (!res.ok) continue
      const data = await res.json().catch(() => ({}))
      const a = data?.alumno || data

      const legajo =
        a?.id_alumno ??
        a?.alumno_id ??
        a?.user?.alumno_id ??
        a?.user?.id_alumno ??
        a?.profile?.alumno_id
      if (legajo) return legajo

      const pk =
        a?.id ??
        a?.pk ??
        a?.alumno?.id ??
        a?.alumno?.pk ??
        a?.user?.alumno?.id ??
        a?.user?.alumno?.pk
      if (pk != null) return pk
    } catch {}
  }
  return null
}

async function resolveAlumnoRouteId(me, previewRole) {
  const direct = alumnoRouteIdFromMe(me)
  if (direct != null) return direct
  return await fetchAlumnoIdSelfFallback(previewRole)
}

export default function DashboardPage() {
  useAuthGuard()

  const [me, setMe] = useState(null)
  const [error, setError] = useState("")
  const [previewRole, setPreviewRole] = useState("")
  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || ""),
    [me]
  )

  const pfetch = (url, options = {}) => {
    const headers = { ...(options?.headers || {}) }
    if (previewRole) headers["X-Preview-Role"] = previewRole
    return authFetch(url, { ...options, headers })
  }

  const [unreadCount, setUnreadCount] = useState(0)

  useEffect(() => {
    let alive = true
    let timer = null

    const loadUnread = async () => {
      try {
        let res = await pfetch("/mensajes/unread_count/")
        if (!res.ok) res = await pfetch("/api/mensajes/unread_count/")
        if (!res.ok) return
        const j = await res.json().catch(() => ({}))
        if (alive && typeof j?.count === "number") setUnreadCount(j.count)
      } catch {}
    }

    loadUnread()
    timer = setInterval(loadUnread, 60000)

    const handler = () => loadUnread()
    if (typeof window !== "undefined") window.addEventListener(INBOX_EVENT, handler)

    return () => {
      alive = false
      if (timer) clearInterval(timer)
      if (typeof window !== "undefined") window.removeEventListener(INBOX_EVENT, handler)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewRole])

  const [openInd, setOpenInd] = useState(false)
  const [openGrp, setOpenGrp] = useState(false)
  const [openSan, setOpenSan] = useState(false)
  const [openComFam, setOpenComFam] = useState(false)

  // ✅ NUEVO: modal selector “Enviar mensajes” (profesor)
  const [openSendPicker, setOpenSendPicker] = useState(false)

  const [cursos, setCursos] = useState([])

  const [cursoInd, setCursoInd] = useState("")
  const [alumnosInd, setAlumnosInd] = useState([])
  const [alumnoInd, setAlumnoInd] = useState("")
  const [asuntoInd, setAsuntoInd] = useState("")
  const [cuerpoInd, setCuerpoInd] = useState("")
  const [loadingInd, setLoadingInd] = useState(false)
  const [msgIndErr, setMsgIndErr] = useState("")
  const [msgIndOk, setMsgIndOk] = useState("")

  const [cursoGrp, setCursoGrp] = useState("")
  const [asuntoGrp, setAsuntoGrp] = useState("")
  const [cuerpoGrp, setCuerpoGrp] = useState("")
  const [loadingGrp, setLoadingGrp] = useState(false)
  const [msgGrpErr, setMsgGrpErr] = useState("")
  const [msgGrpOk, setMsgGrpOk] = useState("")

  const [cursoSan, setCursoSan] = useState("")
  const [alumnosSan, setAlumnosSan] = useState([])
  const [alumnoSan, setAlumnoSan] = useState("")
  const [fechaSan, setFechaSan] = useState(hoyISO())
const [mensajeSan, setMensajeSan] = useState("")
  const [loadingSan, setLoadingSan] = useState(false)
  const [msgSanErr, setMsgSanErr] = useState("")
  const [msgSanOk, setMsgSanOk] = useState("")

  const [alumnoIdSelf, setAlumnoIdSelf] = useState(null)
  const [loadingAlumnoId, setLoadingAlumnoId] = useState(false)

  const [alumnoCurso, setAlumnoCurso] = useState("")
  const [alumnoCursoLoaded, setAlumnoCursoLoaded] = useState(false)
  const [eventosProximos, setEventosProximos] = useState([])
  const [eventosLoading, setEventosLoading] = useState(false)
  const [inasistenciasCount, setInasistenciasCount] = useState(0)
  const [inasistenciasLoading, setInasistenciasLoading] = useState(false)
  const [profesorCursoSel, setProfesorCursoSel] = useState("")
  const [profesorCursoLoaded, setProfesorCursoLoaded] = useState(false)
  const [eventosProfesor, setEventosProfesor] = useState([])
  const [eventosProfesorLoading, setEventosProfesorLoading] = useState(false)
  const [padreKidId, setPadreKidId] = useState("")
  const [padreKidLabel, setPadreKidLabel] = useState("")
  const [padreHijosCount, setPadreHijosCount] = useState(0)
  const [padreHijosLoaded, setPadreHijosLoaded] = useState(false)
  const [eventosPadre, setEventosPadre] = useState([])
  const [eventosPadreLoading, setEventosPadreLoading] = useState(false)
  const [mensajesHome, setMensajesHome] = useState([])
  const [mensajesHomeLoading, setMensajesHomeLoading] = useState(false)

  const [openAlumnoMsg, setOpenAlumnoMsg] = useState(false)
  const [loadingAlumnoMsg, setLoadingAlumnoMsg] = useState(false)
  const [alumnoMsgErr, setAlumnoMsgErr] = useState("")
  const [alumnoMsgOk, setAlumnoMsgOk] = useState("")
  const [destSel, setDestSel] = useState("")
  const [asuntoAlu, setAsuntoAlu] = useState("")
  const [contenidoAlu, setContenidoAlu] = useState("")
  const [destinatariosProf, setDestinatariosProf] = useState([])
  const [destinatariosPrec, setDestinatariosPrec] = useState([])

  const getCursoId = (c) => (c?.id ?? c?.value ?? c)
  const getCursoNombre = (c) => (c?.nombre ?? c?.label ?? String(getCursoId(c)))

  useEffect(() => {
    try {
      if (typeof window !== "undefined") {
        const saved = localStorage.getItem(PREVIEW_KEY) || ""
        setPreviewRole(saved)
      }
    } catch {}
  }, [])

  useEffect(() => {
    const openIndHandler = () => setOpenInd(true)
    const openGrpHandler = () => setOpenGrp(true)
    const openSanHandler = () => setOpenSan(true)
    window.addEventListener("open-individual", openIndHandler)
    window.addEventListener("open-grupal", openGrpHandler)
    window.addEventListener("open-sancion", openSanHandler)
    return () => {
      window.removeEventListener("open-individual", openIndHandler)
      window.removeEventListener("open-grupal", openGrpHandler)
      window.removeEventListener("open-sancion", openSanHandler)
    }
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        const res = await pfetch("/auth/whoami/")
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          setError(data?.detail || `Error ${res.status}`)
          return
        }
        setMe(data)
      } catch {
        setError("No se pudo obtener el perfil")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewRole])

  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoadingAlumnoId(true)
      try {
        const id = await resolveAlumnoRouteId(me || {}, previewRole)
        if (alive) setAlumnoIdSelf(id)
      } finally {
        if (alive) setLoadingAlumnoId(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [me, previewRole])

  useEffect(() => {
    ;(async () => {
      try {
        const res = await pfetch("/notas/catalogos/")
        const j = await res.json().catch(() => ({}))
        setCursos(j?.cursos || [])
      } catch {}
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewRole])

  useEffect(() => {
    if (!cursoInd) {
      setAlumnosInd([])
      setAlumnoInd("")
      return
    }
    ;(async () => {
      try {
        const res = await pfetch(`/alumnos/?curso=${encodeURIComponent(cursoInd)}`)
        const j = await res.json().catch(() => ({}))
        setAlumnosInd(j?.alumnos || [])
      } catch {
        setMsgIndErr("No se pudieron cargar los alumnos.")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoInd, previewRole])

  useEffect(() => {
    if (!cursoSan) {
      setAlumnosSan([])
      setAlumnoSan("")
      return
    }
    ;(async () => {
      try {
        const res = await pfetch(`/alumnos/?curso=${encodeURIComponent(cursoSan)}`)
        const j = await res.json().catch(() => ({}))
        setAlumnosSan(j?.alumnos || [])
      } catch {
        setMsgSanErr("No se pudieron cargar los alumnos.")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoSan, previewRole])

  useEffect(() => {
    try {
      if (typeof window !== "undefined") {
        if (previewRole) localStorage.setItem(PREVIEW_KEY, previewRole)
        else localStorage.removeItem(PREVIEW_KEY)
      }
    } catch {}
  }, [previewRole])

  async function submitIndividual(ev) {
      ev.preventDefault()
      setMsgIndErr("")
      setMsgIndOk("")
      setLoadingInd(true)
      try {
        const selectedAlumno =
          alumnosInd.find((a) => {
            const key =
              a?.id ?? a?.pk ?? a?.id_alumno ?? a?.codigo ?? a?.legajo
            return String(key ?? "") === String(alumnoInd)
          }) || {}
        const alumnoPk = selectedAlumno?.id ?? selectedAlumno?.pk
        const alumnoCode =
          selectedAlumno?.id_alumno ??
          selectedAlumno?.codigo ??
          selectedAlumno?.legajo ??
          alumnoInd
        const alumnoIdNum =
          alumnoPk != null && !Number.isNaN(Number(alumnoPk))
            ? Number(alumnoPk)
            : null

        const res = await pfetch("/mensajes/enviar/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...(alumnoIdNum != null ? { alumno_id: alumnoIdNum } : {}),
            ...(alumnoCode ? { id_alumno: String(alumnoCode) } : {}),
            asunto: asuntoInd.trim(),
            contenido: cuerpoInd.trim(),
          }),
        })
        const j = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      setMsgIndOk("✅ Mensaje enviado.")
      setTimeout(() => {
        setOpenInd(false)
        setCursoInd("")
        setAlumnoInd("")
        setAlumnosInd([])
        setAsuntoInd("")
        setCuerpoInd("")
        setMsgIndOk("")
      }, 600)
    } catch (e) {
      setMsgIndErr(e?.message || "No se pudo enviar.")
    } finally {
      setLoadingInd(false)
    }
  }

  async function submitGrupal(ev) {
    ev.preventDefault()
    setMsgGrpErr("")
    setMsgGrpOk("")
    setLoadingGrp(true)
    try {
      const res = await pfetch("/mensajes/enviar_grupal/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          curso: cursoGrp,
          asunto: asuntoGrp.trim(),
          contenido: cuerpoGrp.trim(),
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      setMsgGrpOk(
        `✅ Enviado a ${j?.creados ?? "varios"} destinatarios${
          j?.sin_receptor ? `, ${j.sin_receptor} sin receptor` : ""
        }.`
      )
      setTimeout(() => {
        setOpenGrp(false)
        setCursoGrp("")
        setAsuntoGrp("")
        setCuerpoGrp("")
        setMsgGrpOk("")
      }, 800)
    } catch (e) {
      setMsgGrpErr(e?.message || "No se pudo enviar.")
    } finally {
      setLoadingGrp(false)
    }
  }

  async function submitSancion(ev) {
    ev.preventDefault()
    setMsgSanErr("")
    setMsgSanOk("")
    setLoadingSan(true)
    try {
      const res = await pfetch("/sanciones/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          alumno: Number(alumnoSan),
          fecha: fechaSan,
mensaje: mensajeSan.trim(),
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      // ✅ UX: si se registró OK, cerramos el modal automáticamente.
      // De paso limpiamos campos para la próxima vez.
      setMsgSanOk("✅ Sanción registrada.")
      setTimeout(() => {
        setOpenSan(false)
        setCursoSan("")
        setAlumnoSan("")
        setAlumnosSan([])
        setFechaSan(hoyISO())
setMensajeSan("")
        setMsgSanOk("")
        setMsgSanErr("")
      }, 250)
    } catch (e) {
      setMsgSanErr(e?.message || "No se pudo guardar la sanción.")
    } finally {
      setLoadingSan(false)
    }
  }

  const cursoSugeridoAlumno = me?.alumno?.curso || me?.curso || me?.user?.alumno?.curso || ""

  useEffect(() => {
    if (!openAlumnoMsg) return
    let alive = true
    ;(async () => {
      setLoadingAlumnoMsg(true)
      setAlumnoMsgErr("")
      try {
        const base = "/api/mensajes/destinatarios_docentes/"
        const withCurso = cursoSugeridoAlumno
          ? `${base}?curso=${encodeURIComponent(cursoSugeridoAlumno)}`
          : base
        const fallbacks = [withCurso, base, "/mensajes/destinatarios_docentes/"]
        let data = null
        for (const url of fallbacks) {
          try {
            const r = await pfetch(url)
            if (!r.ok) continue
            data = await r.json().catch(() => ({}))
            break
          } catch {}
        }

        let arr = []
        if (Array.isArray(data?.profesores) || Array.isArray(data?.preceptores)) {
          setDestinatariosProf(Array.isArray(data?.profesores) ? data.profesores : [])
          setDestinatariosPrec(Array.isArray(data?.preceptores) ? data.preceptores : [])
        } else {
          if (Array.isArray(data)) arr = data
          else if (Array.isArray(data?.results)) arr = data.results
          else arr = []
          const norm = (v) => String(v ?? "").toLowerCase()
          setDestinatariosProf((arr || []).filter((d) => norm(d?.grupo || d?.rol || d?.role).includes("prof")))
          setDestinatariosPrec((arr || []).filter((d) => norm(d?.grupo || d?.rol || d?.role).includes("prec")))
        }

        if (!alive) return
      } catch (e) {
        if (!alive) return
        setAlumnoMsgErr(e?.message || "No se pudieron cargar los destinatarios.")
      } finally {
        if (alive) setLoadingAlumnoMsg(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [openAlumnoMsg, cursoSugeridoAlumno, previewRole])

  async function enviarMensajeAlumno() {
    if (!destSel) return setAlumnoMsgErr("Elegí un destinatario.")
    if (!asuntoAlu.trim()) return setAlumnoMsgErr("Completá el asunto.")
    if (!contenidoAlu.trim()) return setAlumnoMsgErr("Escribí el mensaje.")
    setAlumnoMsgErr("")
    setAlumnoMsgOk("")

    const payload = {
      receptor_id: Number(destSel),
      asunto: asuntoAlu.trim(),
      contenido: contenidoAlu.trim(),
      ...(cursoSugeridoAlumno ? { curso: cursoSugeridoAlumno } : {}),
    }

    const tries = [
      "/api/mensajes/alumno/enviar/",
      "/mensajes/alumno/enviar/",
      "/api/mensajes/enviar/",
      "/mensajes/enviar/",
    ]

    let sent = false
    let lastErr = ""
    for (const url of tries) {
      try {
        const r = await pfetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        })
        if (r.ok) {
          sent = true
          break
        }
        lastErr = `HTTP ${r.status}`
      } catch (e) {
        lastErr = e?.message || "Error de red"
      }
    }

    if (sent) {
      setAlumnoMsgOk("✅ Mensaje enviado.")
      try {
        window.dispatchEvent(new Event(INBOX_EVENT))
      } catch {}
      setTimeout(() => {
        setOpenAlumnoMsg(false)
        setDestSel("")
        setAsuntoAlu("")
        setContenidoAlu("")
        setAlumnoMsgOk("")
      }, 700)
    } else {
      setAlumnoMsgErr(`No se pudo enviar el mensaje. ${lastErr}`)
    }
  }

  // ✅ helpers: abrir modales desde el selector sin conflictos
  const abrirIndividualDesdePicker = () => {
    setOpenSendPicker(false)
    setTimeout(() => setOpenInd(true), 0)
  }
  const abrirGrupalDesdePicker = () => {
    setOpenSendPicker(false)
    setTimeout(() => setOpenGrp(true), 0)
  }
  const abrirFamiliaDesdePicker = () => {
    setOpenSendPicker(false)
    setTimeout(() => setOpenComFam(true), 0)
  }

  useEffect(() => {
    const handler = () => setOpenSendPicker(true)
    if (typeof window !== "undefined") {
      window.addEventListener("open-send-picker", handler)
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("open-send-picker", handler)
      }
    }
  }, [])

  const baseGroups = Array.isArray(me?.groups) ? me.groups : []
  const isSuper = !!me?.is_superuser
  const myId = me?.id ?? me?.user?.id ?? null

  const effectiveGroups = isSuper && previewRole ? [previewRole] : baseGroups
  const showAll = isSuper && !previewRole

  const showProfesor = showAll || effectiveGroups.includes("Profesores")
  const showAlumno = showAll || effectiveGroups.includes("Alumnos")
  const showPadre = showAll || effectiveGroups.includes("Padres")
  const showPreceptor = showAll || effectiveGroups.includes("Preceptores")
  const showDocenteCursos = showProfesor || showPreceptor
  const isAlumnoOnly = showAlumno && !showProfesor && !showPadre && !showPreceptor
  const showLegacyDashboardCards = false

  useEffect(() => {
    if (!showDocenteCursos) return
    let alive = true
    setProfesorCursoLoaded(false)
    const stored = typeof window !== "undefined" ? getStoredCurso() : ""
    if (alive && stored) setProfesorCursoSel(stored)
    setProfesorCursoLoaded(true)
    return () => {
      alive = false
    }
  }, [showDocenteCursos, previewRole])

  useEffect(() => {
    if (!showDocenteCursos) return
    if (profesorCursoSel) return
    const first = Array.isArray(cursos) && cursos.length > 0 ? getCursoId(cursos[0]) : ""
    if (first) setProfesorCursoSel(String(first))
  }, [showDocenteCursos, profesorCursoSel, cursos])

  useEffect(() => {
    if (!showDocenteCursos) return
    if (!profesorCursoSel) return
    setStoredCurso(String(profesorCursoSel))
  }, [showDocenteCursos, profesorCursoSel])

  useEffect(() => {
    if (!showDocenteCursos) return
    if (!profesorCursoSel) {
      setEventosProfesor([])
      return
    }
    let alive = true
    ;(async () => {
      setEventosProfesorLoading(true)
      try {
        const desde = hoyISO()
        const hasta = addDaysISO(desde, 5)
        const res = await pfetch(
          `/eventos/?curso=${encodeURIComponent(profesorCursoSel)}&desde=${desde}&hasta=${hasta}`
        )
        if (!res.ok) {
          if (alive) setEventosProfesor([])
          return
        }
        const raw = await res.json().catch(() => ({}))
        if (alive) setEventosProfesor(parseEventosPayload(raw))
      } catch {
        if (alive) setEventosProfesor([])
      } finally {
        if (alive) setEventosProfesorLoading(false)
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showDocenteCursos, profesorCursoSel, previewRole])

  useEffect(() => {
    if (!showAlumno) return
    let alive = true
    ;(async () => {
      setAlumnoCursoLoaded(false)
      try {
        const res = await pfetch("/mi-curso/")
        if (res.ok) {
          const data = await res.json().catch(() => ({}))
          const curso = String(data?.curso ?? "").trim()
          if (alive) setAlumnoCurso(curso)
        }
      } catch {
      } finally {
        if (alive) setAlumnoCursoLoaded(true)
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showAlumno, previewRole])

  useEffect(() => {
    if (!showPadre) return
    let alive = true

    ;(async () => {
      setPadreHijosLoaded(false)
      try {
        const tries = ["/padres/mis-hijos/", "/api/padres/mis-hijos/"]
        let data = null
        for (const url of tries) {
          try {
            const r = await pfetch(url)
            if (!r.ok) continue
            data = await r.json().catch(() => ({}))
            break
          } catch {}
        }

        const arr = Array.isArray(data)
          ? data
          : data?.results || data?.hijos || []
        const hijos = Array.isArray(arr) ? arr : []
        const ids = hijos
          .map((h) => hijoRouteId(h))
          .filter((x) => x != null && String(x) !== "")
          .map((x) => String(x))

        if (!alive) return

        if (ids.length === 0) {
          setPadreKidId("")
          setPadreKidLabel("")
          setPadreHijosCount(0)
          return
        }

        const stored = getStoredHijo()
        const chosen = stored && ids.includes(stored) ? stored : ids[0]
        const chosenKid = hijos.find((h) => String(hijoRouteId(h)) === String(chosen)) || null
        setPadreKidId(chosen)
        setPadreKidLabel(chosenKid ? hijoDisplayName(chosenKid) : "")
        setPadreHijosCount(ids.length)
        setStoredHijo(chosen)
      } finally {
        if (alive) setPadreHijosLoaded(true)
      }
    })()

    return () => {
      alive = false
    }
  }, [showPadre, previewRole])

  useEffect(() => {
    if (!showPadre) return
    if (!padreKidId) {
      setEventosPadre([])
      return
    }
    let alive = true
    ;(async () => {
      setEventosPadreLoading(true)
      try {
        const desde = hoyISO()
        const hasta = addDaysISO(desde, 5)
        const res = await pfetch(
          `/padres/hijos/${encodeURIComponent(padreKidId)}/eventos/?desde=${desde}&hasta=${hasta}`
        )
        if (!res.ok) {
          if (alive) setEventosPadre([])
          return
        }
        const raw = await res.json().catch(() => ({}))
        if (alive) setEventosPadre(parseEventosPayload(raw))
      } catch {
        if (alive) setEventosPadre([])
      } finally {
        if (alive) setEventosPadreLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [showPadre, padreKidId, previewRole])

  useEffect(() => {
    if (!showPadre && !showAlumno && !showPreceptor && !showProfesor) return
    let alive = true
    ;(async () => {
      setMensajesHomeLoading(true)
      try {
        const candidates = ["/mensajes/recibidos/", "/mensajes/listar/"]
        let list = null
        for (const url of candidates) {
          try {
            const r = await pfetch(url)
            if (!r.ok) continue
            const data = await r.json().catch(() => ({}))
            const arr = Array.isArray(data)
              ? data
              : Array.isArray(data?.results)
              ? data.results
              : Array.isArray(data?.mensajes)
              ? data.mensajes
              : null
            if (arr) {
              list = arr
              break
            }
          } catch {}
        }

        const normalized = Array.isArray(list) ? list : []
        normalized.sort((a, b) => {
          const da = new Date(a?.fecha || a?.fecha_envio || 0).getTime()
          const db = new Date(b?.fecha || b?.fecha_envio || 0).getTime()
          return db - da
        })

        if (alive) setMensajesHome(normalized.slice(0, 5))
      } catch {
        if (alive) setMensajesHome([])
      } finally {
        if (alive) setMensajesHomeLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [showPadre, showAlumno, showPreceptor, showProfesor, previewRole])

  useEffect(() => {
    if (!isAlumnoOnly) return
    if (!alumnoCurso) return
    let alive = true
    ;(async () => {
      setEventosLoading(true)
      try {
        const desde = hoyISO()
        const hasta = addDaysISO(desde, 5)
        const res = await pfetch(
          `/eventos/?curso=${encodeURIComponent(alumnoCurso)}&desde=${desde}&hasta=${hasta}`
        )
        if (!res.ok) {
          if (alive) setEventosProximos([])
          return
        }
        const raw = await res.json().catch(() => ({}))
        if (alive) setEventosProximos(parseEventosPayload(raw))
      } catch {
        if (alive) setEventosProximos([])
      } finally {
        if (alive) setEventosLoading(false)
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAlumnoOnly, alumnoCurso, previewRole])

  useEffect(() => {
    if (!isAlumnoOnly) return
    if (!alumnoIdSelf) return
    let alive = true
    ;(async () => {
      setInasistenciasLoading(true)
      try {
        const encoded = encodeURIComponent(alumnoIdSelf)
        const isNumericId = /^\d+$/.test(String(alumnoIdSelf || ""))
        const tries = [
          `/asistencias/?alumno=${encoded}`,
          `/api/asistencias/?alumno=${encoded}`,
          `/asistencias/alumno/${encoded}/`,
          ...(isNumericId
            ? []
            : [
                `/asistencias/?id_alumno=${encoded}`,
                `/api/asistencias/?id_alumno=${encoded}`,
                `/asistencias/alumno_codigo/${encoded}/`,
              ]),
        ]
        let asistencias = []
        for (const url of tries) {
          const res = await pfetch(url)
          if (!res.ok) continue
          const data = await res.json().catch(() => ({}))
          const list = Array.isArray(data)
            ? data
            : data?.asistencias || data?.results || []
          if (Array.isArray(list)) {
            asistencias = list
            break
          }
        }

        let total = 0
        for (const a of asistencias) {
          const tipo = normalizeAsistenciaTipo(asistenciaTipoFromAny(a)) || "clases"
          if (tipo !== "clases") continue
          if (isJustificadaFromAny(a)) continue
          const estado = estadoTexto(asistenciaEstadoFromAny(a))
          if (estado === "Ausente") total += 1
          else if (estado === "Tarde") total += 0.5
        }

        if (alive) setInasistenciasCount(total)
      } catch {
        if (alive) setInasistenciasCount(0)
      } finally {
        if (alive) setInasistenciasLoading(false)
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAlumnoOnly, alumnoIdSelf, previewRole])

  if (error) {
    return (
      <div className="surface-card surface-card-pad text-red-600">{error}</div>
    )
  }

  if (!me) {
    return (
      <div className="surface-card surface-card-pad">Cargando...</div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-8">
        {isAlumnoOnly ? (
          <AlumnoInicio
            eventos={eventosProximos}
            eventosLoading={eventosLoading || !alumnoCursoLoaded}
            inasistenciasCount={inasistenciasCount}
            inasistenciasLoading={inasistenciasLoading}
            mensajes={mensajesHome}
            mensajesLoading={mensajesHomeLoading}
            myId={myId}
          />
        ) : showProfesor ? (
            <ProfesorInicio
              mensajes={mensajesHome}
              mensajesLoading={mensajesHomeLoading}
              myId={myId}
            />
        ) : showPreceptor ? (
            <PreceptorInicio
              eventos={eventosProfesor}
              eventosLoading={eventosProfesorLoading || !profesorCursoLoaded}
              hasCurso={!!profesorCursoSel}
              mensajes={mensajesHome}
              mensajesLoading={mensajesHomeLoading}
              myId={myId}
            />
        ) : showPadre ? (
            <PadreInicio
              eventos={eventosPadre}
              eventosLoading={eventosPadreLoading || !padreHijosLoaded}
              hasHijo={!!padreKidId}
              hijoLabel={padreKidLabel}
              showHijoLabel={padreHijosCount > 1}
              mensajes={mensajesHome}
              mensajesLoading={mensajesHomeLoading}
              myId={myId}
            />
        ) : null}
      </div>

      {/* ✅ NUEVO: Selector “Enviar mensajes” (profesor) */}
      <Dialog open={openSendPicker} onOpenChange={setOpenSendPicker}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Enviar mensajes</DialogTitle>
            <DialogDescription>
              Elegí si querés enviar a un alumno en particular o a un curso entero.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <TileButton
              title="A un alumno"
              desc="Mensaje individual a un alumno"
              icon={<User className="h-4 w-4 text-blue-600" />}
              onClick={abrirIndividualDesdePicker}
            />
            <TileButton
              title="A un curso"
              desc="Mensaje grupal a un curso"
              icon={<Users className="h-4 w-4 text-blue-600" />}
              onClick={abrirGrupalDesdePicker}
            />
            <TileButton
              title="A la familia"
              desc="Comunicado para padres o tutores"
              icon={<Users className="h-4 w-4 text-blue-600" />}
              onClick={abrirFamiliaDesdePicker}
            />
          </div>

          <div className="flex items-center justify-end pt-2">
            <Button onClick={() => setOpenSendPicker(false)}>
              Cerrar
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* === Modales (profesor) === */}
      <Dialog open={openInd} onOpenChange={setOpenInd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enviar mensaje individual</DialogTitle>
            <DialogDescription>
              Elegí curso y alumno; escribí el asunto y el cuerpo.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={submitIndividual} className="space-y-4">
            {msgIndErr && <div className="text-red-600 text-sm">{msgIndErr}</div>}
            {msgIndOk && <SuccessMessage className="mt-1">{msgIndOk}</SuccessMessage>}

            <div>
              <Label htmlFor="cursoInd">Curso</Label>
              <select
                id="cursoInd"
                className="w-full border p-2 rounded-md"
                value={cursoInd}
                onChange={(e) => setCursoInd(e.target.value)}
                required
              >
                <option value="">Seleccioná un curso…</option>
                {cursos.map((c) => (
                  <option key={getCursoId(c)} value={getCursoId(c)}>
                    {getCursoNombre(c)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="alumnoInd">Alumno</Label>
              <select
                id="alumnoInd"
                className="w-full border p-2 rounded-md"
                value={alumnoInd}
                onChange={(e) => setAlumnoInd(e.target.value)}
                required
                disabled={!cursoInd}
              >
                <option value="">
                  {cursoInd ? "Seleccioná un alumno…" : "Elegí curso primero"}
                </option>
                  {alumnosInd.map((a) => {
                    const key =
                      a?.id ?? a?.pk ?? a?.id_alumno ?? a?.codigo ?? a?.legajo
                    const label =
                      a?.nombre ??
                      [a?.apellido, a?.nombre].filter(Boolean).join(" ") ??
                      a?.full_name ??
                      a?.nombre_completo ??
                      String(key ?? "")
                    const sub =
                      a?.id_alumno ??
                      a?.codigo ??
                      a?.legajo ??
                      a?.curso ??
                      ""
                    return (
                      <option key={String(key)} value={String(key)}>
                        {label}
                        {sub ? ` (${sub})` : ""}
                      </option>
                    )
                  })}
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="asuntoInd">Asunto</Label>
                <Input
                  id="asuntoInd"
                  value={asuntoInd}
                  onChange={(e) => setAsuntoInd(e.target.value)}
                  required
                />
              </div>
              <div className="sm:pt-6 text-xs text-gray-500">
                El mensaje se enviará al buzón del alumno/padre.
              </div>
            </div>

            <div>
              <Label htmlFor="cuerpoInd">Mensaje</Label>
              <Textarea
                id="cuerpoInd"
                value={cuerpoInd}
                onChange={(e) => setCuerpoInd(e.target.value)}
                rows={5}
                required
              />
            </div>

            <DialogFooter>
              <Button type="button" onClick={() => setOpenInd(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={loadingInd || !alumnoInd}>
                {loadingInd ? "Enviando…" : "Enviar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={openGrp} onOpenChange={setOpenGrp}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enviar mensaje grupal</DialogTitle>
            <DialogDescription>Elegí un curso y escribí el mensaje.</DialogDescription>
          </DialogHeader>

          <form onSubmit={submitGrupal} className="space-y-4">
            {msgGrpErr && <div className="text-red-600 text-sm">{msgGrpErr}</div>}
            {msgGrpOk && <SuccessMessage className="mt-1">{msgGrpOk}</SuccessMessage>}

            <div>
              <Label htmlFor="cursoGrp">Curso</Label>
              <select
                id="cursoGrp"
                className="w-full border p-2 rounded-md"
                value={cursoGrp}
                onChange={(e) => setCursoGrp(e.target.value)}
                required
              >
                <option value="">Seleccioná un curso…</option>
                {cursos.map((c) => (
                  <option key={getCursoId(c)} value={getCursoId(c)}>
                    {getCursoNombre(c)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="asuntoGrp">Asunto</Label>
              <Input
                id="asuntoGrp"
                value={asuntoGrp}
                onChange={(e) => setAsuntoGrp(e.target.value)}
                required
              />
            </div>

            <div>
              <Label htmlFor="cuerpoGrp">Mensaje</Label>
              <Textarea
                id="cuerpoGrp"
                value={cuerpoGrp}
                onChange={(e) => setCuerpoGrp(e.target.value)}
                rows={5}
                required
              />
            </div>

            <DialogFooter>
              <Button type="button" onClick={() => setOpenGrp(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={loadingGrp || !cursoGrp}>
                {loadingGrp ? "Enviando…" : "Enviar a curso"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={openSan} onOpenChange={setOpenSan}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nueva sancion disciplinaria</DialogTitle>
            <DialogDescription>
              Seleccioná curso y alumno, y escribí el motivo.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={submitSancion} className="space-y-4">
            {msgSanErr && <div className="text-red-600 text-sm">{msgSanErr}</div>}
            {msgSanOk && <SuccessMessage className="mt-1">{msgSanOk}</SuccessMessage>}

            <div>
              <Label htmlFor="cursoSan">Curso</Label>
              <select
                id="cursoSan"
                className="w-full border p-2 rounded-md"
                value={cursoSan}
                onChange={(e) => setCursoSan(e.target.value)}
                required
              >
                <option value="">Seleccioná un curso…</option>
                {cursos.map((c) => (
                  <option key={getCursoId(c)} value={getCursoId(c)}>
                    {getCursoNombre(c)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="alumnoSan">Alumno</Label>
              <select
                id="alumnoSan"
                className="w-full border p-2 rounded-md"
                value={alumnoSan}
                onChange={(e) => setAlumnoSan(e.target.value)}
                required
                disabled={!cursoSan}
              >
                <option value="">
                  {cursoSan ? "Seleccioná un alumno…" : "Elegí curso primero"}
                </option>
                {alumnosSan.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nombre}
                    {a.apellido ? ` ${a.apellido}` : ""} — {a.id_alumno}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="fechaSan">Fecha</Label>
              <Input
                id="fechaSan"
                type="date"
                value={fechaSan}
                onChange={(e) => setFechaSan(e.target.value)}
                required
              />
            </div>
<div>
              <Label htmlFor="mensajeSan">Motivo</Label>
              <Textarea
                id="mensajeSan"
                value={mensajeSan}
                onChange={(e) => setMensajeSan(e.target.value)}
                rows={5}
                required
              />
            </div>

            <DialogFooter>
              <Button type="button" onClick={() => setOpenSan(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={loadingSan || !alumnoSan}>
                {loadingSan ? "Guardando…" : "Guardar sanción"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={openAlumnoMsg} onOpenChange={setOpenAlumnoMsg}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Escribir a mis docentes</DialogTitle>
            <DialogDescription>Elegí un profesor o preceptor, redactá y enviá.</DialogDescription>
          </DialogHeader>

          {alumnoMsgErr && <div className="text-sm text-red-600">{alumnoMsgErr}</div>}
          {alumnoMsgOk && <SuccessMessage className="mt-1">{alumnoMsgOk}</SuccessMessage>}

          <div className="space-y-3">
            <div>
              <Label>Profesor</Label>
              <select
                className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                value={destSel}
                onChange={(e) => setDestSel(e.target.value)}
              >
                <option value="">Elegí un profesor…</option>
                {destinatariosProf.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.nombre || d.username || `ID ${d.id}`} {d.grupo ? `(${d.grupo})` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label>Preceptor</Label>
              <select
                className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                value={destSel}
                onChange={(e) => setDestSel(e.target.value)}
              >
                <option value="">Elegí un preceptor…</option>
                {destinatariosPrec.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.nombre || d.username || `ID ${d.id}`} {d.grupo ? `(${d.grupo})` : ""}
                  </option>
                ))}
              </select>
              {loadingAlumnoMsg && (
                <div className="text-xs text-gray-500 mt-1">Cargando destinatarios…</div>
              )}
            </div>

            <div>
              <Label>Asunto</Label>
              <Input
                value={asuntoAlu}
                onChange={(e) => setAsuntoAlu(e.target.value)}
                placeholder="Ej: Consulta sobre la tarea"
              />
            </div>

            <div>
              <Label>Mensaje</Label>
              <Textarea
                rows={6}
                value={contenidoAlu}
                onChange={(e) => setContenidoAlu(e.target.value)}
              />
            </div>

            <div className="flex justify-end">
              <Button onClick={enviarMensajeAlumno} disabled={loadingAlumnoMsg}>
                {loadingAlumnoMsg ? "Enviando…" : "Enviar"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <ComposeComunicadoFamilia
        open={openComFam}
        onOpenChange={setOpenComFam}
        // Preceptor: cursos restringidos a su curso. Profesor: lista completa de cursos.
        cursosEndpoint={effectiveGroups.includes("Preceptores") ? "/preceptor/cursos/" : "/notas/catalogos/"}
      />
    </div>
  )
}

/* ======================== Subcomponentes ======================== */

function ProximosEventosCard({
  eventos,
  eventosLoading,
  hasCurso,
  noCursoText,
  countLabel,
  titleText,
  subtitleText,
}) {
  return (
    <Card className="surface-card">
      <CardContent className="surface-card-pad flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center flex-shrink-0">
              <Calendar className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h3 className="tile-title">{titleText || "Proximos eventos"}</h3>
              <p className="tile-subtitle">
                {subtitleText || "En los proximos 5 dias"}
              </p>
            </div>
          </div>
        </div>

        <div>
          {!hasCurso ? (
            <p className="text-sm text-slate-500">
              {noCursoText || "Selecciona un curso para ver eventos."}
            </p>
          ) : eventosLoading ? (
            <p className="text-sm text-slate-500">Cargando eventos...</p>
          ) : eventos.length === 0 ? (
            <p className="text-sm text-slate-500">
              No hay eventos en los proximos 5 dias.
            </p>
          ) : (
            <div className="space-y-3">
              {eventos.map((ev) => (
                <Link
                  key={`${ev.id}-${ev.date}`}
                  href="/calendario"
                  className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 px-4 py-3 bg-white/80 hover:bg-white hover:shadow-md transition"
                >
                  <div className="min-w-0 pl-3">
                    <p className="text-sm font-semibold text-slate-900 truncate">
                      {ev.title}
                    </p>
                    <p className="text-xs text-slate-500">{formatFechaCorta(ev.date)}</p>
                  </div>
                  <span className="text-[11px] px-2 py-1 rounded-full bg-slate-100 text-slate-600">
                    {formatFechaCorta(ev.date)}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function AlumnoInicio({
  eventos,
  eventosLoading,
  inasistenciasCount,
  inasistenciasLoading,
  mensajes,
  mensajesLoading,
  myId,
}) {
  return (
    <section>
      <div className="w-full max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ProximosEventosCard eventos={eventos} eventosLoading={eventosLoading} hasCurso />

        <Card className="surface-card h-full">
          <CardContent className="surface-card-pad h-full flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center flex-shrink-0">
                <CheckSquare className="h-6 w-6 text-blue-600" />
              </div>
              <div>
                <h3 className="tile-title">Inasistencias</h3>
                <p className="tile-subtitle">Cantidad de inasistencias a Clases</p>
              </div>
            </div>

            <div className="flex flex-col items-start sm:items-end">
              <div className="min-w-[96px] h-12 px-4 rounded-full bg-indigo-50 text-indigo-700 flex items-center justify-center text-2xl font-semibold">
                {inasistenciasLoading ? "..." : inasistenciasCount}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="lg:col-span-2">
          <MensajesRecientesCard mensajes={mensajes} loading={mensajesLoading} myId={myId} />
        </div>
      </div>
    </section>
  )
}

function ProfesorInicio({ mensajes, mensajesLoading, myId }) {
  return (
    <section>
      <div className="w-full grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <Card className="surface-card">
          <CardContent className="surface-card-pad flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center flex-shrink-0">
                <Plus className="h-6 w-6 text-blue-600" />
              </div>
              <div>
                <h3 className="tile-title">Accesos rapidos</h3>
                <p className="tile-subtitle">Acciones frecuentes para tu curso</p>
              </div>
            </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <Link href="/agregar_nota" className="block">
                  <Button className="w-full justify-start">
                    <Plus className="h-4 w-4 mr-2" />
                    Nueva nota
                  </Button>
                </Link>
                <Button
                  className="w-full justify-start"
                  onClick={() => {
                    try {
                      window.dispatchEvent(new Event("open-sancion"))
                    } catch {}
                  }}
                >
                  <Gavel className="h-4 w-4 mr-2" />
                  Nueva sancion
                </Button>
              </div>
            </CardContent>
        </Card>

        <MensajesRecientesCard
          mensajes={mensajes}
          loading={mensajesLoading}
          myId={myId}
        />
      </div>
    </section>
  )
}

function PreceptorInicio({
  mensajes,
  mensajesLoading,
  myId,
}) {
  return (
    <section className="min-h-[60vh] flex items-center">
      <div className="w-full max-w-5xl mx-auto">
          <MensajesRecientesCard
            mensajes={mensajes}
            loading={mensajesLoading}
            myId={myId}
          />
      </div>
    </section>
  )
}

function PadreInicio({
  eventos,
  eventosLoading,
  hasHijo,
  hijoLabel,
  showHijoLabel,
  mensajes,
  mensajesLoading,
  myId,
}) {
  return (
    <section className="min-h-[60vh] flex items-center">
      <div className="w-full max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ProximosEventosCard
          eventos={eventos}
          eventosLoading={eventosLoading}
          hasCurso={hasHijo}
          noCursoText="No hay hijos vinculados."
          subtitleText={
            showHijoLabel && hijoLabel
              ? (
                <span>
                  En los proximos 5 dias · <strong>{hijoLabel}</strong>
                </span>
              )
              : "En los proximos 5 dias"
          }
          countLabel="eventos"
        />
        <MensajesRecientesCard
          mensajes={mensajes}
          loading={mensajesLoading}
          myId={myId}
        />
      </div>
    </section>
  )
}

function MensajesRecientesCard({ mensajes, loading, myId }) {
  return (
    <Card className="surface-card">
      <CardContent className="surface-card-pad flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center flex-shrink-0">
              <Inbox className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h3 className="tile-title">Ultimos mensajes</h3>
              <p className="tile-subtitle">Bandeja de entrada</p>
            </div>
          </div>
          <Button
            type="button"
            variant="primary"
            size="icon"
            className="h-9 w-9"
            onClick={() => {
              try {
                window.dispatchEvent(new Event("open-send-picker"))
              } catch {}
            }}
            aria-label="Nuevo mensaje"
          >
            <Pencil className="h-4 w-4 text-white" />
          </Button>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Cargando mensajes...</p>
        ) : mensajes?.length ? (
          <div className="space-y-3">
            {mensajes.map((m) => {
              const id = m?.thread_id ?? m?.id
              const href = id ? `/mensajes/hilo/${encodeURIComponent(String(id))}` : "/mensajes"
              const asunto = String(m?.asunto || m?.titulo || "Mensaje").trim()
              const emisor = String(m?.emisor || m?.remitente || "").trim()
              const fecha = m?.fecha || m?.fecha_envio || ""
              const unread = esNoLeido(m, myId)
              return (
                <Link
                  key={`msg-${m?.id}-${m?.fecha}`}
                  href={href}
                  className={
                    "relative flex items-center justify-between gap-4 rounded-xl border px-4 py-3 transition " +
                    (unread
                      ? "border-blue-200 bg-blue-50 hover:bg-blue-50/80 shadow-sm"
                      : "border-slate-200 bg-white/80 hover:bg-white hover:shadow-md")
                  }
                >
                  <span
                    className={
                      "absolute left-4 top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full " +
                      (unread ? "bg-blue-600" : "bg-transparent")
                    }
                  />
                  <div className="min-w-0 pl-6">
                    <p
                      className={
                        "text-sm truncate " +
                        (unread ? "font-semibold text-slate-900" : "font-medium text-slate-900")
                      }
                    >
                      {asunto}
                    </p>
                    <p className="text-xs text-slate-500 truncate">
                      {emisor || "Remitente"}
                    </p>
                  </div>
                  {fecha ? (
                    <span className="text-[11px] px-2 py-1 rounded-full bg-slate-100 text-slate-600">
                      {formatFechaCorta(fecha)}
                    </span>
                  ) : null}
                </Link>
              )
            })}
          </div>
        ) : (
          <p className="text-sm text-slate-500">No tenes mensajes recientes.</p>
        )}
      </CardContent>
    </Card>
  )
}

function Tile({ icon, title, desc }) {
  return (
    <div className="flex items-start gap-4">
      <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
        {icon}
      </div>
      <div className="flex-1">
        <h3 className="tile-title">{title}</h3>
        <p className="tile-subtitle">{desc}</p>
      </div>
    </div>
  )
}

function TileButton({ title, desc, icon, onClick, emphasis = false }) {
  const keyActivate = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      onClick()
    }
  }

  const base =
    "p-4 border rounded-lg transition-colors cursor-pointer select-none outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2"

  const normal = "border-gray-200 hover:border-blue-300 hover:bg-blue-50/50"

  const emph =
    "border-blue-200 bg-blue-100 text-blue-700 shadow-sm hover:bg-blue-100/80 hover:border-blue-300"

  return (
    <div
      className={`${base} ${emphasis ? emph : normal}`}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={keyActivate}
      aria-label={title}
    >
      <div className="flex items-center gap-3 mb-2">
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center ${
            emphasis ? "bg-white" : "bg-blue-100"
          }`}
        >
          <span className={emphasis ? "text-blue-600" : ""}>{icon}</span>
        </div>
        <h4
          className={`font-medium whitespace-nowrap text-sm ${
            emphasis ? "text-blue-800" : "text-gray-900"
          }`}
        >
          {title}
        </h4>
      </div>
      <p className={`text-sm ${emphasis ? "text-blue-700/80" : "text-gray-600"}`}>
        {desc}
      </p>
    </div>
  )
}




