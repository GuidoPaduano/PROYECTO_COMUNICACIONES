"use client"

import Link from "next/link"
import { Suspense, useEffect, useMemo, useState } from "react"
import { useSearchParams, useRouter, useParams } from "next/navigation"
import { useAuthGuard, authFetch } from "../../_lib/auth"
import { INBOX_EVENT } from "../../_lib/inbox" // ✅ NUEVO: evento unificado inbox
import {
  ChevronLeft,
  ChevronDown,
  Mail,
  Users,
  User as UserIcon,
  ClipboardList,
  Gavel,
  CalendarDays,
  Pencil,
} from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import ComposeMensajeAlumno from "./_compose-alumno"
import { NotificationBell } from "@/components/notification-bell"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

/* ======================== Fix Mis Hijos: persistencia tab ======================== */
const MIS_HIJOS_LAST_TAB_KEY = "mis_hijos_last_tab"
const MIS_HIJOS_LAST_ALUMNO_KEY = "mis_hijos_last_alumno"
const VALID_TABS = new Set(["notas", "sanciones", "asistencias"])
const ALUMNO_DETAIL_CACHE_PREFIX = "alumno_detail_cache:"
const ALUMNO_DETAIL_CACHE_TTL_MS = 5 * 60 * 1000
const ALUMNO_DETAIL_ENDPOINT_KEY = "alumno_detail_endpoint"

function safeGetLS(key) {
  try {
    if (typeof window === "undefined") return ""
    return localStorage.getItem(key) || ""
  } catch {
    return ""
  }
}
function safeSetLS(key, value) {
  try {
    if (typeof window === "undefined") return
    localStorage.setItem(key, String(value ?? ""))
  } catch {}
}

function safeGetLSJson(key) {
  const raw = safeGetLS(key)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function safeSetLSJson(key, value) {
  try {
    if (typeof window === "undefined") return
    localStorage.setItem(key, JSON.stringify(value))
  } catch {}
}

function getCachedAlumnoDetail(idParam) {
  if (!idParam) return null
  const cached = safeGetLSJson(`${ALUMNO_DETAIL_CACHE_PREFIX}${idParam}`)
  if (!cached?.data) return null
  if (cached.ts && Date.now() - cached.ts > ALUMNO_DETAIL_CACHE_TTL_MS) return null
  return cached.data
}

function setCachedAlumnoDetail(idParam, data) {
  if (!idParam || !data) return
  safeSetLSJson(`${ALUMNO_DETAIL_CACHE_PREFIX}${idParam}`, {
    ts: Date.now(),
    data,
  })
}

function kidLegajo(h) {
  return h?.id_alumno ?? h?.alumno_id ?? h?.legajo ?? null
}

function kidPk(h) {
  return h?.id ?? h?.pk ?? null
}

function kidValue(h) {
  const leg = kidLegajo(h)
  const pk = kidPk(h)
  const v = leg != null && String(leg) !== "" ? leg : pk
  return v != null ? String(v) : ""
}

function kidLabel(h) {
  const apellido = h?.apellido ?? ""
  const nombre = h?.nombre ?? ""
  const base =
    [apellido, nombre].filter(Boolean).join(", ") ||
    h?.full_name ||
    h?.username ||
    "Alumno"
  const curso = h?.curso ? ` — ${h.curso}` : ""
  return `${base}${curso}`
}

/* ------------------------------------------------------------
   Helpers texto/fechas para filtros
------------------------------------------------------------ */
function normText(v) {
  return String(v ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
}

function monthKeyFromAnyDate(iso) {
  if (!iso) return ""
  const s = String(iso).trim()

  // YYYY-MM-DD -> parse local (sin corrimientos)
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (m) {
    const y = Number(m[1])
    const mo = Number(m[2]) // 01-12
    if (!Number.isFinite(y) || !Number.isFinite(mo)) return ""
    return `${String(y)}-${String(mo).padStart(2, "0")}`
  }

  try {
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return ""
    const y = d.getFullYear()
    const mo = d.getMonth() + 1
    return `${String(y)}-${String(mo).padStart(2, "0")}`
  } catch {
    return ""
  }
}

function monthLabelFromKey(key) {
  // key: YYYY-MM
  const m = /^(\d{4})-(\d{2})$/.exec(String(key || ""))
  if (!m) return String(key || "")
  const y = Number(m[1])
  const mo = Number(m[2])
  const d = new Date(y, mo - 1, 1)
  return d.toLocaleDateString("es-AR", { month: "short", year: "numeric" })
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

/** Normaliza a: "clases" | "informatica" | "catequesis" | "" */
function normalizeAsistenciaTipo(raw) {
  const s = normText(raw)
  if (!s) return "" // legacy -> lo tratamos como "clases" donde corresponda

  // si backend ya manda el slug
  if (s === "clases" || s === "informatica" || s === "catequesis") return s

  // variantes comunes
  if (s.includes("info")) return "informatica"
  if (s.includes("cateq")) return "catequesis"
  if (s.includes("clase")) return "clases"

  return s
}

function asistenciaTipoLabel(rawOrNorm) {
  const t = normalizeAsistenciaTipo(rawOrNorm) || "clases"
  if (t === "clases") return "Clases"
  if (t === "informatica") return "Informática"
  if (t === "catequesis") return "Catequesis"
  // fallback por si aparece algo raro
  return rawOrNorm ? String(rawOrNorm) : "Clases"
}

/* ------------------------------------------------------------
   Helpers HTTP
------------------------------------------------------------ */
async function fetchJSON(url, opts) {
  const res = await authFetch(url, opts)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

/* ------------------------------------------------------------
   Rutas compatibles (PK o id_alumno/legajo)
------------------------------------------------------------ */
const ALUMNO_DETAIL_ENDPOINTS = [
  "/alumnos/{id}/",
  "/alumnos/detalle/{id}/",
  "/alumno/{id}/",
  "/perfil_alumno/{id}/",
  "/api/alumnos/{id}/",
]

function alumnoDetailEndpointOrder() {
  const preferred = safeGetLS(ALUMNO_DETAIL_ENDPOINT_KEY).trim()
  if (preferred && ALUMNO_DETAIL_ENDPOINTS.includes(preferred)) {
    return [preferred, ...ALUMNO_DETAIL_ENDPOINTS.filter((t) => t !== preferred)]
  }
  return ALUMNO_DETAIL_ENDPOINTS
}

async function getAlumnoIdsFromAny(idParam) {
  const encoded = encodeURIComponent(idParam)
  const order = alumnoDetailEndpointOrder()
  const tries = order.map((t) => t.replace("{id}", encoded))

  for (let i = 0; i < tries.length; i += 1) {
    const url = tries[i]
    try {
      const r = await fetchJSON(url)
      if (!r.ok) continue
      const obj = r.data || {}
      const a = obj.alumno || obj
      const pk = a?.id ?? obj?.id
      const code = a?.id_alumno ?? obj?.id_alumno ?? idParam
      if (pk || code) {
        const template = order[i]
        if (template) safeSetLS(ALUMNO_DETAIL_ENDPOINT_KEY, template)
        return { detail: obj, pk, code }
      }
    } catch {}
  }
  return { detail: null, pk: null, code: idParam }
}

/** Notas por PK o por id_alumno (ambas rutas soportadas) */
async function getNotasByPkOrCode(pk, code) {
  const codeEnc = code != null ? encodeURIComponent(String(code)) : null
  const tries = [
    // ✅ NUEVO: este es el endpoint “bueno” (backend resuelve legajo o pk)
    codeEnc && `/alumnos/${codeEnc}/notas/`,
    pk && `/alumnos/${pk}/notas/`,
    pk && `/notas/?alumno=${pk}`,
    pk && `/notas/alumno/${pk}/`,
    codeEnc && `/notas/?id_alumno=${codeEnc}`,
    codeEnc && `/notas/alumno_codigo/${codeEnc}/`,
  ].filter(Boolean)

  for (const url of tries) {
    try {
      const r = await fetchJSON(url)
      if (!r.ok) continue
      const arr = Array.isArray(r.data)
        ? r.data
        : r.data?.notas || r.data?.results || []
      if (Array.isArray(arr)) return arr
    } catch {}
  }
  return []
}

/** Sanciones por PK o id_alumno */
async function getSancionesByPkOrCode(pk, code) {
  const tries = [
    pk && `/sanciones/?alumno=${pk}`,
    pk && `/api/sanciones/?alumno=${pk}`,
    pk && `/sanciones/alumno/${pk}/`,
    code && `/sanciones/?id_alumno=${encodeURIComponent(code)}`,
    code && `/api/sanciones/?id_alumno=${encodeURIComponent(code)}`,
    code && `/sanciones/alumno_codigo/${encodeURIComponent(code)}/`,
  ].filter(Boolean)

  for (const url of tries) {
    try {
      const r = await fetchJSON(url)
      if (!r.ok) continue
      const arr = Array.isArray(r.data)
        ? r.data
        : r.data?.sanciones || r.data?.results || []
      if (Array.isArray(arr)) return arr
    } catch {}
  }
  return []
}

/** Asistencias por PK o id_alumno */
async function getAsistenciasByPkOrCode(pk, code) {
  const tries = [
    pk && `/asistencias/?alumno=${pk}`,
    pk && `/api/asistencias/?alumno=${pk}`,
    pk && `/asistencias/alumno/${pk}/`,
    code && `/asistencias/?id_alumno=${encodeURIComponent(code)}`,
    code && `/api/asistencias/?id_alumno=${encodeURIComponent(code)}`,
    code && `/asistencias/alumno_codigo/${encodeURIComponent(code)}/`,
  ].filter(Boolean)

  for (const url of tries) {
    try {
      const r = await fetchJSON(url)
      if (!r.ok) continue
      const arr = Array.isArray(r.data)
        ? r.data
        : r.data?.asistencias || r.data?.results || []
      if (Array.isArray(arr)) return arr
    } catch {}
  }
  return []
}

/* ------------------------------------------------------------
   ✅ NUEVO: ID robusto de asistencia (porque no siempre viene como a.id)
------------------------------------------------------------ */
function getAsistenciaId(a) {
  if (!a || typeof a !== "object") return null
  const candidates = [
    a.id,
    a.pk,
    a.asistencia_id,
    a.asistenciaId,
    a.asistenciaID,
    a.asistencia,
    a._id,
  ]
  for (const c of candidates) {
    const v = String(c ?? "").trim()
    if (v) return v
  }
  return null
}

async function toggleJustificada(asistenciaId, nextValue) {
  const id = String(asistenciaId ?? "").trim()
  if (!id) {
    return { ok: false, status: 0, data: { detail: "Sin ID de asistencia." } }
  }

  // ✅ Priorizamos /api (authFetch recorta /api/ si se lo pasan duplicado)
  // y además soportamos rutas legacy.
  const tries = [
    `/api/asistencias/${encodeURIComponent(id)}/justificar/`,
    `/api/asistencias/${encodeURIComponent(id)}/justificar`,
    `/api/asistencias/justificar/${encodeURIComponent(id)}/`,
    `/api/asistencias/justificar/${encodeURIComponent(id)}`,
    `/asistencias/${encodeURIComponent(id)}/justificar/`,
    `/asistencias/${encodeURIComponent(id)}/justificar`,
    `/asistencias/justificar/${encodeURIComponent(id)}/`,
    `/asistencias/justificar/${encodeURIComponent(id)}`,
  ]

  // ✅ Prioridad: POST primero (muchos backends bloquean PATCH en proxies)
  const methods = ["POST", "PATCH", "PUT"]

  let last = { ok: false, status: 500, data: { detail: "No se pudo justificar." } }

  for (const url of tries) {
    for (const method of methods) {
      try {
        const r = await fetchJSON(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ justificada: nextValue }),
        })

        if (r.ok) return r

        last = r

        // 404 => probamos otra URL
        if (r.status === 404) continue

        // 405 => probamos otro método / URL
        if (r.status === 405) continue

        // cualquier otro error: la URL existe pero falló (permisos/validación/500)
        return r
      } catch {
        // seguimos probando
      }
    }
  }

  return last
}

async function updateDetalleAsistencia(asistenciaId, detalle) {
  const id = String(asistenciaId ?? "").trim()
  if (!id) {
    return { ok: false, status: 0, data: { detail: "Sin ID de asistencia." } }
  }

  const tries = [
    `/api/asistencias/${encodeURIComponent(id)}/detalle/`,
    `/api/asistencias/${encodeURIComponent(id)}/detalle`,
    `/api/asistencias/${encodeURIComponent(id)}/observacion/`,
    `/api/asistencias/${encodeURIComponent(id)}/observacion`,
    `/api/asistencias/detalle/${encodeURIComponent(id)}/`,
    `/api/asistencias/detalle/${encodeURIComponent(id)}`,
    `/api/asistencias/observacion/${encodeURIComponent(id)}/`,
    `/api/asistencias/observacion/${encodeURIComponent(id)}`,
    `/asistencias/${encodeURIComponent(id)}/detalle/`,
    `/asistencias/${encodeURIComponent(id)}/detalle`,
    `/asistencias/${encodeURIComponent(id)}/observacion/`,
    `/asistencias/${encodeURIComponent(id)}/observacion`,
    `/asistencias/detalle/${encodeURIComponent(id)}/`,
    `/asistencias/detalle/${encodeURIComponent(id)}`,
    `/asistencias/observacion/${encodeURIComponent(id)}/`,
    `/asistencias/observacion/${encodeURIComponent(id)}`,
  ]

  const methods = ["PATCH", "POST", "PUT"]
  let last = { ok: false, status: 500, data: { detail: "No se pudo guardar el detalle." } }

  for (const url of tries) {
    for (const method of methods) {
      try {
        const r = await fetchJSON(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ detalle }),
        })
        if (r.ok) return r
        last = r
        if (r.status === 404 || r.status === 405) continue
        return r
      } catch {}
    }
  }

  return last
}

/** Formatea fechas sin corrimiento: si viene "YYYY-MM-DD", se parsea en LOCAL */
function fmtFecha(iso) {
  if (!iso) return "—"

  const s = String(iso)
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (m) {
    const [, y, mo, d] = m
    const dt = new Date(Number(y), Number(mo) - 1, Number(d))
    return dt.toLocaleDateString("es-AR", {
      year: "numeric",
      month: "short",
      day: "numeric",
    })
  }

  try {
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return s
    return d.toLocaleDateString("es-AR", {
      year: "numeric",
      month: "short",
      day: "numeric",
    })
  } catch {
    return s
  }
}

/** Mapea boolean/string a "Presente"/"Ausente"/"Tarde" (fallback: muestra el texto) */
function estadoTexto(v) {
  if (v === true) return "Presente"
  if (v === false) return "Ausente"
  const s = String(v ?? "").trim().toLowerCase()
  if (!s) return "—"

  // ✅ NUEVO: tercera opción
  if (["tarde", "llegó tarde", "llego tarde", "retardo", "late", "l"].includes(s))
    return "Tarde"

  if (["presente", "p", "sí", "si", "1", "true", "y", "yes", "on", "ok"].includes(s))
    return "Presente"

  if (["ausente", "a", "no", "0", "false", "f", "n", "inasistente"].includes(s))
    return "Ausente"

  return s
}

/** Normaliza el estado real de una asistencia desde distintos formatos posibles */
function asistenciaEstadoFromAny(a) {
  if (!a || typeof a !== "object") return a

  const raw = a.estado ?? a.status ?? a.estado_asistencia
  if (raw != null && String(raw).trim() !== "") return raw

  // algunos endpoints mandan tarde separado
  const tarde = a.tarde ?? a.llego_tarde ?? a.llegó_tarde ?? a.is_tarde

  // otros mandan presente
  const pres = a.presente ?? a.asistio ?? a.asistió ?? a.pres

  // legacy: inasistente (invertido)
  if (a.inasistente === true) return "ausente"
  if (a.inasistente === false) return "presente"

  if (pres === false) return "ausente"
  if (tarde === true) return "tarde"
  if (pres === true) return "presente"

  // último fallback
  return a.asistencia ?? pres
}

function isJustificadaFromAny(a) {
  if (!a) return false
  // soporta variantes
  const v =
    a.justificada ??
    a.justificado ??
    a.justify ??
    a.is_justificada ??
    a.isJustificada ??
    false
  return v === true || v === 1 || v === "1" || v === "true"
}

function formatFaltas(val) {
  const n = Number(val)
  if (!Number.isFinite(n)) return "0"
  if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n))
  return n
    .toFixed(2)
    .replace(/0+$/, "")
    .replace(/\.$/, "")
    .replace(".", ",")
}

function toNumberOrText(val) {
  if (val == null) return "—"
  const str = String(val).trim()
  if (/^\d+(\.\d+)?$/.test(str)) return Number(str)
  return str
}

/** Extrae el cuatrimestre (1 o 2) desde distintos posibles campos/formatos */
function notaCuatr(nota) {
  const candidates = [nota?.cuatrimestre, nota?.trimestre, nota?.periodo]
  for (const v of candidates) {
    if (v == null) continue
    const s = String(v).trim()
    if (s === "1" || s === "2") return s
    const m = s.match(/\b([12])\b/)
    if (m) return m[1]
  }
  return null
}

/* ------------------------------------------------------------
   Página: PERFIL del alumno (Resumen + Notas + Sanciones + Asistencias)
------------------------------------------------------------ */
export default function AlumnoPerfilPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white flex items-center justify-center">
          <div className="text-gray-700">Cargando...</div>
        </div>
      }
    >
      <AlumnoPerfilPageInner />
    </Suspense>
  )
}

function AlumnoPerfilPageInner() {
  useAuthGuard()

  // ✅ FIX Next: params ahora es Promise -> en Client Component usamos useParams()
  const routeParams = useParams() || {}
  const alumnoid =
    routeParams?.alumnoId ?? routeParams?.alumnoid ?? routeParams?.id ?? ""

  const searchParams = useSearchParams()
  const router = useRouter()

  const [me, setMe] = useState(null)
  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || ""),
    [me]
  )

  const [unreadCount, setUnreadCount] = useState(0)

  // ✅ PADRE: selector de hijo/a dentro del perfil
  const [hijos, setHijos] = useState([])
  const [selectedKid, setSelectedKid] = useState("")
  const [hijosLoaded, setHijosLoaded] = useState(false)

  const [alumnoDetail, setAlumnoDetail] = useState(null)
  const [pk, setPk] = useState(null)
  const [code, setCode] = useState(alumnoid)

  const [notas, setNotas] = useState([])
  const [sanciones, setSanciones] = useState([])
  const [asistencias, setAsistencias] = useState([])

  const [materiasCat, setMateriasCat] = useState([])

  const [filMateria, setFilMateria] = useState("ALL")
  const [filCuatr, setFilCuatr] = useState("ALL")
  const [filTipo, setFilTipo] = useState("ALL")
  const [buscar, setBuscar] = useState("")

  const [filSancionMes, setFilSancionMes] = useState("ALL")
  const [filSancionDocente, setFilSancionDocente] = useState("ALL")
  const [buscarSanc, setBuscarSanc] = useState("")

  // ✅ NUEVO: filtros de asistencias (mes + tipo)
  const [filAsisMes, setFilAsisMes] = useState("ALL")
  const [filAsisTipo, setFilAsisTipo] = useState("ALL")
  const [detalleModal, setDetalleModal] = useState({
    open: false,
    asistenciaId: null,
    value: "",
    label: "",
    error: "",
    saving: false,
  })

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  // sección activa (tarjeta clickeada)
  const [activeSection, setActiveSection] = useState(null)

  /* ===== DEBUG banner controlado por env ===== */
  const isDev = process.env.NODE_ENV === "development"
  const debugEnv = String(process.env.NEXT_PUBLIC_DEBUG_BANNER || "").toLowerCase()
  const debugEnabled =
    isDev && (debugEnv === "1" || debugEnv === "true" || debugEnv === "yes")
  const [showDebug, setShowDebug] = useState(debugEnabled)

  useEffect(() => {
    if (!debugEnabled) return
    const t = setTimeout(() => setShowDebug(false), 6000)
    const onKey = (e) => {
      if (e.altKey && String(e.key || "").toLowerCase() === "d") {
        setShowDebug((v) => !v)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => {
      clearTimeout(t)
      window.removeEventListener("keydown", onKey)
    }
  }, [debugEnabled, alumnoid])

  // Perfil + badge no leídos
  useEffect(() => {
    let alive = true

    ;(async () => {
      const who = await fetchJSON("/auth/whoami/")
      if (alive && who.ok) setMe(who.data)
    })()

    const loadUnread = async () => {
      const r = await fetchJSON("/mensajes/unread_count/")
      if (!alive) return
      if (r.ok && typeof r.data?.count === "number") setUnreadCount(r.data.count)
    }

    // ✅ carga inicial
    loadUnread()

    // ✅ NUEVO: refrescar al vuelo cuando se envía/lee un mensaje (evento unificado + legacy)
    const onInboxChanged = () => loadUnread()
    try {
      window.addEventListener(INBOX_EVENT, onInboxChanged)
      window.addEventListener("inbox-changed", onInboxChanged) // legacy
    } catch {}

    const t = setInterval(loadUnread, 60000)

    return () => {
      alive = false
      clearInterval(t)
      try {
        window.removeEventListener(INBOX_EVENT, onInboxChanged)
        window.removeEventListener("inbox-changed", onInboxChanged)
      } catch {}
    }
  }, [])

  // Carga detalle -> pk/code -> (notas, sanciones, asistencias)
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError("")
    // ✅ reset filtros asistencia al cambiar de alumno
    setFilAsisMes("ALL")
    setFilAsisTipo("ALL")

    const cachedDetail = getCachedAlumnoDetail(alumnoid)
    if (cachedDetail && alive) {
      const cachedAlumno = cachedDetail?.alumno || cachedDetail || {}
      const cachedPk = cachedAlumno?.id ?? cachedDetail?.id ?? null
      const cachedCode =
        cachedAlumno?.id_alumno ??
        cachedDetail?.id_alumno ??
        cachedAlumno?.legajo ??
        cachedAlumno?.codigo ??
        null

      setAlumnoDetail(cachedDetail)
      setPk(cachedPk || null)
      if (cachedCode != null && String(cachedCode).trim()) {
        setCode(String(cachedCode))
      }
    }

    ;(async () => {
      try {
        const { detail, pk, code } = await getAlumnoIdsFromAny(alumnoid)
        if (!detail) throw new Error("No se encontró información del alumno.")
        if (!alive) return
        setAlumnoDetail(detail)
        setPk(pk || null)
        setCode(code || alumnoid)
        setCachedAlumnoDetail(alumnoid, detail)

        const [n, s, a] = await Promise.all([
          getNotasByPkOrCode(pk, code),
          getSancionesByPkOrCode(pk, code),
          getAsistenciasByPkOrCode(pk, code),
        ])
        if (!alive) return
        setNotas(Array.isArray(n) ? n : [])
        setSanciones(Array.isArray(s) ? s : [])
        setAsistencias(Array.isArray(a) ? a : [])
      } catch (e) {
        if (alive)
          setError(e?.message || "No se pudieron cargar los datos del alumno.")
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [alumnoid])

  // Catálogo de materias (opcional)
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const r = await fetchJSON("/notas/catalogos/")
        if (!r.ok) return
        const d = r.data || {}
        if (!alive) return
        const materias = d.materias || d.MATERIAS || []
        setMateriasCat(Array.isArray(materias) ? materias : [])
      } catch {}
    })()
    return () => {
      alive = false
    }
  }, [])

  // Curso sugerido para el modal de “Enviar mensaje”
  const cursoParam = searchParams.get("curso")
  const fromParam = searchParams.get("from")

  // 👇 acá detectamos si venimos de /mis-notas
  const isMisNotas = fromParam === "mis-notas"

  // ✅ PADRE: ocultar acciones de navegación y “Enviar mensaje”
  const isFromMisHijos = fromParam === "/mis-hijos" || fromParam === "mis-hijos"
  const meGroups = Array.isArray(me?.groups) ? me.groups : []
  const isPadre = meGroups.includes("Padres") && !me?.is_superuser
  const isAlumno = meGroups.includes("Alumnos") && !me?.is_superuser
  const isPreceptor =
    meGroups.includes("Preceptores") || meGroups.includes("Preceptor")
  const canJustifyAsistencias =
    !!me && (me?.is_superuser || me?.is_staff || isPreceptor)
  const meLoaded = !!me
  const hidePadreNavAndMessage = isFromMisHijos || isPadre
  const showKidSelector = hidePadreNavAndMessage
  const hasHijos = hijos.length > 0

  // ✅ título dinámico del header (padre vs alumno)
  const topbarTitle = "Perfil de Alumno"

  // ✅ Carga de hijos (solo PADRE /mis-hijos) para poder cambiar de hijo sin salir del perfil
  useEffect(() => {
    if (!showKidSelector) return
    let alive = true

    ;(async () => {
      setHijosLoaded(false)
      try {
        const tries = ["/padres/mis-hijos/", "/api/padres/mis-hijos/"]
        let data = null
        for (const url of tries) {
          try {
            const r = await fetchJSON(url)
            if (!r.ok) continue
            data = r.data
            break
          } catch {}
        }

        const arr = Array.isArray(data) ? data : data?.results || data?.hijos || []

        const list = Array.isArray(arr) ? arr : []
        if (!alive) return
        setHijos(list)

        const currentCandidates = new Set(
          [String(alumnoid || ""), String(code || ""), pk != null ? String(pk) : ""]
            .map((s) => String(s).trim())
            .filter(Boolean)
        )

        const stored = safeGetLS(MIS_HIJOS_LAST_ALUMNO_KEY).trim()

        let chosen = ""

        // 1) si el actual matchea alguno del listado, lo elegimos
        for (const h of list) {
          const v = kidValue(h)
          const leg = kidLegajo(h)
          const pkid = kidPk(h)
          if (
            (v && currentCandidates.has(String(v))) ||
            (leg != null && currentCandidates.has(String(leg))) ||
            (pkid != null && currentCandidates.has(String(pkid)))
          ) {
            chosen = v || String(leg ?? pkid)
            break
          }
        }

        // 2) si no, usamos el último guardado
        if (!chosen && stored) {
          const exists = list.some((h) => String(kidValue(h)) === String(stored))
          if (exists) chosen = String(stored)
        }

        // 3) fallback: primero
        if (!chosen && list.length > 0) {
          chosen = kidValue(list[0])
        }

        if (alive) {
          setSelectedKid(chosen)
          if (chosen) safeSetLS(MIS_HIJOS_LAST_ALUMNO_KEY, chosen)
        }
      } finally {
        if (alive) setHijosLoaded(true)
      }
    })()

    return () => {
      alive = false
    }
  }, [showKidSelector, alumnoid, code, pk])

  // ✅ Persistimos "último hijo visto" aunque todavía no haya cargado el listado
  useEffect(() => {
    if (!showKidSelector) return
    const v = String(selectedKid || code || alumnoid || "").trim()
    if (!v) return
    safeSetLS(MIS_HIJOS_LAST_ALUMNO_KEY, v)
  }, [showKidSelector, selectedKid, code, alumnoid])

  function onChangeKid(v) {
    const next = String(v || "").trim()
    if (!next) return

    setSelectedKid(next)
    safeSetLS(MIS_HIJOS_LAST_ALUMNO_KEY, next)

    const qs = new URLSearchParams(searchParams.toString())
    qs.set("from", "/mis-hijos")

    // mantenemos la sección actual al cambiar de hijo
    const tabNow = String(activeSection || "").toLowerCase().trim()
    if (tabNow && VALID_TABS.has(tabNow)) {
      qs.set("tab", tabNow)
    } else {
      const storedTab = safeGetLS(MIS_HIJOS_LAST_TAB_KEY).toLowerCase().trim()
      if (storedTab && VALID_TABS.has(storedTab)) qs.set("tab", storedTab)
    }

    router.push(`/alumnos/${encodeURIComponent(next)}?${qs.toString()}`)
  }

  const cursoSugerido = useMemo(() => {
    return cursoParam || alumnoDetail?.alumno?.curso || alumnoDetail?.curso || ""
  }, [cursoParam, alumnoDetail])

  // Reconstrucción del "volver a alumnos"
  const backToAlumnosHref = useMemo(() => {
    if (fromParam && fromParam !== "mis-notas") return fromParam
    const c = cursoParam || (alumnoDetail?.alumno?.curso || alumnoDetail?.curso)
    if (c) return `/gestion_alumnos/curso/${encodeURIComponent(String(c))}`
    return null
  }, [fromParam, cursoParam, alumnoDetail])

  // Handler robusto
  function handleBackToAlumnos() {
    try {
      if (
        typeof document !== "undefined" &&
        document.referrer &&
        document.referrer.startsWith(location.origin)
      ) {
        router.back()
        return
      }
    } catch {}
    if (backToAlumnosHref) {
      router.push(backToAlumnosHref)
    } else {
      router.push("/gestion_alumnos")
    }
  }

  /* ====================== FIX: tab por URL + persistencia para /mis-hijos ====================== */
  const tabParamRaw = (searchParams.get("tab") || "").toLowerCase().trim()
  const shouldRememberTab = fromParam === "/mis-hijos"

  useEffect(() => {
    const tabFromUrl = VALID_TABS.has(tabParamRaw) ? tabParamRaw : ""
    if (tabFromUrl) {
      setActiveSection(tabFromUrl)
      if (shouldRememberTab) safeSetLS(MIS_HIJOS_LAST_TAB_KEY, tabFromUrl)
      return
    }

    if (!shouldRememberTab) return

    const stored = safeGetLS(MIS_HIJOS_LAST_TAB_KEY).toLowerCase().trim()
    const chosen = VALID_TABS.has(stored) ? stored : "notas"
    setActiveSection(chosen)
  }, [shouldRememberTab, tabParamRaw, alumnoid])

  useEffect(() => {
    if (!shouldRememberTab) return
    if (!activeSection) return
    if (!VALID_TABS.has(String(activeSection))) return
    safeSetLS(MIS_HIJOS_LAST_TAB_KEY, String(activeSection))
  }, [shouldRememberTab, activeSection])

  /* ====================== Derivados ====================== */

  const notasFiltradas = useMemo(() => {
    let arr = Array.isArray(notas) ? notas.slice() : []

    if (filMateria !== "ALL") {
      arr = arr.filter(
        (n) => (n.materia || "").toLowerCase() === filMateria.toLowerCase()
      )
    }
    if (filCuatr !== "ALL") {
      arr = arr.filter((n) => notaCuatr(n) === filCuatr)
    }
    if (filTipo !== "ALL") {
      arr = arr.filter((n) => (n.tipo || "").toLowerCase() === filTipo.toLowerCase())
    }
    if (buscar.trim()) {
      const q = buscar.trim().toLowerCase()
      arr = arr.filter(
        (n) =>
          (n.materia || "").toLowerCase().includes(q) ||
          String(n.calificacion || "").toLowerCase().includes(q) ||
          (n.observaciones || n.comentarios || "").toLowerCase().includes(q)
      )
    }
    arr.sort((a, b) => {
      const da = new Date(a.fecha || a.created_at || 0).getTime()
      const db = new Date(b.fecha || b.created_at || 0).getTime()
      return db - da
    })
    return arr
  }, [notas, filMateria, filCuatr, filTipo, buscar])

  const mesesSancionesDisponibles = useMemo(() => {
    const map = new Map()
    const arr = Array.isArray(sanciones) ? sanciones : []
    for (const s of arr) {
      const key = monthKeyFromAnyDate(s.fecha || s.created_at)
      if (!key) continue
      if (!map.has(key)) map.set(key, monthLabelFromKey(key))
    }
    const out = Array.from(map.entries()).map(([key, label]) => ({ key, label }))
    out.sort((a, b) => String(b.key).localeCompare(String(a.key)))
    return out
  }, [sanciones])

  const docentesSancionesDisponibles = useMemo(() => {
    const set = new Set()
    const arr = Array.isArray(sanciones) ? sanciones : []
    for (const s of arr) {
      const nombre = String(s.docente || s.creado_por_nombre || s.creado_por || "")
        .trim()
      if (nombre) set.add(nombre)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [sanciones])

  const sancionesFiltradas = useMemo(() => {
    let arr = Array.isArray(sanciones) ? sanciones.slice() : []

    if (filSancionMes !== "ALL") {
      arr = arr.filter(
        (s) =>
          monthKeyFromAnyDate(s.fecha || s.created_at) === String(filSancionMes)
      )
    }

    if (filSancionDocente !== "ALL") {
      arr = arr.filter((s) => {
        const docente = String(
          s.docente || s.creado_por_nombre || s.creado_por || ""
        ).trim()
        return docente === String(filSancionDocente)
      })
    }

    if (buscarSanc.trim()) {
      const q = buscarSanc.trim().toLowerCase()
      arr = arr.filter(
        (s) =>
          (s.motivo || s.descripcion || s.detalle || "").toLowerCase().includes(q) ||
          (s.docente || s.creado_por_nombre || s.creado_por || "")
            .toLowerCase()
            .includes(q)
      )
    }

    arr.sort((a, b) => {
      const da = new Date(a.fecha || a.created_at || 0).getTime()
      const db = new Date(b.fecha || b.created_at || 0).getTime()
      return db - da
    })
    return arr
  }, [sanciones, filSancionMes, filSancionDocente, buscarSanc])

  // ✅ NUEVO: meses disponibles para el filtro
  const mesesDisponibles = useMemo(() => {
    const map = new Map() // key -> label
    const arr = Array.isArray(asistencias) ? asistencias : []
    for (const a of arr) {
      const key = monthKeyFromAnyDate(a.fecha || a.created_at)
      if (!key) continue
      if (!map.has(key)) map.set(key, monthLabelFromKey(key))
    }
    const out = Array.from(map.entries()).map(([key, label]) => ({ key, label }))
    out.sort((a, b) => String(b.key).localeCompare(String(a.key)))
    return out
  }, [asistencias])

  // ✅ NUEVO: asistencias filtradas por mes + tipo
  const asistenciasFiltradas = useMemo(() => {
    let arr = Array.isArray(asistencias) ? asistencias.slice() : []

    if (filAsisMes !== "ALL") {
      arr = arr.filter(
        (a) => monthKeyFromAnyDate(a.fecha || a.created_at) === String(filAsisMes)
      )
    }

    if (filAsisTipo !== "ALL") {
      const wantedNorm = normalizeAsistenciaTipo(filAsisTipo)
      arr = arr.filter((a) => {
        const tipoNorm =
          normalizeAsistenciaTipo(asistenciaTipoFromAny(a)) || "clases"
        return tipoNorm === wantedNorm
      })
    }

    // orden por fecha desc
    arr.sort((a, b) => {
      const da = new Date(a.fecha || a.created_at || 0).getTime()
      const db = new Date(b.fecha || b.created_at || 0).getTime()
      return db - da
    })

    return arr
  }, [asistencias, filAsisMes, filAsisTipo])

  // ✅ NUEVO: total de inasistencias ponderadas SIEMPRE (no filtra por mes)
  // Solo respeta el filtro de tipo (Clases / Informática / Catequesis / Todas)
  // Presente = 0 · Ausente = 1 · Tarde = 0,50
  const asistenciasParaTotal = useMemo(() => {
    let arr = Array.isArray(asistencias) ? asistencias.slice() : []

    if (filAsisTipo !== "ALL") {
      const wantedNorm = normalizeAsistenciaTipo(filAsisTipo)
      arr = arr.filter((a) => {
        const tipoNorm =
          normalizeAsistenciaTipo(asistenciaTipoFromAny(a)) || "clases"
        return tipoNorm === wantedNorm
      })
    }

    return arr
  }, [asistencias, filAsisTipo])

  const totalInasistencias = useMemo(() => {
    const arr = Array.isArray(asistenciasParaTotal) ? asistenciasParaTotal : []
    let sum = 0
    for (const a of arr) {
      if (isJustificadaFromAny(a)) continue
      const texto = estadoTexto(asistenciaEstadoFromAny(a))
      if (texto === "Ausente") sum += 1
      else if (texto === "Tarde") sum += 0.5
    }
    return sum
  }, [asistenciasParaTotal])

  const openDetalleModal = (asistencia) => {
    const asistenciaId = getAsistenciaId(asistencia)
    if (!asistenciaId) return
    const detalle =
      asistencia?.detalle || asistencia?.observaciones || asistencia?.observacion || ""
    const tipoNorm = normalizeAsistenciaTipo(asistenciaTipoFromAny(asistencia)) || "clases"
    const label = `${fmtFecha(asistencia?.fecha || asistencia?.created_at)} - ${asistenciaTipoLabel(tipoNorm)}`
    setDetalleModal({
      open: true,
      asistenciaId,
      value: detalle,
      label,
      error: "",
      saving: false,
    })
  }

  const closeDetalleModal = () => {
    setDetalleModal({
      open: false,
      asistenciaId: null,
      value: "",
      label: "",
      error: "",
      saving: false,
    })
  }

  const handleGuardarDetalle = async () => {
    if (!detalleModal.asistenciaId || detalleModal.saving) return
    setDetalleModal((prev) => ({ ...prev, saving: true, error: "" }))

    const r = await updateDetalleAsistencia(
      detalleModal.asistenciaId,
      detalleModal.value
    )

    if (!r.ok) {
      setDetalleModal((prev) => ({
        ...prev,
        saving: false,
        error: r.data?.detail || `Error (HTTP ${r.status || "?"})`,
      }))
      return
    }

    const nuevoDetalle = r.data?.detalle ?? r.data?.observacion ?? detalleModal.value

    setAsistencias((prev) => {
      const list = Array.isArray(prev) ? prev : []
      return list.map((x) => {
        const xid = getAsistenciaId(x)
        if (String(xid) !== String(detalleModal.asistenciaId)) return x
        return {
          ...x,
          detalle: nuevoDetalle,
          observaciones: nuevoDetalle,
          observacion: nuevoDetalle,
        }
      })
    })

    closeDetalleModal()
  }

  const nombreAlumno = useMemo(() => {
    if (loading && !alumnoDetail) return ""
    const a = alumnoDetail?.alumno || alumnoDetail || {}
    return a.nombre && a.apellido
      ? `${a.nombre} ${a.apellido}`
      : a.full_name || a.apellido_y_nombre || a.nombre || "Alumno"
  }, [alumnoDetail, loading])

  const cursoAlumno = useMemo(() => {
    const a = alumnoDetail?.alumno || alumnoDetail || {}
    return a.curso || a.division || "—"
  }, [alumnoDetail])

  const legajoAlumno = useMemo(() => {
    const a = alumnoDetail?.alumno || alumnoDetail || {}
    return a.id_alumno || a.legajo || a.codigo || String(code || "")
  }, [alumnoDetail, code])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      {/* ===== Banner de depuración (opcional por env) ===== */}
      {debugEnabled && showDebug && (
        <div className="fixed z-[100] top-2 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-md bg-fuchsia-600 text-white text-xs shadow flex items-center gap-2">
          <span>
            Render: <b>app/alumnos/[alumnoId]/page.jsx</b> — alumnoId:{" "}
            <b>{String(alumnoid)}</b> — PERFIL ✅
          </span>
          <button
            type="button"
            onClick={() => setShowDebug(false)}
            className="ml-1 rounded px-1 leading-none bg-white/20 hover:bg-white/30"
            aria-label="Cerrar"
            title="Cerrar (Alt+D para alternar)"
          >
            ✕
          </button>
        </div>
      )}

      <Topbar
        title={topbarTitle}
        userLabel={userLabel}
        unreadCount={unreadCount}
        backToAlumnosHref={backToAlumnosHref}
        onBackToAlumnos={handleBackToAlumnos}
        // ✅ ocultamos volver a alumnos/cursos para padres (/mis-hijos) y también para mis-notas
        showBackAlumnos={!isMisNotas && !hidePadreNavAndMessage}
        showBackCursos={!isMisNotas && !hidePadreNavAndMessage}
      />

      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* ===== Encabezado + acciones ===== */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 bg-blue-100 rounded-xl flex items-center justify-center">
              <Users className="w-7 h-7 text-blue-600" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold">{nombreAlumno}</h1>
              <p className="text-gray-600 text-sm">
                Curso: <b>{cursoAlumno}</b> · Legajo/ID: <b>{legajoAlumno}</b>
              </p>
            </div>
          </div>

          {/* ✅ ocultamos "Enviar mensaje" cuando es padre / viene de /mis-hijos */}
          <div className="flex flex-col items-end gap-3 w-full md:flex-1">
            {showKidSelector && (
              <Card className="w-full md:max-w-[900px] shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                <CardContent className="p-4">
                  <div className="grid grid-cols-1 gap-4">
                    <div>
                      <Label className="block text-sm mb-1">Elegí el hijo/a</Label>
                      <Select
                        value={selectedKid}
                        onValueChange={onChangeKid}
                        disabled={!hijosLoaded || !hasHijos}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue
                            placeholder={
                              hijosLoaded ? (hasHijos ? "Seleccionar" : "Sin hijos") : "Cargando…"
                            }
                          />
                        </SelectTrigger>
                        {hasHijos && (
                          <SelectContent>
                            {hijos.map((h) => {
                              const v = kidValue(h)
                              if (!v) return null
                              return (
                                <SelectItem key={v} value={v}>
                                  {kidLabel(h)}
                                </SelectItem>
                              )
                            })}
                          </SelectContent>
                        )}
                      </Select>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {meLoaded && !hidePadreNavAndMessage && !isAlumno && (
              <div className="flex items-center gap-2">
                <ComposeMensajeAlumno
                  cursoSugerido={searchParams.get("curso") || cursoAlumno || ""}
                  // ✅ NUEVO: identificadores y nombre para preseleccionar destinatario
                  alumnoPk={pk}
                  alumnoCode={code}
                  alumnoNombre={nombreAlumno}
                  onSent={() => {
                    try {
                      // ✅ NUEVO: evento unificado + legacy
                      window.dispatchEvent(new Event(INBOX_EVENT))
                      window.dispatchEvent(new Event("inbox-changed"))
                    } catch {}
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {/* ===== Tarjetas resumen (clickeables) ===== */}
        <div className="grid md:grid-cols-3 gap-4">
          <Card
            onClick={() => setActiveSection("notas")}
            className={[
              "border-0 shadow-sm cursor-pointer transition-all",
              activeSection === "notas"
                ? "ring-2 ring-blue-500 bg-blue-50"
                : "hover:bg-blue-50/70",
            ].join(" ")}
          >
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                  <ClipboardList className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <div className="text-xl font-semibold text-gray-900">Notas</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card
            onClick={() => setActiveSection("sanciones")}
            className={[
              "border-0 shadow-sm cursor-pointer transition-all",
              activeSection === "sanciones"
                ? "ring-2 ring-amber-500 bg-amber-50"
                : "hover:bg-amber-50/70",
            ].join(" ")}
          >
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                  <Gavel className="w-5 h-5 text-amber-700" />
                </div>
                <div>
                  <div className="text-xl font-semibold text-gray-900">Sanciones</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card
            onClick={() => setActiveSection("asistencias")}
            className={[
              "border-0 shadow-sm cursor-pointer transition-all",
              activeSection === "asistencias"
                ? "ring-2 ring-emerald-500 bg-emerald-50"
                : "hover:bg-emerald-50/70",
            ].join(" ")}
          >
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center">
                  <CalendarDays className="w-5 h-5 text-emerald-700" />
                </div>
                <div>
                  <div className="text-xl font-semibold text-gray-900">
                    Inasistencias
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {!loading && !error && !activeSection && (
          <p className="text-sm text-gray-500">
            Seleccioná una de las tarjetas de arriba para ver el detalle.
          </p>
        )}

        {error ? (
          <div className="p-4 bg-red-50 text-red-700 rounded-lg border border-red-200">
            {error}
          </div>
        ) : loading ? (
          <div className="text-sm text-gray-600">Cargando información del alumno…</div>
        ) : (
          <>
            {/* ===== Sección: Notas ===== */}
            {activeSection === "notas" && (
              <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                <CardContent className="p-6">
                  <div className="flex items-start justify-between gap-4 mb-4">
                    <div className="flex items-start gap-4">
                      <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <ClipboardList className="h-6 w-6 text-blue-600" />
                      </div>
                      <div className="flex-1">
                        <h3 className="tile-title">Notas</h3>
                        <p className="tile-subtitle">
                          Calificaciones registradas por materia
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Filtros de notas */}
                  <div className="mb-4 grid grid-cols-1 sm:grid-cols-4 gap-3">
                    <div>
                      <Label htmlFor="filMateria" className="text-xs text-gray-600">
                        Materia
                      </Label>
                      <select
                        id="filMateria"
                        className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                        value={filMateria}
                        onChange={(e) => setFilMateria(e.target.value)}
                      >
                        <option value="ALL">Todas</option>
                        {materiasCat.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <Label htmlFor="filCuatr" className="text-xs text-gray-600">
                        Cuatrimestre
                      </Label>
                      <select
                        id="filCuatr"
                        className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                        value={filCuatr}
                        onChange={(e) => setFilCuatr(e.target.value)}
                      >
                        <option value="ALL">Todos</option>
                        <option value="1">1</option>
                        <option value="2">2</option>
                      </select>
                    </div>

                    <div>
                      <Label htmlFor="filTipo" className="text-xs text-gray-600">
                        Tipo
                      </Label>
                      <select
                        id="filTipo"
                        className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                        value={filTipo}
                        onChange={(e) => setFilTipo(e.target.value)}
                      >
                        <option value="ALL">Todos</option>
                        <option value="Examen">Examen</option>
                        <option value="Trabajo Práctico">Trabajo Práctico</option>
                        <option value="Participación">Participación</option>
                        <option value="Tarea">Tarea</option>
                      </select>
                    </div>

                    <div>
                      <Label htmlFor="buscar" className="text-xs text-gray-600">
                        Buscar
                      </Label>
                      <input
                        id="buscar"
                        className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                        placeholder="Materia, nota, comentario…"
                        value={buscar}
                        onChange={(e) => setBuscar(e.target.value)}
                      />
                    </div>
                  </div>

                  {/* Tabla de notas */}
                  {notasFiltradas.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      No se encontraron notas con los filtros actuales.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead>
                          <tr className="text-left text-gray-600 border-b">
                            <th className="py-2 pr-4">Fecha</th>
                            <th className="py-2 pr-4">Materia</th>
                            <th className="py-2 pr-4">Cuatrimestre</th>
                            <th className="py-2 pr-4">Tipo</th>
                            <th className="py-2 pr-4">Calificación</th>
                            <th className="py-2 pr-4">Comentarios</th>
                          </tr>
                        </thead>
                        <tbody>
                          {notasFiltradas.map((n, i) => {
                            const cuatr = notaCuatr(n)
                            return (
                              <tr key={n.id || i} className="border-b last:border-b-0">
                                <td className="py-2 pr-4">
                                  {fmtFecha(n.fecha || n.created_at)}
                                </td>
                                <td className="py-2 pr-4">{n.materia || "—"}</td>
                                <td className="py-2 pr-4">{cuatr ?? "—"}</td>
                                <td className="py-2 pr-4">{n.tipo || "—"}</td>
                                <td className="py-2 pr-4">
                                  <span className="inline-flex items-center px-2 py-0.5 rounded bg-blue-100 text-blue-700">
                                    {toNumberOrText(n.calificacion)}
                                  </span>
                                </td>
                                <td className="py-2 pr-4">
                                  {n.observaciones || n.comentarios || "—"}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* ===== Sección: Sanciones ===== */}
            {activeSection === "sanciones" && (
              <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                <CardContent className="p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-12 h-12 bg-amber-100 rounded-lg flex items-center justify-center">
                      <Gavel className="h-6 w-6 text-amber-700" />
                    </div>
                    <div>
                      <h3 className="tile-title">Sanciones</h3>
                      <p className="tile-subtitle">Historial disciplinario del alumno</p>
                    </div>
                  </div>

                  {/* Filtros de sanciones */}
                  <div className="mb-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <Label className="text-xs text-gray-600">Mes</Label>
                      <select
                        className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                        value={filSancionMes}
                        onChange={(e) => setFilSancionMes(e.target.value)}
                      >
                        <option value="ALL">Todos</option>
                        {mesesSancionesDisponibles.map((m) => (
                          <option key={m.key} value={m.key}>
                            {m.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <Label className="text-xs text-gray-600">Docente</Label>
                      <select
                        className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                        value={filSancionDocente}
                        onChange={(e) => setFilSancionDocente(e.target.value)}
                      >
                        <option value="ALL">Todos</option>
                        {docentesSancionesDisponibles.map((d) => (
                          <option key={d} value={d}>
                            {d}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <Label className="text-xs text-gray-600">Buscar</Label>
                      <input
                        className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                        placeholder="Motivo o docente..."
                        value={buscarSanc}
                        onChange={(e) => setBuscarSanc(e.target.value)}
                      />
                    </div>
                  </div>
                  {sancionesFiltradas.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      No hay sanciones registradas.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full table-fixed text-sm">
                        <colgroup>
                          <col className="w-[18%]" />
                          <col className="w-[56%]" />
                          <col className="w-[26%]" />
                        </colgroup>
                        <thead>
                          <tr className="text-left text-gray-600 border-b">
                            <th className="py-2 pr-4">Fecha</th>
                            <th className="py-2 pr-4">Motivo</th>
                            <th className="py-2 pr-4">Docente</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sancionesFiltradas.map((s, i) => (
                            <tr key={s.id || i} className="border-b last:border-b-0">
                              <td className="py-2 pr-4">
                                {fmtFecha(s.fecha || s.created_at)}
                              </td>
                              <td className="py-2 pr-4 break-words">
                                {s.motivo || s.detalle || s.descripcion || "-"}
                              </td>
                              <td className="py-2 pr-4">
                                {s.docente || s.creado_por || "-"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* ===== Sección: Asistencias ===== */}
            {activeSection === "asistencias" && (
              <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                <CardContent className="p-6">
                  {/* ✅ header con filtros a la derecha */}
                  <div className="flex items-start justify-between gap-4 mb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 bg-emerald-100 rounded-lg flex items-center justify-center">
                        <CalendarDays className="h-6 w-6 text-emerald-700" />
                      </div>
                      <div>
                        <h3 className="tile-title">Asistencias</h3>
                        <p className="tile-subtitle">
                          {asistencias.length === 0 ? "(Próximamente)" : ""}
                        </p>
                      </div>
                    </div>

                    {/* ✅ NUEVO: filtros mes + tipo */}
                    {asistencias.length > 0 && (
                      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end">
                        <div className="min-w-[180px]">
                          <Label className="text-xs text-gray-600">Mes</Label>
                          <select
                            className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                            value={filAsisMes}
                            onChange={(e) => setFilAsisMes(e.target.value)}
                          >
                            <option value="ALL">Todos</option>
                            {mesesDisponibles.map((m) => (
                              <option key={m.key} value={m.key}>
                                {m.label}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="min-w-[200px]">
                          <Label className="text-xs text-gray-600">Asistencia</Label>
                          <select
                            className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                            value={filAsisTipo}
                            onChange={(e) => setFilAsisTipo(e.target.value)}
                          >
                            <option value="ALL">Todas</option>
                            <option value="clases">Clases</option>
                            <option value="informatica">Informática</option>
                            <option value="catequesis">Catequesis</option>
                          </select>
                        </div>
                      </div>
                    )}
                  </div>

                  {asistencias.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      Aún no hay asistencias cargadas para este alumno o la API de
                      asistencias no está habilitada.
                    </div>
                  ) : asistenciasFiltradas.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      No hay asistencias para los filtros seleccionados.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full table-fixed text-sm">
                        <colgroup>
                          <col className="w-[18%]" />
                          <col className="w-[14%]" />
                          <col className="w-[12%]" />
                          <col className="w-[16%]" />
                          <col className="w-[40%]" />
                        </colgroup>
                        <thead>
                          <tr className="text-left text-gray-600 border-b">
                            <th className="py-2 pr-4">Fecha</th>
                            <th className="py-2 pr-4">Asistencia</th>
                            <th className="py-2 pr-4">Estado</th>
                            <th className="py-2 pr-4">Justificada</th>
                            <th className="py-2 pr-4">Detalle</th>
                          </tr>
                        </thead>
                        <tbody>
                          {asistenciasFiltradas.map((a, i) => {
                            const tipoRaw = asistenciaTipoFromAny(a)
                            const tipoNorm = normalizeAsistenciaTipo(tipoRaw) || "clases"
                            const rowId = getAsistenciaId(a) || `${i}`
                            const est = estadoTexto(asistenciaEstadoFromAny(a))
                            const puedeDetalle =
                              canJustifyAsistencias &&
                              (est === "Ausente" || est === "Tarde")
                            const detalleTexto =
                              a.detalle || a.observaciones || a.observacion || ""

                            return (
                              <tr key={rowId} className="border-b last:border-b-0">
                                <td className="py-2 pr-4">
                                  {fmtFecha(a.fecha || a.created_at)}
                                </td>
                                <td className="py-2 pr-4">
                                  <span className="inline-flex items-center px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                                    {asistenciaTipoLabel(tipoNorm)}
                                  </span>
                                </td>
                                <td className="py-2 pr-4">{est}</td>
                                <td className="py-2 pr-4">
                                  {(() => {
                                    const can = est === "Ausente" || est === "Tarde"
                                    if (!can) return "—"
                                    const just = isJustificadaFromAny(a)
                                    const asistenciaId = getAsistenciaId(a)

                                    // 🔒 Solo el preceptor (o admin) puede justificar.
                                    if (!canJustifyAsistencias) {
                                      if (just) {
                                        return (
                                          <span className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-emerald-300 bg-emerald-50 text-emerald-800">
                                            Justificada
                                          </span>
                                        )
                                      }
                                      return "—"
                                    }

                                    return (
                                      <button
                                        type="button"
                                        onClick={async () => {
                                          const r = await toggleJustificada(
                                            asistenciaId,
                                            !just
                                          )
                                          if (!r.ok) {
                                            alert(
                                              r.data?.detail ||
                                                `Error (HTTP ${r.status || "?"})`
                                            )
                                            return
                                          }

                                          setAsistencias((prev) => {
                                            const list = Array.isArray(prev) ? prev : []
                                            return list.map((x) => {
                                              const xid = getAsistenciaId(x)
                                              if (String(xid) !== String(asistenciaId))
                                                return x
                                              return {
                                                ...x,
                                                justificada:
                                                  r.data?.justificada ?? !just,
                                                falta_valor:
                                                  r.data?.falta_valor ?? x.falta_valor,
                                              }
                                            })
                                          })
                                        }}
                                        className={
                                          just
                                            ? "inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                                            : "inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-gray-300 bg-white text-gray-800 hover:bg-gray-50"
                                        }
                                      >
                                        {just ? "Justificada" : "Justificar"}
                                      </button>
                                    )
})()}
                                </td>
                                <td className="py-2 pr-4">
                                  <div className="flex items-start gap-2">
                                    <span
                                      className={`min-w-0 flex-1 break-words ${
                                        detalleTexto ? "text-gray-900" : "text-gray-400"
                                      }`}
                                    >
                                      {detalleTexto || "—"}
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => openDetalleModal(a)}
                                      className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-gray-200 text-gray-600 hover:border-blue-200 hover:text-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
                                      title="Agregar/editar detalle"
                                      disabled={!puedeDetalle}
                                    >
                                      <Pencil className="h-4 w-4" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}

                  <div className="mt-4 flex items-center justify-end">
                    <div className="text-xl font-semibold text-gray-900">
                      <span>Total inasistencias:</span>{" "}
                      {formatFaltas(totalInasistencias)}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>

      <Dialog
        open={detalleModal.open}
        onOpenChange={(open) => (!open ? closeDetalleModal() : null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Detalle de la asistencia</DialogTitle>
            <DialogDescription>
              {detalleModal.label || "Agrega un detalle para la asistencia seleccionada."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Detalle</Label>
            <Textarea
              value={detalleModal.value}
              onChange={(e) =>
                setDetalleModal((prev) => ({ ...prev, value: e.target.value }))
              }
              className="min-h-[140px]"
              placeholder="Ej: justifico la inasistencia por control medico"
            />
            {detalleModal.error && (
              <p className="text-sm text-red-600">{detalleModal.error}</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeDetalleModal}>
              Cancelar
            </Button>
            <Button onClick={handleGuardarDetalle} disabled={detalleModal.saving}>
              {detalleModal.saving ? "Guardando..." : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* ======================== Subcomponentes ======================== */

function Topbar({
  title = "Perfil del alumno",
  userLabel,
  unreadCount,
  backToAlumnosHref,
  onBackToAlumnos,
  showBackAlumnos = true,
  showBackCursos = true,
}) {
  return (
    <div className="bg-blue-600 text-white px-6 py-4">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="inline-flex">
            <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center overflow-hidden">
              <img
                src={LOGO_SRC}
                alt="Escuela Santa Teresa"
                className="h-full w-full object-contain"
              />
            </div>
          </Link>
          <h1 className="text-xl font-semibold">{title}</h1>
        </div>

        <div className="flex items-center gap-2">
          {/* Volver a alumnos */}
          {showBackAlumnos && (
            <Button
              type="button"
              variant="ghost"
              onClick={onBackToAlumnos}
              className="text-white hover:bg-blue-700 gap-2"
            >
              <ChevronLeft className="h-4 w-4" />
              {backToAlumnosHref ? "Volver a alumnos" : "Volver"}
            </Button>
          )}

          {/* Volver a cursos */}
          {showBackCursos && (
            <Link href="/gestion_alumnos" prefetch>
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <ChevronLeft className="h-4 w-4" />
                Volver a cursos
              </Button>
            </Link>
          )}

          {/* Volver al panel: siempre */}
          <Link href="/dashboard" prefetch>
            <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
              <ChevronLeft className="h-4 w-4" />
              Volver al panel
            </Button>
          </Link>

          <NotificationBell unreadCount={unreadCount} />

          <div className="relative">
            <Link href="/mensajes" prefetch>
              <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
                <Mail className="h-5 w-5" />
              </Button>
            </Link>
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 text-[10px] leading-none px-1.5 py-0.5 rounded-full bg-red-600 text-white border border-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <UserIcon className="h-4 w-4" />
                {userLabel}
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem asChild>
                <Link href="/perfil">
                  <div className="flex items-center">
                    <UserIcon className="h-4 w-4 mr-2" />
                    Perfil
                  </div>
                </Link>
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => {
                  try {
                    localStorage.clear()
                  } catch {}
                  window.location.href = "/login"
                }}
              >
                <span className="h-4 w-4 mr-2">🚪</span>
                Cerrar sesión
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  )
}
