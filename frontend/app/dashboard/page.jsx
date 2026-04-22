"use client"

import dynamic from "next/dynamic"
import Link from "next/link"
import { useEffect, useMemo, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuthGuard, authFetch, getCachedSessionProfileData, getSessionProfile, useSessionContext } from "../_lib/auth"
import { INBOX_EVENT } from "../_lib/inbox"
import {
  getCourseDisplayName,
  getCourseLabel,
  getCourseSchoolCourseId,
  getCourseValue,
  loadCourseCatalog,
  normalizeCourseList,
} from "../_lib/courses"

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

const ComposeComunicadoFamilia = dynamic(() => import("../mensajes/_compose-comunicado-familia"), {
  loading: () => null,
})

const ROLES = ["Profesores", "Alumnos", "Padres", "Preceptores", "Directivos"]
const PREVIEW_KEY = "preview_role"
const LAST_CURSO_KEY = "ultimo_curso_seleccionado"
const LAST_HIJO_KEY = "mis_hijos_last_alumno"
const PROXIMOS_EVENTOS_DIAS = 8
const DASHBOARD_RESOURCE_MAX_AGE_MS = 30000
const DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS = 10000

const dashboardResourceCache = new Map()
const dashboardResourcePromises = new Map()

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

  const legajo = me?.alumno?.id_alumno
  if (legajo != null && legajo !== "") return legajo

  const pk = me?.alumno?.id ?? me?.alumno?.pk
  if (pk != null && pk !== "") return pk

  return null
}

async function resolveAlumnoRouteId(me) {
  return alumnoRouteIdFromMe(me)
}

async function fetchProfile(fetcher) {
  try {
    return await getSessionProfile()
  } catch (err) {
    throw new Error(err?.message || "No se pudo obtener el perfil")
  }
}

async function loadDashboardResource(cacheKey, loader, maxAgeMs = DASHBOARD_RESOURCE_MAX_AGE_MS) {
  const key = String(cacheKey || "").trim()
  if (!key || typeof loader !== "function") {
    return await loader()
  }

  const cached = dashboardResourceCache.get(key)
  if (cached && cached.expiresAt > Date.now()) {
    return cached.data
  }

  if (dashboardResourcePromises.has(key)) {
    return await dashboardResourcePromises.get(key)
  }

  const promise = (async () => {
    const data = await loader()
    dashboardResourceCache.set(key, {
      data,
      expiresAt: Date.now() + maxAgeMs,
    })
    return data
  })()

  dashboardResourcePromises.set(key, promise)

  try {
    return await promise
  } finally {
    if (dashboardResourcePromises.get(key) === promise) {
      dashboardResourcePromises.delete(key)
    }
  }
}

export default function DashboardPage() {
  useAuthGuard()
  const router = useRouter()
  const sessionContext = useSessionContext()
  const cachedProfile = useMemo(() => getCachedSessionProfileData(), [])

  const [me, setMe] = useState(() => {
    if (cachedProfile) return cachedProfile
    if (
      sessionContext &&
      (Array.isArray(sessionContext.groups) || sessionContext.userLabel || sessionContext.username)
    ) {
      return {
        full_name: sessionContext.userLabel || "",
        username: sessionContext.username || "",
        groups: Array.isArray(sessionContext.groups) ? sessionContext.groups : [],
        rol: sessionContext.role || "",
        is_superuser: !!sessionContext.isSuperuser,
        school: sessionContext.school || null,
      }
    }
    return null
  })
  const [error, setError] = useState("")
  const [previewRole, setPreviewRole] = useState(() => {
    try {
      if (typeof window !== "undefined") return localStorage.getItem(PREVIEW_KEY) || ""
    } catch {}
    return ""
  })
  const blockAdminDashboard =
    (
      !!sessionContext?.isSuperuser ||
      (Array.isArray(sessionContext?.groups) &&
        sessionContext.groups.some((group) => {
          const value = String(group || "").toLowerCase()
          return value === "administradores" || value === "administrador"
        }))
    ) &&
    !previewRole
  const adminRedirectStartedRef = useRef(false)
  const courseCatalogCacheKey = useMemo(
    () =>
      `dashboard:${sessionContext?.username || "anon"}:${sessionContext?.school?.id || "default"}:${previewRole || "base"}`,
    [sessionContext?.school?.id, sessionContext?.username, previewRole]
  )
  const dashboardScopeKey = useMemo(
    () =>
      `${sessionContext?.username || "anon"}:${sessionContext?.school?.id || "default"}:${previewRole || "base"}`,
    [sessionContext?.school?.id, sessionContext?.username, previewRole]
  )
  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || ""),
    [me]
  )

  const pfetch = (url, options = {}) => {
    const headers = { ...(options?.headers || {}) }
    if (previewRole) headers["X-Preview-Role"] = previewRole
    return authFetch(url, { ...options, headers })
  }

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
  const [preceptorAlertas, setPreceptorAlertas] = useState([])
  const [preceptorAlertasLoading, setPreceptorAlertasLoading] = useState(false)
  const [preceptorAlertasInasistencias, setPreceptorAlertasInasistencias] = useState([])
  const [preceptorAlertasInasistenciasLoading, setPreceptorAlertasInasistenciasLoading] = useState(false)

  const [openAlumnoMsg, setOpenAlumnoMsg] = useState(false)
  const [loadingAlumnoMsg, setLoadingAlumnoMsg] = useState(false)
  const [alumnoMsgErr, setAlumnoMsgErr] = useState("")
  const [alumnoMsgOk, setAlumnoMsgOk] = useState("")
  const [alumnoDestType, setAlumnoDestType] = useState("profesor")
  const [destSel, setDestSel] = useState("")
  const [asuntoAlu, setAsuntoAlu] = useState("")
  const [contenidoAlu, setContenidoAlu] = useState("")
  const [destinatariosProf, setDestinatariosProf] = useState([])
  const [destinatariosPrec, setDestinatariosPrec] = useState([])

  const getCursoId = (c) => getCourseValue(c) || ""
  const getCursoNombre = (c) => getCourseLabel(c) || String(getCursoId(c))
  const cursoIndId = useMemo(() => getCourseSchoolCourseId(cursoInd, cursos), [cursoInd, cursos])
  const cursoGrpId = useMemo(() => getCourseSchoolCourseId(cursoGrp, cursos), [cursoGrp, cursos])
  const cursoSanId = useMemo(() => getCourseSchoolCourseId(cursoSan, cursos), [cursoSan, cursos])
  const profesorCursoSelId = useMemo(
    () => getCourseSchoolCourseId(profesorCursoSel, cursos),
    [profesorCursoSel, cursos]
  )
  const alumnoCursoId = useMemo(() => getCourseSchoolCourseId(alumnoCurso, cursos), [alumnoCurso, cursos])

  useEffect(() => {
    try {
      if (typeof window !== "undefined") {
        const saved = localStorage.getItem(PREVIEW_KEY) || ""
        setPreviewRole((current) => (current === saved ? current : saved))
      }
    } catch {}
  }, [])

  useEffect(() => {
    if (!blockAdminDashboard || adminRedirectStartedRef.current) return
    adminRedirectStartedRef.current = true
    router.replace("/admin/colegio")
  }, [blockAdminDashboard, router])

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
    if (blockAdminDashboard) return
    ;(async () => {
      try {
        const data = await fetchProfile(pfetch)
        setMe(data)
        setError("")
      } catch (err) {
        setError(err?.message || "No se pudo obtener el perfil")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blockAdminDashboard, previewRole])

  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoadingAlumnoId(true)
      try {
        const id = await resolveAlumnoRouteId(me || {})
        if (alive) setAlumnoIdSelf(id)
      } finally {
        if (alive) setLoadingAlumnoId(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [me])

  useEffect(() => {
    ;(async () => {
      try {
        const list = await loadCourseCatalog({
          fetcher: pfetch,
          urls: ["/api/notas/catalogos/"],
          cacheKey: courseCatalogCacheKey,
        })
        setCursos(normalizeCourseList(list))
      } catch {}
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseCatalogCacheKey])

  useEffect(() => {
    if (!cursoInd) {
      setAlumnosInd([])
      setAlumnoInd("")
      return
    }
    if (cursoIndId == null) {
      setAlumnosInd([])
      setAlumnoInd("")
      setMsgIndErr("No se pudo resolver el curso seleccionado.")
      return
    }
    ;(async () => {
      try {
        const alumnos = await loadDashboardResource(
          `dashboard-curso-alumnos:${dashboardScopeKey}:${cursoIndId}`,
          async () => {
            const res = await pfetch(
              `/api/alumnos/?school_course_id=${encodeURIComponent(String(cursoIndId))}`
            )
            if (!res.ok) return []
            const j = await res.json().catch(() => ({}))
            return Array.isArray(j?.alumnos) ? j.alumnos : []
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
        setAlumnosInd(Array.isArray(alumnos) ? alumnos : [])
      } catch {
        setMsgIndErr("No se pudieron cargar los alumnos.")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoInd, cursoIndId, dashboardScopeKey, previewRole, cursos])

  useEffect(() => {
    if (!cursoSan) {
      setAlumnosSan([])
      setAlumnoSan("")
      return
    }
    if (cursoSanId == null) {
      setAlumnosSan([])
      setAlumnoSan("")
      setMsgSanErr("No se pudo resolver el curso seleccionado.")
      return
    }
    ;(async () => {
      try {
        const alumnos = await loadDashboardResource(
          `dashboard-curso-alumnos:${dashboardScopeKey}:${cursoSanId}`,
          async () => {
            const res = await pfetch(
              `/api/alumnos/?school_course_id=${encodeURIComponent(String(cursoSanId))}`
            )
            if (!res.ok) return []
            const j = await res.json().catch(() => ({}))
            return Array.isArray(j?.alumnos) ? j.alumnos : []
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
        setAlumnosSan(Array.isArray(alumnos) ? alumnos : [])
      } catch {
        setMsgSanErr("No se pudieron cargar los alumnos.")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoSan, cursoSanId, dashboardScopeKey, previewRole, cursos])

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

        const res = await pfetch("/api/mensajes/enviar/", {
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
      if (!res.ok) throw new Error(j?.detail || `Error (HTTP ${res.status})`)
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
      if (cursoGrpId == null) {
        throw new Error("No se pudo resolver el curso seleccionado.")
      }
      const res = await pfetch("/api/mensajes/enviar_grupal/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          school_course_id: cursoGrpId,
          asunto: asuntoGrp.trim(),
          contenido: cuerpoGrp.trim(),
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(j?.detail || `Error (HTTP ${res.status})`)
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
      const res = await pfetch("/api/sanciones/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          alumno: Number(alumnoSan),
          fecha: fechaSan,
mensaje: mensajeSan.trim(),
        }),
      })
      const j = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(j?.detail || `Error (HTTP ${res.status})`)
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

  const cursoSugeridoAlumnoId = useMemo(() => {
    const schoolCourseId = me?.alumno?.school_course_id ?? null
    if (schoolCourseId == null || schoolCourseId === "") return null
    const parsed = Number(schoolCourseId)
    if (Number.isNaN(parsed)) return null
    return parsed
  }, [me])

  useEffect(() => {
    if (!openAlumnoMsg) return
    let alive = true
    ;(async () => {
      setLoadingAlumnoMsg(true)
      setAlumnoMsgErr("")
      try {
        const data = await loadDashboardResource(
          `dashboard-destinatarios:${dashboardScopeKey}:${cursoSugeridoAlumnoId ?? "none"}`,
          async () => {
            const base = "/api/mensajes/destinatarios_docentes/"
            const courseQuery =
              cursoSugeridoAlumnoId != null
                ? `school_course_id=${encodeURIComponent(String(cursoSugeridoAlumnoId))}`
                : ""
            const url = courseQuery ? `${base}?${courseQuery}` : base
            const r = await pfetch(url)
            if (!r.ok) return {}
            return await r.json().catch(() => ({}))
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )

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
  }, [openAlumnoMsg, cursoSugeridoAlumnoId, dashboardScopeKey, previewRole])

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
      ...(cursoSugeridoAlumnoId != null ? { school_course_id: cursoSugeridoAlumnoId } : {}),
    }

    const tries = [
      "/api/mensajes/alumno/enviar/",
      "/api/mensajes/enviar/",
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

  const baseGroups = Array.isArray(me?.groups) ? me.groups : []
  const isSuper = !!me?.is_superuser
  const myId = me?.id ?? me?.user?.id ?? null

  const effectiveGroups = isSuper && previewRole ? [previewRole] : baseGroups
  const showAll = isSuper && !previewRole

  const showProfesor = showAll || effectiveGroups.includes("Profesores")
  const showAlumno = showAll || effectiveGroups.includes("Alumnos")
  const showPadre = showAll || effectiveGroups.includes("Padres")
  const showPreceptor = showAll || effectiveGroups.includes("Preceptores")
  const showDirectivo = showAll || effectiveGroups.includes("Directivos")
  const showDocenteCursos = showProfesor || showPreceptor || showDirectivo
  const isAlumnoOnly = showAlumno && !showProfesor && !showPadre && !showPreceptor && !showDirectivo
  const isAlumnoOrPadreOnly = (showAlumno || showPadre) && !showProfesor && !showPreceptor && !showDirectivo
  const showLegacyDashboardCards = false

  useEffect(() => {
    const handler = () => {
      setOpenSendPicker(true)
    }
    if (typeof window !== "undefined") {
      window.addEventListener("open-send-picker", handler)
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("open-send-picker", handler)
      }
    }
  }, [isAlumnoOnly])

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
    if (profesorCursoSelId == null) {
      setEventosProfesor([])
      return
    }
    let alive = true
    ;(async () => {
      setEventosProfesorLoading(true)
      try {
        const desde = hoyISO()
        const hasta = addDaysISO(desde, PROXIMOS_EVENTOS_DIAS)
        const eventos = await loadDashboardResource(
          `profesor-eventos:${dashboardScopeKey}:${profesorCursoSelId}:${desde}:${hasta}`,
          async () => {
            const params = new URLSearchParams({
              school_course_id: String(profesorCursoSelId),
              desde,
              hasta,
            })
            const res = await pfetch(`/eventos/?${params.toString()}`)
            if (!res.ok) return []
            const raw = await res.json().catch(() => ({}))
            return parseEventosPayload(raw)
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
        if (alive) setEventosProfesor(Array.isArray(eventos) ? eventos : [])
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
  }, [showDocenteCursos, profesorCursoSel, profesorCursoSelId, previewRole])

  useEffect(() => {
    if (!showAlumno) return
    let alive = true
    ;(async () => {
      setAlumnoCursoLoaded(false)
      try {
        const courseValue = await loadDashboardResource(
          `alumno-curso:${dashboardScopeKey}`,
          async () => {
            const res = await pfetch("/api/mi-curso/")
            if (!res.ok) return ""
            const data = await res.json().catch(() => ({}))
            return String(data?.school_course_id ?? "").trim()
          }
        )
        if (alive) setAlumnoCurso(courseValue)
      } catch {
      } finally {
        if (alive) setAlumnoCursoLoaded(true)
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardScopeKey, showAlumno, previewRole])

  useEffect(() => {
    if (!showPadre) return
    let alive = true

    ;(async () => {
      setPadreHijosLoaded(false)
      try {
        const hijos = await loadDashboardResource(
          `padre-hijos:${dashboardScopeKey}`,
          async () => {
            const r = await pfetch("/api/padres/mis-hijos/")
            if (!r.ok) return []
            const data = await r.json().catch(() => ({}))
            const arr = Array.isArray(data) ? data : data?.results || []
            return Array.isArray(arr) ? arr : []
          }
        )
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
  }, [dashboardScopeKey, showPadre, previewRole])

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
        const hasta = addDaysISO(desde, PROXIMOS_EVENTOS_DIAS)
        const eventos = await loadDashboardResource(
          `padre-eventos:${dashboardScopeKey}:${padreKidId}:${desde}:${hasta}`,
          async () => {
            const res = await pfetch(
              `/api/padres/hijos/${encodeURIComponent(padreKidId)}/eventos/?desde=${desde}&hasta=${hasta}`
            )
            if (!res.ok) return []
            const raw = await res.json().catch(() => ({}))
            return parseEventosPayload(raw)
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
        if (alive) setEventosPadre(Array.isArray(eventos) ? eventos : [])
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
    if (!showPadre && !showAlumno && !showPreceptor && !showDirectivo && !showProfesor) return
    let alive = true
    ;(async () => {
      setMensajesHomeLoading(true)
      try {
        const list = await loadDashboardResource(
          `mensajes-home:${dashboardScopeKey}`,
          async () => {
            const r = await pfetch("/api/mensajes/recibidos/?limit=5")
            let next = []
            if (r.ok) {
              const data = await r.json().catch(() => ({}))
              next = Array.isArray(data) ? data : []
            }
            next.sort((a, b) => {
              const da = new Date(a?.fecha || a?.fecha_envio || 0).getTime()
              const db = new Date(b?.fecha || b?.fecha_envio || 0).getTime()
              return db - da
            })
            return next.slice(0, 5)
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
        if (alive) setMensajesHome(Array.isArray(list) ? list : [])
      } catch {
        if (alive) setMensajesHome([])
      } finally {
        if (alive) setMensajesHomeLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [showPadre, showAlumno, showPreceptor, showDirectivo, showProfesor, previewRole])

  useEffect(() => {
    if (!showPreceptor) return
    let alive = true
    ;(async () => {
      setPreceptorAlertasLoading(true)
      setPreceptorAlertasInasistenciasLoading(true)
      try {
        const data = await loadDashboardResource(
          `preceptor-alertas:${dashboardScopeKey}`,
          async () => {
            const [academicasRes, inasistenciasRes] = await Promise.all([
              pfetch("/api/preceptor/alertas-academicas/?limit=12"),
              pfetch("/api/preceptor/alertas-inasistencias/?limit=12"),
            ])
            const academicasData = academicasRes.ok
              ? await academicasRes.json().catch(() => ({}))
              : {}
            const inasistenciasData = inasistenciasRes.ok
              ? await inasistenciasRes.json().catch(() => ({}))
              : {}
            return {
              academicas: Array.isArray(academicasData?.results) ? academicasData.results : [],
              inasistencias: Array.isArray(inasistenciasData?.results)
                ? inasistenciasData.results
                : [],
            }
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
        if (alive) {
          setPreceptorAlertas(Array.isArray(data?.academicas) ? data.academicas : [])
          setPreceptorAlertasInasistencias(
            Array.isArray(data?.inasistencias) ? data.inasistencias : []
          )
        }
      } catch {
        if (alive) {
          setPreceptorAlertas([])
          setPreceptorAlertasInasistencias([])
        }
      } finally {
        if (alive) {
          setPreceptorAlertasLoading(false)
          setPreceptorAlertasInasistenciasLoading(false)
        }
      }
    })()
    return () => {
      alive = false
    }
  }, [showPreceptor, previewRole])

  useEffect(() => {
    if (!isAlumnoOnly) return
    if (!alumnoCurso) return
    if (alumnoCursoId == null) {
      setEventosProximos([])
      return
    }
    let alive = true
    ;(async () => {
      setEventosLoading(true)
      try {
        const desde = hoyISO()
        const hasta = addDaysISO(desde, PROXIMOS_EVENTOS_DIAS)
        const eventos = await loadDashboardResource(
          `alumno-eventos:${dashboardScopeKey}:${alumnoCursoId}:${desde}:${hasta}`,
          async () => {
            const params = new URLSearchParams({
              school_course_id: String(alumnoCursoId),
              desde,
              hasta,
            })
            const res = await pfetch(`/eventos/?${params.toString()}`)
            if (!res.ok) return []
            const raw = await res.json().catch(() => ({}))
            return parseEventosPayload(raw)
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
        if (alive) setEventosProximos(Array.isArray(eventos) ? eventos : [])
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
  }, [isAlumnoOnly, alumnoCurso, alumnoCursoId, previewRole])

  useEffect(() => {
    if (!isAlumnoOnly) return
    if (!alumnoIdSelf) return
    let alive = true
    ;(async () => {
      setInasistenciasLoading(true)
      try {
        const total = await loadDashboardResource(
          `alumno-inasistencias:${dashboardScopeKey}:${alumnoIdSelf}`,
          async () => {
            const encoded = encodeURIComponent(alumnoIdSelf)
            const isNumericId = /^\d+$/.test(String(alumnoIdSelf || ""))
            let asistencias = []
            const url = isNumericId
              ? `/api/asistencias/?alumno=${encoded}`
              : `/api/asistencias/?id_alumno=${encoded}`
            const res = await pfetch(url)
            if (res.ok) {
              const data = await res.json().catch(() => ({}))
              const list = data?.results || []
              if (Array.isArray(list)) {
                asistencias = list
              }
            }

            let nextTotal = 0
            for (const a of asistencias) {
              const tipo = normalizeAsistenciaTipo(asistenciaTipoFromAny(a)) || "clases"
              if (tipo !== "clases") continue
              if (isJustificadaFromAny(a)) continue
              const estado = estadoTexto(asistenciaEstadoFromAny(a))
              if (estado === "Ausente") nextTotal += 1
              else if (estado === "Tarde") nextTotal += 0.5
            }
            return nextTotal
          },
          DASHBOARD_DYNAMIC_RESOURCE_MAX_AGE_MS
        )
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

  if (blockAdminDashboard) {
    return (
      <div className="surface-card surface-card-pad">Redirigiendo al panel de administracion...</div>
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
              eventos={eventosProfesor}
              eventosLoading={eventosProfesorLoading || !profesorCursoLoaded}
              hasCurso={!!profesorCursoSel}
              cursoSel={profesorCursoSel}
              onCursoChange={setProfesorCursoSel}
              cursos={cursos}
              getCursoId={getCursoId}
              getCursoNombre={getCursoNombre}
              mensajes={mensajesHome}
              mensajesLoading={mensajesHomeLoading}
              myId={myId}
            />
        ) : showPreceptor || showDirectivo ? (
            <PreceptorInicio
              eventos={eventosProfesor}
              eventosLoading={eventosProfesorLoading || !profesorCursoLoaded}
              hasCurso={!!profesorCursoSel}
              cursoSel={profesorCursoSel}
              onCursoChange={setProfesorCursoSel}
              cursos={cursos}
              getCursoId={getCursoId}
              getCursoNombre={getCursoNombre}
              mensajes={mensajesHome}
              mensajesLoading={mensajesHomeLoading}
              showAlerts={showPreceptor}
              alertas={preceptorAlertas}
              alertasLoading={preceptorAlertasLoading}
              alertasInasistencias={preceptorAlertasInasistencias}
              alertasInasistenciasLoading={preceptorAlertasInasistenciasLoading}
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

      {/* ✅ NUEVO: Selector “Enviar mensajes” */}
      <Dialog open={openSendPicker} onOpenChange={setOpenSendPicker}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Enviar mensajes</DialogTitle>
            <DialogDescription>
              {isAlumnoOrPadreOnly
                ? "Elegí si querés enviar a un profesor o preceptor."
                : "Elegí si querés enviar a un alumno en particular o a un curso entero."}
            </DialogDescription>
          </DialogHeader>

          {isAlumnoOrPadreOnly ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => {
                  setOpenSendPicker(false)
                  setAlumnoDestType("profesor")
                  setTimeout(() => setOpenAlumnoMsg(true), 0)
                }}
                className="border rounded-xl p-4 text-left transition school-hover-card"
              >
                <div className="text-sm font-semibold text-slate-900">Profesores</div>
                <div className="text-xs text-slate-500 mt-1">Mensaje a un profesor</div>
              </button>
              <button
                type="button"
                onClick={() => {
                  setOpenSendPicker(false)
                  setAlumnoDestType("preceptor")
                  setTimeout(() => setOpenAlumnoMsg(true), 0)
                }}
                className="border rounded-xl p-4 text-left transition school-hover-card"
              >
                <div className="text-sm font-semibold text-slate-900">Preceptores</div>
                <div className="text-xs text-slate-500 mt-1">Mensaje a un preceptor</div>
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <button
                type="button"
                onClick={abrirIndividualDesdePicker}
                className="border rounded-xl p-4 text-left transition school-hover-card"
              >
                <div className="text-sm font-semibold text-slate-900">A un alumno</div>
                <div className="text-xs text-slate-500 mt-1">Mensaje individual a un alumno</div>
              </button>
              <button
                type="button"
                onClick={abrirGrupalDesdePicker}
                className="border rounded-xl p-4 text-left transition school-hover-card"
              >
                <div className="text-sm font-semibold text-slate-900">A un curso</div>
                <div className="text-xs text-slate-500 mt-1">Mensaje grupal a un curso</div>
              </button>
              <button
                type="button"
                onClick={abrirFamiliaDesdePicker}
                className="border rounded-xl p-4 text-left transition school-hover-card"
              >
                <div className="text-sm font-semibold text-slate-900">A la familia</div>
                <div className="text-xs text-slate-500 mt-1">Comunicado para padres o tutores</div>
              </button>
            </div>
          )}

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
                      getCourseDisplayName(a) ??
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
            {alumnoDestType !== "preceptor" && (
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
            )}

            {alumnoDestType !== "profesor" && (
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
            )}

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

      {openComFam ? (
        <ComposeComunicadoFamilia
          open={openComFam}
          onOpenChange={setOpenComFam}
          cursosEndpoint="/alumnos/cursos/"
        />
      ) : null}
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
  cursos,
  cursoSel,
  onCursoChange,
  getCursoId,
  getCursoNombre,
  selectorLabel,
}) {
  const showSelector =
    Array.isArray(cursos) &&
    cursos.length > 0 &&
    typeof onCursoChange === "function" &&
    typeof getCursoId === "function" &&
    typeof getCursoNombre === "function"

  return (
    <Card className="surface-card">
      <CardContent className="surface-card-pad flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: "var(--school-accent-soft)" }}
            >
              <Calendar className="h-6 w-6" style={{ color: "var(--school-accent)" }} />
            </div>
            <div>
              <h3 className="tile-title">{titleText || "Proximos eventos"}</h3>
              <p className="tile-subtitle">
                {subtitleText ||
                  `En los proximos ${PROXIMOS_EVENTOS_DIAS} dias`}
              </p>
            </div>
          </div>
        </div>

        {showSelector ? (
          <div>
            <Label htmlFor="dashboard-eventos-curso">
              {selectorLabel || "Curso"}
            </Label>
            <select
              id="dashboard-eventos-curso"
              className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
              value={cursoSel || ""}
              onChange={(e) => onCursoChange(e.target.value)}
            >
              <option value="">Seleccioná un curso…</option>
              {cursos.map((c) => (
                <option key={getCursoId(c)} value={getCursoId(c)}>
                  {getCursoNombre(c)}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <div>
          {!hasCurso ? (
            <p className="text-sm text-slate-500">
              {noCursoText || "Selecciona un curso para ver eventos."}
            </p>
          ) : eventosLoading ? (
            <p className="text-sm text-slate-500">Cargando eventos...</p>
          ) : eventos.length === 0 ? (
            <p className="text-sm text-slate-500">
              {`No hay eventos en los proximos ${PROXIMOS_EVENTOS_DIAS} dias.`}
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
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: "var(--school-accent-soft)" }}
              >
                <CheckSquare className="h-6 w-6" style={{ color: "var(--school-accent)" }} />
              </div>
              <div>
                <h3 className="tile-title">Inasistencias</h3>
                <p className="tile-subtitle">Cantidad de inasistencias a Clases</p>
              </div>
            </div>

            <div className="flex flex-col items-start sm:items-end">
              <div
                className="min-w-[96px] h-12 px-4 rounded-full flex items-center justify-center text-2xl font-semibold"
                style={{
                  backgroundColor: "var(--school-accent-soft)",
                  color: "var(--school-accent)",
                }}
              >
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

function ProfesorInicio({
  eventos,
  eventosLoading,
  hasCurso,
  cursoSel,
  onCursoChange,
  cursos,
  getCursoId,
  getCursoNombre,
  mensajes,
  mensajesLoading,
  myId,
}) {
  return (
    <section>
      <div className="w-full grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <ProximosEventosCard
          eventos={eventos}
          eventosLoading={eventosLoading}
          hasCurso={hasCurso}
          noCursoText="Seleccioná un curso para ver eventos."
          cursos={cursos}
          cursoSel={cursoSel}
          onCursoChange={onCursoChange}
          getCursoId={getCursoId}
          getCursoNombre={getCursoNombre}
        />

        <Card className="surface-card">
          <CardContent className="surface-card-pad flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: "var(--school-accent-soft)" }}
              >
                <Plus className="h-6 w-6" style={{ color: "var(--school-accent)" }} />
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

        <div className="lg:col-span-2">
          <MensajesRecientesCard
            mensajes={mensajes}
            loading={mensajesLoading}
            myId={myId}
          />
        </div>
      </div>
    </section>
  )
}

function PreceptorInicio({
  eventos,
  eventosLoading,
  hasCurso,
  cursoSel,
  onCursoChange,
  cursos,
  getCursoId,
  getCursoNombre,
  mensajes,
  mensajesLoading,
  showAlerts,
  alertas,
  alertasLoading,
  alertasInasistencias,
  alertasInasistenciasLoading,
  myId,
}) {
  if (showAlerts) {
    return (
      <section>
        <div className="w-full max-w-7xl mx-auto grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
          <ProximosEventosCard
            eventos={eventos}
            eventosLoading={eventosLoading}
            hasCurso={hasCurso}
            noCursoText="Seleccioná un curso para ver eventos."
            cursos={cursos}
            cursoSel={cursoSel}
            onCursoChange={onCursoChange}
            getCursoId={getCursoId}
            getCursoNombre={getCursoNombre}
          />
          <MensajesRecientesCard mensajes={mensajes} loading={mensajesLoading} myId={myId} />
          <AlertasAcademicasCard alertas={alertas} loading={alertasLoading} />
          <AlertasInasistenciasCard
            alertas={alertasInasistencias}
            loading={alertasInasistenciasLoading}
          />
        </div>
      </section>
    )
  }

  return (
    <section>
      <div className="w-full max-w-7xl mx-auto grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
        <ProximosEventosCard
          eventos={eventos}
          eventosLoading={eventosLoading}
          hasCurso={hasCurso}
          noCursoText="Seleccioná un curso para ver eventos."
          cursos={cursos}
          cursoSel={cursoSel}
          onCursoChange={onCursoChange}
          getCursoId={getCursoId}
          getCursoNombre={getCursoNombre}
        />
        <MensajesRecientesCard mensajes={mensajes} loading={mensajesLoading} myId={myId} />
      </div>
    </section>
  )
}

function AlertasAcademicasCard({ alertas, loading }) {
  const visibleAlertas = Array.isArray(alertas) ? alertas.slice(0, 5) : []

  return (
    <Card className="surface-card">
      <CardContent className="surface-card-pad flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <ClipboardList className="h-6 w-6 text-amber-700" />
          </div>
          <div>
            <h3 className="tile-title">Atencion academica</h3>
            <p className="tile-subtitle">Alumnos detectados en alerta</p>
          </div>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Cargando alertas...</p>
        ) : !Array.isArray(alertas) || alertas.length === 0 ? (
          <p className="text-sm text-slate-500">No hay alumnos en alerta academica.</p>
        ) : (
          <div className="space-y-3">
            {visibleAlertas.map((it, idx) => {
              const a = it?.alumno || {}
              const nombre = [String(a?.apellido || "").trim(), String(a?.nombre || "").trim()]
                .filter(Boolean)
                .join(", ") || String(a?.id_alumno || "Alumno")
              const alumnoId = a?.id
              const href = alumnoId
                ? `/alumnos/${encodeURIComponent(String(alumnoId))}?tab=notas`
                : "/alumnos"
              const materias = Array.isArray(it?.materias_en_alerta) ? it.materias_en_alerta : []
              return (
                <Link
                  key={`alerta-alumno-${alumnoId || idx}`}
                  href={href}
                  className="flex items-center justify-between gap-4 rounded-xl border border-amber-200 px-4 py-3 bg-amber-50/40 hover:bg-amber-50 transition"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900 truncate">{nombre}</p>
                    <p className="text-xs text-slate-600 truncate">
                      {getCourseDisplayName(a) ? `Curso ${getCourseDisplayName(a)}` : "Curso s/d"}
                      {materias.length ? ` · ${materias.join(", ")}` : ""}
                    </p>
                  </div>
                  <span className="text-[11px] px-2 py-1 rounded-full bg-amber-100 text-amber-800">
                    Ver perfil
                  </span>
                </Link>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function AlertasInasistenciasCard({ alertas, loading }) {
  return (
    <Card className="surface-card">
      <CardContent className="surface-card-pad flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-rose-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <CheckSquare className="h-6 w-6 text-rose-700" />
          </div>
          <div>
            <h3 className="tile-title">Alerta por inasistencias</h3>
            <p className="tile-subtitle">Ausencias consecutivas detectadas</p>
          </div>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Cargando alertas...</p>
        ) : !Array.isArray(alertas) || alertas.length === 0 ? (
          <p className="text-sm text-slate-500">No hay alumnos con alerta por inasistencias.</p>
        ) : (
          <div className="space-y-3">
            {alertas.map((it, idx) => {
              const a = it?.alumno || {}
              const nombre = [String(a?.apellido || "").trim(), String(a?.nombre || "").trim()]
                .filter(Boolean)
                .join(", ") || String(a?.id_alumno || "Alumno")
              const alumnoId = a?.id
              const href = alumnoId
                ? `/alumnos/${encodeURIComponent(String(alumnoId))}?tab=asistencias`
                : "/alumnos"
              const totalInas = Number(it?.total_inasistencias_clases || 0)
              return (
                <Link
                  key={`alerta-inasist-${alumnoId || idx}`}
                  href={href}
                  className="flex items-center justify-between gap-4 rounded-xl border border-rose-200 px-4 py-3 bg-rose-50/40 hover:bg-rose-50 transition"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900 truncate">{nombre}</p>
                    <p className="text-xs text-slate-600 truncate">
                      {getCourseDisplayName(a) ? `Curso ${getCourseDisplayName(a)}` : "Curso s/d"}
                      {totalInas > 0 ? ` · ${totalInas} inasistencias totales a clases` : " · 0 inasistencias totales a clases"}
                    </p>
                  </div>
                  <span className="text-[11px] px-2 py-1 rounded-full bg-rose-100 text-rose-800">
                    Ver asistencias
                  </span>
                </Link>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
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
                  En los proximos {PROXIMOS_EVENTOS_DIAS} dias ·{" "}
                  <strong>{hijoLabel}</strong>
                </span>
              )
              : `En los proximos ${PROXIMOS_EVENTOS_DIAS} dias`
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
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: "var(--school-accent-soft)" }}
            >
              <Inbox className="h-6 w-6" style={{ color: "var(--school-accent)" }} />
            </div>
            <div>
              <h3 className="tile-title">Últimos mensajes</h3>
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
                      ? "shadow-sm"
                      : "border-slate-200 bg-white/80 hover:bg-white hover:shadow-md")
                  }
                  style={
                    unread
                      ? {
                          borderColor: "var(--school-accent-soft-strong)",
                          backgroundColor: "var(--school-accent-soft)",
                        }
                      : undefined
                  }
                >
                  <span
                    className="absolute left-4 top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full"
                    style={{
                      backgroundColor: unread ? "var(--school-accent)" : "transparent",
                    }}
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
          <p className="text-sm text-slate-500">No tenés mensajes recientes.</p>
        )}
      </CardContent>
    </Card>
  )
}

function Tile({ icon, title, desc }) {
  return (
    <div className="flex items-start gap-4">
      <div
        className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ backgroundColor: "var(--school-accent-soft)" }}
      >
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
    "p-4 border rounded-lg transition-colors cursor-pointer select-none outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2"

  const normal = "border-gray-200"

  const emph = "shadow-sm"

  return (
    <div
      className={`${base} ${emphasis ? emph : normal}`}
      style={
        emphasis
          ? {
              borderColor: "var(--school-accent-soft-strong)",
              backgroundColor: "var(--school-accent-soft)",
              color: "var(--school-accent)",
            }
          : undefined
      }
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={keyActivate}
      aria-label={title}
    >
      <div className="flex items-center gap-3 mb-2">
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center"
          style={{
            backgroundColor: emphasis ? "#ffffff" : "var(--school-accent-soft)",
          }}
        >
          <span style={emphasis ? { color: "var(--school-accent)" } : undefined}>{icon}</span>
        </div>
        <h4
          className="font-medium whitespace-nowrap text-sm text-gray-900"
          style={emphasis ? { color: "var(--school-accent)" } : undefined}
        >
          {title}
        </h4>
      </div>
      <p
        className="text-sm text-gray-600"
        style={emphasis ? { color: "color-mix(in srgb, var(--school-accent) 82%, white)" } : undefined}
      >
        {desc}
      </p>
    </div>
  )
}




