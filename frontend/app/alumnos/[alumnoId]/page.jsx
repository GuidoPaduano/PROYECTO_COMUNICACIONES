"use client"

import dynamic from "next/dynamic"
import Link from "next/link"
import {
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { useSearchParams, useRouter, useParams } from "next/navigation"
import { getSessionProfile, useAuthGuard, authFetch, useSessionContext } from "../../_lib/auth"
import { getCourseDisplayName } from "../../_lib/courses"
import { INBOX_EVENT } from "../../_lib/inbox" // ✅ NUEVO: evento unificado inbox
import { useUnreadMessages } from "../../_lib/useUnreadMessages"
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
  Download,
  Loader2,
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
import { NotificationBell } from "@/components/notification-bell"

const ComposeMensajeAlumno = dynamic(() => import("./_compose-alumno"), {
  loading: () => null,
})
const TransferAlumno = dynamic(() => import("./_transfer-alumno"), {
  loading: () => null,
})

const LOGO_SRC = "/imagenes/Logo%20Color.png"

/* ======================== Fix Mis Hijos: persistencia tab ======================== */
const MIS_HIJOS_LAST_TAB_KEY = "mis_hijos_last_tab"
const MIS_HIJOS_LAST_ALUMNO_KEY = "mis_hijos_last_alumno"
const VALID_TABS = new Set(["notas", "sanciones", "asistencias"])
const ALUMNO_DETAIL_CACHE_PREFIX = "alumno_detail_cache:"
const ALUMNO_DETAIL_CACHE_TTL_MS = 5 * 60 * 1000
const ALUMNO_DATA_CACHE_TTL_MS = 5 * 60 * 1000
const NOTAS_CACHE_PREFIX = "alumno_notas_cache:"
const SANCIONES_CACHE_PREFIX = "alumno_sanciones_cache:"
const ASISTENCIAS_CACHE_PREFIX = "alumno_asistencias_cache:"
const ALUMNO_RESOURCE_MAX_AGE_MS = 30000
const NOTA_TIPOS = ["Examen", "Trabajo Práctico", "Participación", "Tarea"]
const NOTA_RESULTADOS = [
  { value: "TEA", label: "TEA" },
  { value: "TEP", label: "TEP" },
  { value: "TED", label: "TED" },
]

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

function getCachedList(prefix, idParam) {
  if (!idParam) return { data: null, fresh: false }
  const cached = safeGetLSJson(`${prefix}${idParam}`)
  if (!cached?.data) return { data: null, fresh: false }
  if (cached.ts && Date.now() - cached.ts > ALUMNO_DATA_CACHE_TTL_MS) {
    return { data: cached.data, fresh: false }
  }
  return { data: cached.data, fresh: true }
}

function setCachedList(prefix, idParam, data) {
  if (!idParam || !data) return
  safeSetLSJson(`${prefix}${idParam}`, {
    ts: Date.now(),
    data,
  })
}

const alumnoResourceCache = new Map()
const alumnoResourcePromises = new Map()

function invalidateAlumnoResource(cacheKeyPrefix = "") {
  const prefix = String(cacheKeyPrefix || "").trim()
  if (!prefix) return
  for (const key of Array.from(alumnoResourceCache.keys())) {
    if (key.startsWith(prefix)) {
      alumnoResourceCache.delete(key)
    }
  }
  for (const key of Array.from(alumnoResourcePromises.keys())) {
    if (key.startsWith(prefix)) {
      alumnoResourcePromises.delete(key)
    }
  }
}

async function loadAlumnoResource(
  cacheKey,
  loader,
  { force = false, maxAgeMs = ALUMNO_RESOURCE_MAX_AGE_MS } = {}
) {
  const key = String(cacheKey || "").trim()
  if (!key || typeof loader !== "function") {
    return await loader()
  }

  if (force) {
    invalidateAlumnoResource(key)
  }

  const cached = alumnoResourceCache.get(key)
  if (cached && cached.expiresAt > Date.now()) {
    return cached.data
  }

  if (alumnoResourcePromises.has(key)) {
    return await alumnoResourcePromises.get(key)
  }

  const promise = (async () => {
    const data = await loader()
    alumnoResourceCache.set(key, {
      data,
      expiresAt: Date.now() + maxAgeMs,
    })
    return data
  })()

  alumnoResourcePromises.set(key, promise)

  try {
    return await promise
  } finally {
    if (alumnoResourcePromises.get(key) === promise) {
      alumnoResourcePromises.delete(key)
    }
  }
}

function runIdle(cb, timeout = 800) {
  if (typeof window === "undefined") return setTimeout(cb, timeout)
  if ("requestIdleCallback" in window) {
    return window.requestIdleCallback(cb, { timeout })
  }
  return setTimeout(cb, timeout)
}

function cancelIdle(id) {
  if (typeof window === "undefined") return clearTimeout(id)
  if ("cancelIdleCallback" in window) {
    return window.cancelIdleCallback(id)
  }
  return clearTimeout(id)
}

function kidLegajo(h) {
  return h?.id_alumno ?? h?.alumno_id ?? h?.legajo ?? null
}

function kidPk(h) {
  return h?.id ?? h?.pk ?? null
}

function kidValue(h) {
  const pk = kidPk(h)
  const leg = kidLegajo(h)
  const v = pk != null && String(pk) !== "" ? pk : leg
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
  const courseLabel = getCourseDisplayName(h)
  const curso = courseLabel ? ` — ${courseLabel}` : ""
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
  if (!s) return "" // vacio -> luego se trata como "clases" donde corresponda

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

async function getAlumnoIdsFromAny(idParam) {
  const encoded = encodeURIComponent(idParam)
  try {
    const r = await fetchJSON(`/api/alumnos/${encoded}/`)
    if (r.ok) {
      const obj = r.data || {}
      const pk = obj?.id
      const code = obj?.id_alumno ?? idParam
      if (pk || code) {
        return { detail: obj, pk, code }
      }
    }
  } catch {}
  return { detail: null, pk: null, code: idParam }
}

/** Notas por PK o por id_alumno (ambas rutas soportadas) */
async function getNotasByPkOrCode(pk, code) {
  const codeEnc = code != null ? encodeURIComponent(String(code)) : null
  const pkStr = pk != null ? encodeURIComponent(String(pk)) : null
  const tries = [
    pkStr && `/api/notas/?alumno=${pkStr}`,
    pkStr && `/api/notas/?alumno_id=${pkStr}`,
    codeEnc && `/api/notas/?id_alumno=${codeEnc}`,
    pk && `/api/alumnos/${pk}/notas/`,
  ].filter(Boolean)

  let fallback = null
  for (const url of tries) {
    try {
      const r = await fetchJSON(url)
      if (!r.ok) continue
      const arr = r.data?.notas || []
      if (!Array.isArray(arr)) continue
      if (arr.length > 0) return arr
      if (fallback === null) fallback = arr
    } catch {}
  }
  return Array.isArray(fallback) ? fallback : []
}

/** Sanciones por PK o id_alumno */
async function getSancionesByPkOrCode(pk, code) {
  const tries = [
    code && `/api/sanciones/?id_alumno=${encodeURIComponent(code)}`,
    pk && `/api/sanciones/?alumno=${pk}`,
  ].filter(Boolean)

  for (const url of tries) {
    try {
      const r = await fetchJSON(url)
      if (!r.ok) continue
      const arr = r.data?.results || []
      if (Array.isArray(arr)) return arr
    } catch {}
  }
  return []
}

/** Asistencias por PK o id_alumno */
async function getAsistenciasByPkOrCode(pk, code) {
  const pkStr = String(pk ?? "").trim()
  const codeSafe = String(code ?? "").trim()

  const tries = [
    codeSafe && `/api/asistencias/?id_alumno=${encodeURIComponent(codeSafe)}`,
    pkStr && `/api/asistencias/?alumno=${pkStr}`,
  ].filter(Boolean)

  for (const url of tries) {
    try {
      const r = await fetchJSON(url)
      if (!r.ok) continue
      const arr = r.data?.results || []
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

  const url = `/api/asistencias/${encodeURIComponent(id)}/justificar/`

  const methods = ["POST", "PATCH", "PUT"]
  let last = { ok: false, status: 500, data: { detail: "No se pudo justificar." } }

  for (const method of methods) {
    try {
      const r = await fetchJSON(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ justificada: nextValue }),
      })
      if (r.ok) return r
      last = r
      if (r.status === 404 || r.status === 405) continue
      return r
    } catch {
      // seguimos probando el próximo método
    }
  }

  return last
}

async function firmarAsistencia(asistenciaId) {
  const id = String(asistenciaId ?? "").trim()
  if (!id) {
    return { ok: false, status: 0, data: { detail: "Sin ID de asistencia." } }
  }

  const url = `/api/asistencias/${encodeURIComponent(id)}/firmar/`
  const methods = ["POST", "PATCH"]
  let last = { ok: false, status: 500, data: { detail: "No se pudo firmar la inasistencia." } }

  for (const method of methods) {
    try {
      const r = await fetchJSON(url, { method })
      if (r.ok) return r
      last = r
      if (r.status === 404 || r.status === 405) continue
      return r
    } catch {}
  }

  return last
}

async function firmarSancion(sancionId) {
  const id = String(sancionId ?? "").trim()
  if (!id) {
    return { ok: false, status: 0, data: { detail: "Sin ID de sanción." } }
  }

  const url = `/api/sanciones/${encodeURIComponent(id)}/firmar/`
  const methods = ["POST", "PATCH"]
  let last = { ok: false, status: 500, data: { detail: "No se pudo firmar la sanción." } }

  for (const method of methods) {
    try {
      const r = await fetchJSON(url, { method })
      if (r.ok) return r
      last = r
      if (r.status === 404 || r.status === 405) continue
      return r
    } catch {}
  }

  return last
}

async function firmarNota(notaId) {
  const id = String(notaId ?? "").trim()
  if (!id) {
    return { ok: false, status: 0, data: { detail: "Sin ID de nota." } }
  }

  const url = `/api/notas/${encodeURIComponent(id)}/firmar/`
  const methods = ["POST", "PATCH"]
  let last = { ok: false, status: 500, data: { detail: "No se pudo firmar la nota." } }

  for (const method of methods) {
    try {
      const r = await fetchJSON(url, { method })
      if (r.ok) return r
      last = r
      if (r.status === 404 || r.status === 405) continue
      return r
    } catch {}
  }

  return last
}

async function updateDetalleAsistencia(asistenciaId, detalle) {
  const id = String(asistenciaId ?? "").trim()
  if (!id) {
    return { ok: false, status: 0, data: { detail: "Sin ID de asistencia." } }
  }

  const url = `/api/asistencias/${encodeURIComponent(id)}/detalle/`
  const methods = ["PATCH", "POST", "PUT"]
  let last = { ok: false, status: 500, data: { detail: "No se pudo guardar el detalle." } }

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

function fmtFechaHora(iso) {
  if (!iso) return "—"
  try {
    const d = new Date(String(iso))
    if (Number.isNaN(d.getTime())) return String(iso)
    return d.toLocaleString("es-AR", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return String(iso)
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

  // Variante historica: inasistente (invertido)
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

function isFirmadaFromAny(item) {
  if (!item || typeof item !== "object") return false
  return Boolean(
    item.firmada ??
      item.firmado ??
      item.signed ??
      item.is_firmada ??
      item.isFirmada ??
      false
  )
}

function isAsistenciaFirmable(item) {
  const estado = estadoTexto(asistenciaEstadoFromAny(item))
  return estado === "Ausente" || estado === "Tarde"
}

function normalizeNotaNumericaInput(value) {
  return String(value ?? "").replace(",", ".")
}

/* ------------------------------------------------------------
   Página: PERFIL del alumno (Resumen + Notas + Sanciones + Asistencias)
------------------------------------------------------------ */
export default function AlumnoPerfilPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center">
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
  const session = useSessionContext()

  // ✅ FIX Next: params ahora es Promise -> en Client Component usamos useParams()
  const routeParams = useParams() || {}
  const alumnoid =
    routeParams?.alumnoId ?? routeParams?.alumnoid ?? routeParams?.id ?? ""

  const searchParams = useSearchParams()
  const router = useRouter()

  const [me, setMe] = useState(null)
  const alumnoPageScopeKey = useMemo(
    () => `${session?.username || "anon"}:${session?.school?.id || "default"}`,
    [session?.school?.id, session?.username]
  )
  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || ""),
    [me]
  )

  const unreadCount = useUnreadMessages()

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
  const notasRef = useRef([])
  const sancionesRef = useRef([])
  const asistenciasRef = useRef([])

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
  const [notaModal, setNotaModal] = useState({
    open: false,
    notaId: null,
    materia: "",
    tipo: "",
    resultado: "",
    nota_numerica: "",
    cuatrimestre: "1",
    fecha: "",
    observaciones: "",
    error: "",
    saving: false,
  })
  const [savingNotaId, setSavingNotaId] = useState(null)
  const [signingNotaId, setSigningNotaId] = useState(null)
  const [signingAllNotas, setSigningAllNotas] = useState(false)
  const [confirmFirmarTodoOpen, setConfirmFirmarTodoOpen] = useState(false)
  const [signingSancionId, setSigningSancionId] = useState(null)
  const [signingAllSanciones, setSigningAllSanciones] = useState(false)
  const [confirmFirmarSancionesOpen, setConfirmFirmarSancionesOpen] = useState(false)
  const [signingAsistenciaId, setSigningAsistenciaId] = useState(null)
  const [signingAllAsistencias, setSigningAllAsistencias] = useState(false)
  const [confirmFirmarAsistenciasOpen, setConfirmFirmarAsistenciasOpen] = useState(false)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [downloadingPdf, setDownloadingPdf] = useState(false)
  const [downloadingSancionesPdf, setDownloadingSancionesPdf] = useState(false)
  const [downloadingAsistenciasPdf, setDownloadingAsistenciasPdf] = useState(false)
  const [loadingNotas, setLoadingNotas] = useState(false)
  const [loadingSanciones, setLoadingSanciones] = useState(false)
  const [loadingAsistencias, setLoadingAsistencias] = useState(false)

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

  // Perfil
  useEffect(() => {
    let alive = true

    ;(async () => {
      try {
        if (
          Array.isArray(session?.groups) &&
          (session.groups.length > 0 || session?.isSuperuser)
        ) {
          const contextMe = {
            full_name: session.userLabel || session.username || "",
            username: session.username || "",
            groups: session.groups,
            rol: session.role || "",
            is_superuser: !!session.isSuperuser,
          }
          if (alive) setMe(contextMe)
          return
        }

        const who = await getSessionProfile()
        if (alive) setMe(who)
      } catch {}
    })()

    return () => {
      alive = false
    }
  }, [session])

  // Carga detalle -> pk/code -> (notas, sanciones, asistencias)
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError("")
    setNotas([])
    setSanciones([])
    setAsistencias([])
    setLoadingNotas(false)
    setLoadingSanciones(false)
    setLoadingAsistencias(false)
    // ✅ reset filtros asistencia al cambiar de alumno
    setFilAsisMes("ALL")
    setFilAsisTipo("ALL")

    const cachedDetail = getCachedAlumnoDetail(alumnoid)
    if (cachedDetail && alive) {
      const cachedPk = cachedDetail?.id ?? null
      const cachedCode =
        cachedDetail?.id_alumno ??
        cachedDetail?.legajo ??
        cachedDetail?.codigo ??
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
        const d = await loadAlumnoResource(
          `alumno-materias:${alumnoPageScopeKey}`,
          async () => {
            const r = await fetchJSON("/notas/catalogos/")
            if (!r.ok) throw new Error("No se pudo cargar el catálogo de materias.")
            return r.data || {}
          }
        )
        if (!alive) return
        const materias = d.materias || d.MATERIAS || []
        setMateriasCat(Array.isArray(materias) ? materias : [])
      } catch {}
    })()
    return () => {
      alive = false
    }
  }, [alumnoPageScopeKey])

  // Curso sugerido para el modal de “Enviar mensaje”
  const cursoParam = searchParams.get("curso")
  const schoolCourseParam = searchParams.get("school_course_id")
  const fromParam = searchParams.get("from")

  /* ====================== FIX: tab por URL + persistencia para /mis-hijos ====================== */
  const initialTabParam = String(searchParams.get("tab") || "").toLowerCase().trim()
  const initialFromParam = String(searchParams.get("from") || "").trim()
  const [tabParamRaw, setTabParamRaw] = useState(initialTabParam)
  const [fromParamRaw, setFromParamRaw] = useState(initialFromParam)
  const tabFromUrl = VALID_TABS.has(tabParamRaw) ? tabParamRaw : ""
  const fromParamEffective = String(fromParamRaw || fromParam || "").trim()
  const isAlumnoMenuNav =
    fromParamEffective === "mis-notas" ||
    fromParamEffective === "mis-sanciones" ||
    fromParamEffective === "mis-asistencias"

  // 👇 acá detectamos si venimos de /mis-notas
  const isMisNotas = fromParamEffective === "mis-notas"

  // ✅ PADRE: ocultar acciones de navegación y “Enviar mensaje”
  const isFromMisHijos =
    fromParamEffective === "/mis-hijos" || fromParamEffective === "mis-hijos"
  const rawGroups = Array.isArray(me?.groups)
    ? me.groups
    : []
  const groupNames = rawGroups
    .map((g) => (typeof g === "string" ? g : g?.name || g?.nombre || ""))
    .filter(Boolean)
  const groupSet = new Set(groupNames.map((g) => String(g).toLowerCase()))
  const hasGroup = (name) => groupSet.has(String(name).toLowerCase())
  const isPadre = (hasGroup("padres") || hasGroup("padre")) && !me?.is_superuser
  const isAlumno = (hasGroup("alumnos") || hasGroup("alumno")) && !me?.is_superuser
  const isPreceptor = hasGroup("preceptores") || hasGroup("preceptor")
  const isDirectivo = hasGroup("directivos") || hasGroup("directivo")
  const canEditNotas = !!me && (me?.is_superuser || hasGroup("profesores") || hasGroup("profesor"))
  const canJustifyAsistencias =
    !!me && (me?.is_superuser || isPreceptor || isDirectivo)
  const canSignByPadre = !!me && (me?.is_superuser || isPadre)
  const canEditAsistenciaDetalle =
    !!me && (me?.is_superuser || isPreceptor || isDirectivo)
  const canViewFirmaEstado =
    !!me && (me?.is_superuser || isPreceptor || isDirectivo || isPadre)
  const canTransferAlumno =
    !!me && (me?.is_superuser || isPreceptor || isDirectivo)
  const meLoaded = !!me
  const rolesReady = meLoaded
  const hidePadreNavAndMessage = isFromMisHijos || isPadre
  const showKidSelector = hidePadreNavAndMessage
  const hasHijos = hijos.length > 0
  const shouldHideAlumnoContent = isAlumnoMenuNav && !tabFromUrl
  const activeSectionLower = String(activeSection || "").toLowerCase().trim()
  const alumnoTab = VALID_TABS.has(tabFromUrl)
    ? tabFromUrl
    : VALID_TABS.has(activeSectionLower)
    ? activeSectionLower
    : "notas"

  // ✅ título dinámico del header (padre vs alumno)
  const topbarTitle = "Perfil de Alumno"

  // ✅ Carga de hijos (solo PADRE /mis-hijos) para poder cambiar de hijo sin salir del perfil
  useEffect(() => {
    if (!showKidSelector) return
    let alive = true

    ;(async () => {
      setHijosLoaded(false)
      try {
        const data = await loadAlumnoResource(
          `alumno-mis-hijos:${alumnoPageScopeKey}`,
          async () => {
            const r = await fetchJSON("/api/padres/mis-hijos/")
            if (!r.ok) throw new Error("No se pudieron cargar los hijos asociados.")
            return r.data || {}
          }
        )

        const arr = data?.results || []

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
  }, [showKidSelector, alumnoid, code, pk, alumnoPageScopeKey])

  // ✅ Persistimos "último hijo visto" aunque todavía no haya cargado el listado
  useEffect(() => {
    if (!showKidSelector) return
    const currentPk = pk != null ? String(pk).trim() : ""
    const currentCode = String(code || "").trim()
    const currentRoute = String(alumnoid || "").trim()
    const v = String(selectedKid || currentPk || currentCode || currentRoute || "").trim()
    if (!v) return
    safeSetLS(MIS_HIJOS_LAST_ALUMNO_KEY, v)
  }, [showKidSelector, selectedKid, pk, code, alumnoid])

  function onChangeKid(v) {
    const next = String(v || "").trim()
    if (!next) return
    if (next === String(selectedKid || "").trim()) return
    const currentId = String(alumnoid || "").trim()
    const currentCode = String(code || "").trim()
    const currentPk = pk != null ? String(pk).trim() : ""
    if (next === currentId || next === currentCode || next === currentPk) return

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

    const target = `/alumnos/${encodeURIComponent(next)}?${qs.toString()}`
    try {
      if (typeof window !== "undefined") {
        const current = `${window.location.pathname}${window.location.search}`
        if (current === target) return
      }
    } catch {}
    router.push(target)
  }

  // Reconstrucción del "volver a alumnos"
  const backToAlumnosHref = useMemo(() => {
    if (fromParamEffective && fromParamEffective !== "mis-notas") return fromParamEffective
    const schoolCourseId =
      schoolCourseParam ??
      alumnoDetail?.school_course_id ??
      (/^\d+$/.test(String(cursoParam || "").trim()) ? cursoParam : null)
    if (schoolCourseId != null && String(schoolCourseId).trim() !== "") {
      return `/alumnos/curso/${encodeURIComponent(String(schoolCourseId))}`
    }
    return "/alumnos"
  }, [fromParamEffective, schoolCourseParam, cursoParam, alumnoDetail])

  // Handler robusto
  function handleBackToAlumnos() {
    const target = backToAlumnosHref || "/alumnos"
    try {
      if (typeof window !== "undefined") {
        // Forzamos navegación completa para evitar reutilizar estado trabado de App Router.
        window.location.assign(target)
        return
      }
    } catch {}

    if (target) {
      router.replace(target)
    }
  }

  /* ====================== FIX: tab por URL + persistencia para /mis-hijos ====================== */
  const shouldRememberTab = fromParamEffective === "/mis-hijos"

  useEffect(() => {
    const rawTab = String(searchParams.get("tab") || "").toLowerCase().trim()
    const rawFrom = String(searchParams.get("from") || "").trim()
    setTabParamRaw(rawTab)
    setFromParamRaw(rawFrom)
  }, [searchParams])

  useEffect(() => {
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

  const notasPendientesFirma = useMemo(
    () =>
      (Array.isArray(notas) ? notas : []).filter(
        (nota) => nota?.id && !isFirmadaFromAny(nota)
      ),
    [notas]
  )

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

  const sancionesPendientesFirma = useMemo(
    () =>
      (Array.isArray(sanciones) ? sanciones : []).filter(
        (sancion) => sancion?.id && !isFirmadaFromAny(sancion)
      ),
    [sanciones]
  )

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

  const asistenciasPendientesFirma = useMemo(
    () =>
      (Array.isArray(asistencias) ? asistencias : []).filter(
        (asistencia) =>
          getAsistenciaId(asistencia) &&
          isAsistenciaFirmable(asistencia) &&
          !isFirmadaFromAny(asistencia)
      ),
    [asistencias]
  )

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

  const openNotaModal = (nota) => {
    setNotaModal({
      open: true,
      notaId: nota?.id ?? null,
      materia: String(nota?.materia || ""),
      tipo: String(nota?.tipo || ""),
      resultado: String(nota?.resultado || ""),
      nota_numerica: String(nota?.nota_numerica ?? ""),
      cuatrimestre: String(notaCuatr(nota) || "1"),
      fecha: String(nota?.fecha || ""),
      observaciones: String(nota?.observaciones || nota?.comentarios || ""),
      error: "",
      saving: false,
    })
  }

  const closeNotaModal = () => {
    setNotaModal({
      open: false,
      notaId: null,
      materia: "",
      tipo: "",
      resultado: "",
      nota_numerica: "",
      cuatrimestre: "1",
      fecha: "",
      observaciones: "",
      error: "",
      saving: false,
    })
  }

  const handleGuardarNota = async () => {
    if (!notaModal.notaId || notaModal.saving) return

    const draft = { ...notaModal }
    const notaNumerica = normalizeNotaNumericaInput(notaModal.nota_numerica).trim()
    if (!notaModal.materia || !notaModal.tipo || !notaModal.cuatrimestre) {
      setNotaModal((prev) => ({ ...prev, error: "Completá materia, tipo y cuatrimestre." }))
      return
    }
    if (!notaModal.resultado && !notaNumerica) {
      setNotaModal((prev) => ({
        ...prev,
        error: "Completá resultado o nota numérica.",
      }))
      return
    }

    setNotaModal((prev) => ({ ...prev, saving: true, error: "" }))
    const targetNotaId = draft.notaId
    const payload = {
      materia: draft.materia,
      tipo: draft.tipo,
      resultado: draft.resultado || null,
      nota_numerica: notaNumerica || null,
      calificacion: draft.resultado || notaNumerica || "",
      cuatrimestre: Number(draft.cuatrimestre),
      fecha: draft.fecha || null,
      observaciones: draft.observaciones,
    }
    const previousNotas = Array.isArray(notas) ? notas : []
    const previousNota = previousNotas.find((item) => String(item?.id) === String(targetNotaId))
    const optimisticNota = previousNota
      ? {
          ...previousNota,
          ...payload,
          id: previousNota.id,
        }
      : null

    if (optimisticNota) {
      setNotas((prev) =>
        (Array.isArray(prev) ? prev : []).map((item) =>
          String(item?.id) === String(targetNotaId) ? optimisticNota : item
        )
      )
    }
    setSavingNotaId(String(targetNotaId))
    closeNotaModal()

    const r = await fetchJSON(`/calificaciones/notas/${targetNotaId}/`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    })

    if (!r.ok) {
      const detail =
        r.data?.detail ||
        Object.values(r.data?.errors || {})
          .flat()
          .join(" ") ||
        `Error (HTTP ${r.status || "?"})`
      if (previousNota) {
        setNotas((prev) =>
          (Array.isArray(prev) ? prev : []).map((item) =>
            String(item?.id) === String(targetNotaId) ? previousNota : item
          )
        )
      }
      setSavingNotaId(null)
      setNotaModal({
        ...draft,
        open: true,
        error: detail,
        saving: false,
      })
      return
    }

    const notaActualizada = r.data?.nota || payload

    setNotas((prev) =>
      (Array.isArray(prev) ? prev : []).map((item) =>
        String(item?.id) === String(targetNotaId)
          ? {
              ...item,
              ...notaActualizada,
              observaciones: notaActualizada.observaciones,
            }
          : item
      )
    )
    setSavingNotaId(null)
  }

  const nombreAlumno = useMemo(() => {
    if (loading && !alumnoDetail) return ""
    const a = alumnoDetail || {}
    return a.nombre && a.apellido
      ? `${a.nombre} ${a.apellido}`
      : a.full_name || a.apellido_y_nombre || a.nombre || "Alumno"
  }, [alumnoDetail, loading])

  const cursoAlumno = useMemo(() => {
    const a = alumnoDetail || {}
    return a.school_course_name || a.division || "—"
  }, [alumnoDetail])

  const legajoAlumno = useMemo(() => {
    const a = alumnoDetail || {}
    return a.id_alumno || a.legajo || a.codigo || String(code || "")
  }, [alumnoDetail, code])

  const alumnoCacheId = useMemo(
    () => String(pk || code || alumnoid || "").trim(),
    [pk, code, alumnoid]
  )
  const lastLoadedRef = useRef({ notas: "", sanciones: "", asistencias: "" })
  const inFlightRef = useRef({ notas: "", sanciones: "", asistencias: "" })

  useEffect(() => {
    if (!alumnoCacheId) return
    lastLoadedRef.current = { notas: "", sanciones: "", asistencias: "" }
    inFlightRef.current = { notas: "", sanciones: "", asistencias: "" }
    const cachedNotas = getCachedList(NOTAS_CACHE_PREFIX, alumnoCacheId)
    if (cachedNotas.data) {
      setNotas(Array.isArray(cachedNotas.data) ? cachedNotas.data : [])
    }

    const cachedSanciones = getCachedList(SANCIONES_CACHE_PREFIX, alumnoCacheId)
    if (cachedSanciones.data) {
      setSanciones(Array.isArray(cachedSanciones.data) ? cachedSanciones.data : [])
    }

    const cachedAsistencias = getCachedList(ASISTENCIAS_CACHE_PREFIX, alumnoCacheId)
    if (cachedAsistencias.data) {
      setAsistencias(
        Array.isArray(cachedAsistencias.data) ? cachedAsistencias.data : []
      )
    }
  }, [alumnoCacheId])

  const fetchNotas = useCallback(async () => {
    if (!pk && !code) return
    const key = `${pk || ""}:${code || ""}`
    if (lastLoadedRef.current.notas === key) return
    if (inFlightRef.current.notas === key) return
    const currentNotas = notasRef.current

    const cached = getCachedList(NOTAS_CACHE_PREFIX, alumnoCacheId)
    if (cached.fresh && Array.isArray(cached.data) && cached.data.length > 0) {
      setNotas(Array.isArray(cached.data) ? cached.data : [])
      lastLoadedRef.current.notas = key
      return
    }

    if (
      Array.isArray(cached.data) &&
      cached.data.length > 0 &&
      (!Array.isArray(currentNotas) || currentNotas.length === 0)
    ) {
      setNotas(Array.isArray(cached.data) ? cached.data : [])
    }

    inFlightRef.current.notas = key
    setLoadingNotas(true)
    try {
      const n = await getNotasByPkOrCode(pk, code)
      setNotas(Array.isArray(n) ? n : [])
      setCachedList(NOTAS_CACHE_PREFIX, alumnoCacheId, Array.isArray(n) ? n : [])
      lastLoadedRef.current.notas = key
    } finally {
      if (inFlightRef.current.notas === key) {
        inFlightRef.current.notas = ""
      }
      setLoadingNotas(false)
    }
  }, [pk, code, alumnoCacheId])

  const fetchSanciones = useCallback(async () => {
    if (!pk && !code) return
    const key = `${pk || ""}:${code || ""}`
    if (lastLoadedRef.current.sanciones === key) return
    if (inFlightRef.current.sanciones === key) return
    const currentSanciones = sancionesRef.current

    const cached = getCachedList(SANCIONES_CACHE_PREFIX, alumnoCacheId)
    if (cached.fresh) {
      setSanciones(Array.isArray(cached.data) ? cached.data : [])
      lastLoadedRef.current.sanciones = key
      return
    }

    if (
      cached.data &&
      (!Array.isArray(currentSanciones) || currentSanciones.length === 0)
    ) {
      setSanciones(Array.isArray(cached.data) ? cached.data : [])
    }

    inFlightRef.current.sanciones = key
    setLoadingSanciones(true)
    try {
      const s = await getSancionesByPkOrCode(pk, code)
      setSanciones(Array.isArray(s) ? s : [])
      setCachedList(SANCIONES_CACHE_PREFIX, alumnoCacheId, Array.isArray(s) ? s : [])
      lastLoadedRef.current.sanciones = key
    } finally {
      if (inFlightRef.current.sanciones === key) {
        inFlightRef.current.sanciones = ""
      }
      setLoadingSanciones(false)
    }
  }, [pk, code, alumnoCacheId])

  const fetchAsistencias = useCallback(async () => {
    if (!pk && !code) return
    const codeStr = String(code || "").trim()
    // Evita 404 ruidosos cuando todavía no resolvimos pk y el "code" es numérico.
    if (!pk && codeStr && /^\d+$/.test(codeStr)) {
      return
    }
    const key = `${pk || ""}:${code || ""}`
    const currentAsistencias = asistenciasRef.current
    if (
      lastLoadedRef.current.asistencias === key &&
      Array.isArray(currentAsistencias) &&
      currentAsistencias.length > 0
    )
      return
    if (inFlightRef.current.asistencias === key) return

    const cached = getCachedList(ASISTENCIAS_CACHE_PREFIX, alumnoCacheId)
    if (cached.fresh) {
      setAsistencias((prev) => {
        if (Array.isArray(prev) && prev.length > 0) return prev
        return Array.isArray(cached.data) ? cached.data : []
      })
      // Revalidamos en background para no quedar desactualizado.
    }

    if (
      cached.data &&
      (!Array.isArray(currentAsistencias) || currentAsistencias.length === 0)
    ) {
      setAsistencias(Array.isArray(cached.data) ? cached.data : [])
    }

    inFlightRef.current.asistencias = key
    setLoadingAsistencias(true)
    try {
      const a = await getAsistenciasByPkOrCode(pk, code)
      setAsistencias(Array.isArray(a) ? a : [])
      setCachedList(ASISTENCIAS_CACHE_PREFIX, alumnoCacheId, Array.isArray(a) ? a : [])
      lastLoadedRef.current.asistencias = key
    } finally {
      if (inFlightRef.current.asistencias === key) {
        inFlightRef.current.asistencias = ""
      }
      setLoadingAsistencias(false)
    }
  }, [pk, code, alumnoCacheId])

  useEffect(() => {
    notasRef.current = Array.isArray(notas) ? notas : []
  }, [notas])

  useEffect(() => {
    sancionesRef.current = Array.isArray(sanciones) ? sanciones : []
  }, [sanciones])

  useEffect(() => {
    asistenciasRef.current = Array.isArray(asistencias) ? asistencias : []
  }, [asistencias])

  useEffect(() => {
    if (shouldHideAlumnoContent) return
    const target = activeSectionLower || (isAlumno ? "notas" : "")
    if (!target) return
    if (target === "notas") fetchNotas()
    if (target === "sanciones") fetchSanciones()
    if (target === "asistencias") fetchAsistencias()
  }, [
    activeSectionLower,
    isAlumno,
    shouldHideAlumnoContent,
    fetchNotas,
    fetchSanciones,
    fetchAsistencias,
  ])

  useEffect(() => {
    if (shouldHideAlumnoContent) return
    if (!pk && !code) return

    if (isAlumno) {
      Promise.allSettled([fetchNotas(), fetchSanciones(), fetchAsistencias()])
      return
    }

    const idleId = runIdle(() => {
      const tasks = []
      if (activeSectionLower !== "notas") tasks.push(fetchNotas())
      if (activeSectionLower !== "sanciones") tasks.push(fetchSanciones())
      if (activeSectionLower !== "asistencias") tasks.push(fetchAsistencias())
      if (tasks.length) Promise.allSettled(tasks)
    })

    return () => cancelIdle(idleId)
  }, [
    pk,
    code,
    isAlumno,
    shouldHideAlumnoContent,
    activeSectionLower,
    fetchNotas,
    fetchSanciones,
    fetchAsistencias,
  ])


  const handleDownloadNotasPdf = async () => {
    if (downloadingPdf) return
    setDownloadingPdf(true)

    try {
      const { jsPDF } = await import("jspdf")
      const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" })
      const margin = 40
      const pageWidth = doc.internal.pageSize.getWidth()
      const pageHeight = doc.internal.pageSize.getHeight()
      const contentWidth = pageWidth - margin * 2
      const fixedWidth = 80 + 140 + 60 + 120 + 80
      const commentsWidth = Math.max(140, contentWidth - fixedWidth)
      const columns = [
        { key: "fecha", label: "Fecha", width: 80 },
        { key: "materia", label: "Materia", width: 140 },
        { key: "cuatr", label: "Cuatr.", width: 60 },
        { key: "tipo", label: "Tipo", width: 120 },
        { key: "calificacion", label: "Calificación", width: 80 },
        { key: "comentarios", label: "Comentarios", width: commentsWidth },
      ]
      const lineHeight = 12
      const now = new Date()
      let y = margin

      doc.setFont("helvetica", "bold")
      doc.setFontSize(16)
      doc.text("Notas del alumno", margin, y)
      y += 20

      doc.setFont("helvetica", "normal")
      doc.setFontSize(11)
      doc.text(`Alumno: ${nombreAlumno || "Alumno"}`, margin, y)
      y += 14
      doc.text(`Curso: ${cursoAlumno || "-"}`, margin, y)
      y += 14
      doc.text(`Legajo/ID: ${legajoAlumno || "-"}`, margin, y)
      y += 14
      doc.text(`Generado: ${now.toLocaleString("es-AR")}`, margin, y)
      y += 18

      const filtros = [
        `Materia: ${filMateria === "ALL" ? "Todas" : filMateria}`,
        `Cuatrimestre: ${filCuatr === "ALL" ? "Todos" : filCuatr}`,
        `Tipo: ${filTipo === "ALL" ? "Todos" : filTipo}`,
        `Buscar: ${buscar ? buscar : "Sin filtro"}`,
      ]
      doc.text(filtros.join(" | "), margin, y)
      y += 18

      const drawTableHeader = () => {
        doc.setFont("helvetica", "bold")
        doc.setFontSize(10)
        let x = margin
        columns.forEach((col) => {
          doc.text(col.label, x + 2, y)
          x += col.width
        })
        y += 10
        doc.setDrawColor(220)
        doc.line(margin, y, pageWidth - margin, y)
        y += 8
      }

      drawTableHeader()

      if (notasFiltradas.length === 0) {
        doc.setFont("helvetica", "normal")
        doc.setFontSize(11)
        doc.text("No hay notas para los filtros actuales.", margin, y)
      } else {
        doc.setFont("helvetica", "normal")
        doc.setFontSize(10)

        for (const nota of notasFiltradas) {
          const cuatr = notaCuatr(nota)
          const row = {
            fecha: fmtFecha(nota.fecha || nota.created_at),
            materia: nota.materia || "",
            cuatr: cuatr ?? "",
            tipo: nota.tipo || "",
            calificacion: String(toNumberOrText(nota.calificacion) ?? ""),
            comentarios: nota.observaciones || nota.comentarios || "",
          }

          const cellLines = columns.map((col) =>
            doc.splitTextToSize(String(row[col.key] || ""), col.width - 6)
          )
          const maxLines = Math.max(1, ...cellLines.map((lines) => lines.length))
          const rowHeight = maxLines * lineHeight + 6

          if (y + rowHeight > pageHeight - margin) {
            doc.addPage()
            y = margin
            drawTableHeader()
          }

          let x = margin
          cellLines.forEach((lines, idx) => {
            const col = columns[idx]
            lines.forEach((line, i) => {
              doc.text(String(line), x + 2, y + i * lineHeight)
            })
            x += col.width
          })

          y += rowHeight
          doc.setDrawColor(235)
          doc.line(margin, y - 2, pageWidth - margin, y - 2)
        }
      }

      const safeName = String(nombreAlumno || "alumno")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .toLowerCase()
      const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(
        2,
        "0"
      )}-${String(now.getDate()).padStart(2, "0")}`
      const fileName = `notas_${safeName || "alumno"}_${stamp}.pdf`
      doc.save(fileName)
    } catch (err) {
      console.error("No se pudo generar el PDF de notas:", err)
      alert("No se pudo generar el PDF. Probá nuevamente.")
  } finally {
      setDownloadingPdf(false)
    }
  }

  const handleFirmarTodasNotas = async () => {
    if (signingAllNotas) return
    const pendientes = notasPendientesFirma
    if (!pendientes.length) return

    setConfirmFirmarTodoOpen(false)
    setSigningAllNotas(true)
    try {
      const results = await Promise.allSettled(
        pendientes.map(async (nota) => {
          const r = await firmarNota(nota.id)
          if (!r.ok) {
            throw new Error(r.data?.detail || `Error (HTTP ${r.status || "?"})`)
          }
          return {
            id: nota.id,
            firmada_en: r.data?.firmada_en || new Date().toISOString(),
          }
        })
      )

      const firmadas = new Map()
      let fallidas = 0

      for (const result of results) {
        if (result.status === "fulfilled") {
          firmadas.set(String(result.value.id), result.value.firmada_en)
        } else {
          fallidas += 1
        }
      }

      if (firmadas.size > 0) {
        setNotas((prev) => {
          const next = (Array.isArray(prev) ? prev : []).map((nota) => {
            const firmadaEn = firmadas.get(String(nota?.id || ""))
            if (!firmadaEn) return nota
            return {
              ...nota,
              firmada: true,
              firmada_en: firmadaEn,
            }
          })
          setCachedList(NOTAS_CACHE_PREFIX, alumnoCacheId, next)
          return next
        })
      }

      if (fallidas > 0) {
        alert(
          fallidas === 1
            ? "No se pudo firmar 1 nota pendiente."
            : `No se pudieron firmar ${fallidas} notas pendientes.`
        )
      }
    } finally {
      setSigningAllNotas(false)
    }
  }

  const handleDownloadSancionesPdf = async () => {
    if (downloadingSancionesPdf) return
    setDownloadingSancionesPdf(true)

    try {
      const { jsPDF } = await import("jspdf")
      const doc = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" })
      const margin = 40
      const pageWidth = doc.internal.pageSize.getWidth()
      const pageHeight = doc.internal.pageSize.getHeight()
      const contentWidth = pageWidth - margin * 2
      const fixedWidth = 90 + 120
      const motivoWidth = Math.max(220, contentWidth - fixedWidth)
      const columns = [
        { key: "fecha", label: "Fecha", width: 90 },
        { key: "motivo", label: "Motivo", width: motivoWidth },
        { key: "docente", label: "Docente", width: 120 },
      ]
      const lineHeight = 12
      const now = new Date()
      let y = margin

      doc.setFont("helvetica", "bold")
      doc.setFontSize(16)
      doc.text("Sanciones del alumno", margin, y)
      y += 20

      doc.setFont("helvetica", "normal")
      doc.setFontSize(11)
      doc.text(`Alumno: ${nombreAlumno || "Alumno"}`, margin, y)
      y += 14
      doc.text(`Curso: ${cursoAlumno || "-"}`, margin, y)
      y += 14
      doc.text(`Legajo/ID: ${legajoAlumno || "-"}`, margin, y)
      y += 14
      doc.text(`Generado: ${now.toLocaleString("es-AR")}`, margin, y)
      y += 18

      const filtros = [
        `Mes: ${filSancionMes === "ALL" ? "Todos" : filSancionMes}`,
        `Docente: ${filSancionDocente === "ALL" ? "Todos" : filSancionDocente}`,
        `Buscar: ${buscarSanc ? buscarSanc : "Sin filtro"}`,
      ]
      doc.text(filtros.join(" | "), margin, y)
      y += 18

      const drawTableHeader = () => {
        doc.setFont("helvetica", "bold")
        doc.setFontSize(10)
        let x = margin
        columns.forEach((col) => {
          doc.text(col.label, x + 2, y)
          x += col.width
        })
        y += 10
        doc.setDrawColor(220)
        doc.line(margin, y, pageWidth - margin, y)
        y += 8
      }

      drawTableHeader()

      if (sancionesFiltradas.length === 0) {
        doc.setFont("helvetica", "normal")
        doc.setFontSize(11)
        doc.text("No hay sanciones para los filtros actuales.", margin, y)
      } else {
        doc.setFont("helvetica", "normal")
        doc.setFontSize(10)

        for (const sancion of sancionesFiltradas) {
          const row = {
            fecha: fmtFecha(sancion.fecha || sancion.created_at),
            motivo: sancion.motivo || sancion.detalle || sancion.descripcion || "",
            docente: sancion.docente || sancion.creado_por || "",
          }

          const cellLines = columns.map((col) =>
            doc.splitTextToSize(String(row[col.key] || ""), col.width - 6)
          )
          const maxLines = Math.max(1, ...cellLines.map((lines) => lines.length))
          const rowHeight = maxLines * lineHeight + 6

          if (y + rowHeight > pageHeight - margin) {
            doc.addPage()
            y = margin
            drawTableHeader()
          }

          let x = margin
          cellLines.forEach((lines, idx) => {
            const col = columns[idx]
            lines.forEach((line, i) => {
              doc.text(String(line), x + 2, y + i * lineHeight)
            })
            x += col.width
          })

          y += rowHeight
          doc.setDrawColor(235)
          doc.line(margin, y - 2, pageWidth - margin, y - 2)
        }
      }

      const safeName = String(nombreAlumno || "alumno")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .toLowerCase()
      const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(
        2,
        "0"
      )}-${String(now.getDate()).padStart(2, "0")}`
      const fileName = `sanciones_${safeName || "alumno"}_${stamp}.pdf`
      doc.save(fileName)
    } catch (err) {
      console.error("No se pudo generar el PDF de sanciones:", err)
      alert("No se pudo generar el PDF. Proba nuevamente.")
    } finally {
      setDownloadingSancionesPdf(false)
    }
  }

  const handleFirmarTodasSanciones = async () => {
    if (signingAllSanciones) return
    const pendientes = sancionesPendientesFirma
    if (!pendientes.length) return

    setConfirmFirmarSancionesOpen(false)
    setSigningAllSanciones(true)
    try {
      const results = await Promise.allSettled(
        pendientes.map(async (sancion) => {
          const r = await firmarSancion(sancion.id)
          if (!r.ok) {
            throw new Error(r.data?.detail || `Error (HTTP ${r.status || "?"})`)
          }
          return {
            id: sancion.id,
            firmada_en: r.data?.firmada_en || new Date().toISOString(),
          }
        })
      )

      const firmadas = new Map()
      let fallidas = 0

      for (const result of results) {
        if (result.status === "fulfilled") {
          firmadas.set(String(result.value.id), result.value.firmada_en)
        } else {
          fallidas += 1
        }
      }

      if (firmadas.size > 0) {
        setSanciones((prev) => {
          const next = (Array.isArray(prev) ? prev : []).map((sancion) => {
            const firmadaEn = firmadas.get(String(sancion?.id || ""))
            if (!firmadaEn) return sancion
            return {
              ...sancion,
              firmada: true,
              firmada_en: firmadaEn,
            }
          })
          setCachedList(SANCIONES_CACHE_PREFIX, alumnoCacheId, next)
          return next
        })
      }

      if (fallidas > 0) {
        alert(
          fallidas === 1
            ? "No se pudo firmar 1 sanción pendiente."
            : `No se pudieron firmar ${fallidas} sanciones pendientes.`
        )
      }
    } finally {
      setSigningAllSanciones(false)
    }
  }

  const handleDownloadAsistenciasPdf = async () => {
    if (downloadingAsistenciasPdf) return
    setDownloadingAsistenciasPdf(true)

    try {
      const { jsPDF } = await import("jspdf")
      const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" })
      const margin = 40
      const pageWidth = doc.internal.pageSize.getWidth()
      const pageHeight = doc.internal.pageSize.getHeight()
      const contentWidth = pageWidth - margin * 2
      const fixedWidth = 90 + 120 + 90 + 90
      const detalleWidth = Math.max(180, contentWidth - fixedWidth)
      const columns = [
        { key: "fecha", label: "Fecha", width: 90 },
        { key: "asistencia", label: "Asistencia", width: 120 },
        { key: "estado", label: "Estado", width: 90 },
        { key: "justificada", label: "Justificada", width: 90 },
        { key: "detalle", label: "Detalle", width: detalleWidth },
      ]
      const lineHeight = 12
      const now = new Date()
      let y = margin

      doc.setFont("helvetica", "bold")
      doc.setFontSize(16)
      doc.text("Inasistencias del alumno", margin, y)
      y += 20

      doc.setFont("helvetica", "normal")
      doc.setFontSize(11)
      doc.text(`Alumno: ${nombreAlumno || "Alumno"}`, margin, y)
      y += 14
      doc.text(`Curso: ${cursoAlumno || "-"}`, margin, y)
      y += 14
      doc.text(`Legajo/ID: ${legajoAlumno || "-"}`, margin, y)
      y += 14
      doc.text(`Generado: ${now.toLocaleString("es-AR")}`, margin, y)
      y += 18

      const mesLabel =
        filAsisMes === "ALL" ? "Todos" : monthLabelFromKey(filAsisMes)
      const tipoLabel =
        filAsisTipo === "ALL" ? "Todas" : asistenciaTipoLabel(filAsisTipo)
      const filtros = [`Mes: ${mesLabel}`, `Asistencia: ${tipoLabel}`]
      doc.text(filtros.join(" | "), margin, y)
      y += 18

      const drawTableHeader = () => {
        doc.setFont("helvetica", "bold")
        doc.setFontSize(10)
        let x = margin
        columns.forEach((col) => {
          doc.text(col.label, x + 2, y)
          x += col.width
        })
        y += 10
        doc.setDrawColor(220)
        doc.line(margin, y, pageWidth - margin, y)
        y += 8
      }

      drawTableHeader()

      if (asistenciasFiltradas.length === 0) {
        doc.setFont("helvetica", "normal")
        doc.setFontSize(11)
        doc.text("No hay asistencias para los filtros actuales.", margin, y)
      } else {
        doc.setFont("helvetica", "normal")
        doc.setFontSize(10)

        for (const asistencia of asistenciasFiltradas) {
          const tipoRaw = asistenciaTipoFromAny(asistencia)
          const tipoNorm = normalizeAsistenciaTipo(tipoRaw) || "clases"
          const est = estadoTexto(asistenciaEstadoFromAny(asistencia))
          const just = isJustificadaFromAny(asistencia) ? "Si" : "No"
          const detalle =
            asistencia.detalle ||
            asistencia.observaciones ||
            asistencia.observacion ||
            ""

          const row = {
            fecha: fmtFecha(asistencia.fecha || asistencia.created_at),
            asistencia: asistenciaTipoLabel(tipoNorm),
            estado: est,
            justificada: just,
            detalle,
          }

          const cellLines = columns.map((col) =>
            doc.splitTextToSize(String(row[col.key] || ""), col.width - 6)
          )
          const maxLines = Math.max(1, ...cellLines.map((lines) => lines.length))
          const rowHeight = maxLines * lineHeight + 6

          if (y + rowHeight > pageHeight - margin) {
            doc.addPage()
            y = margin
            drawTableHeader()
          }

          let x = margin
          cellLines.forEach((lines, idx) => {
            const col = columns[idx]
            lines.forEach((line, i) => {
              doc.text(String(line), x + 2, y + i * lineHeight)
            })
            x += col.width
          })

          y += rowHeight
          doc.setDrawColor(235)
          doc.line(margin, y - 2, pageWidth - margin, y - 2)
        }
      }

      const safeName = String(nombreAlumno || "alumno")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .toLowerCase()
      const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(
        2,
        "0"
      )}-${String(now.getDate()).padStart(2, "0")}`
      const fileName = `inasistencias_${safeName || "alumno"}_${stamp}.pdf`
      doc.save(fileName)
    } catch (err) {
      console.error("No se pudo generar el PDF de asistencias:", err)
      alert("No se pudo generar el PDF. Proba nuevamente.")
    } finally {
      setDownloadingAsistenciasPdf(false)
    }
  }

  const handleFirmarTodasAsistencias = async () => {
    if (signingAllAsistencias) return
    const pendientes = asistenciasPendientesFirma
    if (!pendientes.length) return

    setConfirmFirmarAsistenciasOpen(false)
    setSigningAllAsistencias(true)
    try {
      const results = await Promise.allSettled(
        pendientes.map(async (asistencia) => {
          const asistenciaId = getAsistenciaId(asistencia)
          const r = await firmarAsistencia(asistenciaId)
          if (!r.ok) {
            throw new Error(r.data?.detail || `Error (HTTP ${r.status || "?"})`)
          }
          return {
            id: asistenciaId,
            firmada_en: r.data?.firmada_en || new Date().toISOString(),
          }
        })
      )

      const firmadas = new Map()
      let fallidas = 0

      for (const result of results) {
        if (result.status === "fulfilled") {
          firmadas.set(String(result.value.id), result.value.firmada_en)
        } else {
          fallidas += 1
        }
      }

      if (firmadas.size > 0) {
        setAsistencias((prev) => {
          const next = (Array.isArray(prev) ? prev : []).map((asistencia) => {
            const asistenciaId = getAsistenciaId(asistencia)
            const firmadaEn = firmadas.get(String(asistenciaId || ""))
            if (!firmadaEn) return asistencia
            return {
              ...asistencia,
              firmada: true,
              firmada_en: firmadaEn,
            }
          })
          setCachedList(ASISTENCIAS_CACHE_PREFIX, alumnoCacheId, next)
          return next
        })
      }

      if (fallidas > 0) {
        alert(
          fallidas === 1
            ? "No se pudo firmar 1 inasistencia pendiente."
            : `No se pudieron firmar ${fallidas} inasistencias pendientes.`
        )
      }
    } finally {
      setSigningAllAsistencias(false)
    }
  }

  const renderNotasPanel = ({
    title,
    subtitle,
    icon,
    iconWrapClass,
    idPrefix = "notas",
  }) => {
    const materiaId = `${idPrefix}-filMateria`
    const cuatrId = `${idPrefix}-filCuatr`
    const tipoId = `${idPrefix}-filTipo`
    const buscarId = `${idPrefix}-buscar`

    return (
      <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
        <CardContent className="p-6">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="flex items-start gap-4">
              <div
                className={`w-12 h-12 rounded-lg flex items-center justify-center ${iconWrapClass}`}
              >
                {icon}
              </div>
              <div className="flex-1">
                <h3 className="tile-title">{title}</h3>
                {subtitle ? <p className="tile-subtitle">{subtitle}</p> : null}
              </div>
            </div>
          </div>

          <div className="mb-4 grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div>
              <Label htmlFor={materiaId} className="text-xs text-gray-600">
                Materia
              </Label>
              <select
                id={materiaId}
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
              <Label htmlFor={cuatrId} className="text-xs text-gray-600">
                Cuatrimestre
              </Label>
              <select
                id={cuatrId}
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
              <Label htmlFor={tipoId} className="text-xs text-gray-600">
                Tipo
              </Label>
              <select
                id={tipoId}
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
              <Label htmlFor={buscarId} className="text-xs text-gray-600">
                Buscar
              </Label>
              <input
                id={buscarId}
                className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                placeholder="Materia, nota, comentario..."
                value={buscar}
                onChange={(e) => setBuscar(e.target.value)}
              />
            </div>
          </div>

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
                          <span className="inline-flex items-center px-2 py-0.5 rounded school-primary-soft-badge">
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
    )
  }

  return (
    <div className="space-y-6">
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

      <div className="space-y-6">
        {/* ===== Encabezado + acciones ===== */}
        <div
          className={[
            "flex justify-between gap-4",
            showKidSelector ? "items-center" : "items-start",
          ].join(" ")}
        >
          <div
            className={[
              "flex gap-4",
              showKidSelector ? "items-center" : "items-start",
            ].join(" ")}
          >
            <div className="w-14 h-14 rounded-xl flex items-center justify-center school-primary-soft-icon">
              <Users className="w-7 h-7" />
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
                      <Label className="block text-sm mb-1">Alumno</Label>
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
                <Button type="button" variant="primary" onClick={handleBackToAlumnos} className="primary-button">
                  &lt; Volver a alumnos
                </Button>
                {canTransferAlumno && (
                  <TransferAlumno
                    alumnoPk={pk}
                    alumnoCode={code}
                    cursoActual={cursoAlumno}
                    onTransferred={() => {
                      try {
                        router.refresh?.()
                      } catch {}
                    }}
                  />
                )}
                <ComposeMensajeAlumno
                  // ✅ NUEVO: identificadores y nombre para preseleccionar destinatario
                  alumnoPk={pk}
                  alumnoCode={code}
                  alumnoNombre={nombreAlumno}
                  onSent={() => {
                    try {
                      // Evento unificado + refresco local del inbox
                      window.dispatchEvent(new Event(INBOX_EVENT))
                      window.dispatchEvent(new Event("inbox-changed"))
                    } catch {}
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {!isAlumno && rolesReady && (
          <>
            {/* ===== Tarjetas resumen (clickeables) ===== */}
        <div className="grid md:grid-cols-3 gap-4">
          <Card
            onClick={() => setActiveSection("notas")}
            className={[
              "border-0 shadow-sm cursor-pointer transition-all school-hover-card",
              activeSection === "notas" ? "school-primary-selected" : "",
            ].join(" ")}
          >
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center school-primary-soft-icon">
                  <ClipboardList className="w-5 h-5" />
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
          </>
        )}

        {shouldHideAlumnoContent ? null : error ? (
          <div className="p-4 bg-red-50 text-red-700 rounded-lg border border-red-200">
            {error}
          </div>
        ) : loading || !rolesReady ? (
          <div className="text-sm text-gray-600">Cargando información del alumno…</div>
        ) : (
          <>
            {/* ===== Sección: Notas ===== */}
            {activeSection === "notas" && (
              <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
                <CardContent className="p-6">
                  <div className="flex items-start justify-between gap-4 mb-4">
                    <div className="flex items-start gap-4">
                      <div className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 school-primary-soft-icon">
                        <ClipboardList className="h-6 w-6" />
                      </div>
                      <div className="flex-1">
                        <h3 className="tile-title">Notas</h3>
                        <p className="tile-subtitle">
                          Calificaciones registradas por materia
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {canSignByPadre ? (
                        <Button
                          type="button"
                          onClick={() => setConfirmFirmarTodoOpen(true)}
                          disabled={signingAllNotas || notasPendientesFirma.length === 0}
                          className="h-9 gap-2 primary-button disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {signingAllNotas ? "Firmando..." : "Firmar todo"}
                        </Button>
                      ) : null}
                      <Button
                        type="button"
                        onClick={handleDownloadNotasPdf}
                        disabled={downloadingPdf}
                        className="h-9 gap-2 primary-button"
                      >
                        <Download className="h-4 w-4" />
                        {downloadingPdf ? "Generando..." : "Descargar en PDF"}
                      </Button>
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
                  {loadingNotas && notas.length === 0 ? (
                    <div className="text-sm text-gray-600">Cargando notas...</div>
                  ) : notasFiltradas.length === 0 ? (
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
                            {canViewFirmaEstado ? <th className="py-2 pr-4">Firma</th> : null}
                            {canEditNotas ? <th className="py-2 pr-4 text-right">Editar</th> : null}
                          </tr>
                        </thead>
                        <tbody>
                          {notasFiltradas.map((n, i) => {
                            const cuatr = notaCuatr(n)
                            const firmada = isFirmadaFromAny(n)
                            const firmadaEn = n?.firmada_en || n?.firmado_en || null
                            return (
                              <tr key={n.id || i} className="border-b last:border-b-0">
                                <td className="py-2 pr-4">
                                  {fmtFecha(n.fecha || n.created_at)}
                                </td>
                                <td className="py-2 pr-4">{n.materia || "—"}</td>
                                <td className="py-2 pr-4">{cuatr ?? "—"}</td>
                                <td className="py-2 pr-4">{n.tipo || "—"}</td>
                                <td className="py-2 pr-4">
                                  <span className="inline-flex items-center px-2 py-0.5 rounded school-primary-soft-badge">
                                    {toNumberOrText(n.calificacion)}
                                  </span>
                                </td>
                                <td className="py-2 pr-4">
                                  {n.observaciones || n.comentarios || "—"}
                                </td>
                                {canViewFirmaEstado ? (
                                  <td className="py-2 pr-4">
                                    {firmada ? (
                                      <span className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-emerald-300 bg-emerald-50 text-emerald-800">
                                        Firmada {firmadaEn ? `- ${fmtFecha(firmadaEn)}` : ""}
                                      </span>
                                    ) : canSignByPadre ? (
                                      <button
                                        type="button"
                                        onClick={async () => {
                                          setSigningNotaId(String(n.id || ""))
                                          const r = await firmarNota(n.id)
                                          setSigningNotaId(null)
                                          if (!r.ok) {
                                            alert(
                                              r.data?.detail ||
                                                `Error (HTTP ${r.status || "?"})`
                                            )
                                            return
                                          }

                                          setNotas((prev) => {
                                            const list = Array.isArray(prev) ? prev : []
                                            const next = list.map((x) =>
                                              String(x?.id || "") !== String(n.id || "")
                                                ? x
                                                : {
                                                    ...x,
                                                    firmada: true,
                                                    firmada_en:
                                                      r.data?.firmada_en || new Date().toISOString(),
                                                  }
                                            )
                                            setCachedList(NOTAS_CACHE_PREFIX, alumnoCacheId, next)
                                            return next
                                          })
                                        }}
                                        disabled={
                                          signingAllNotas ||
                                          String(signingNotaId || "") === String(n.id || "")
                                        }
                                        className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-gray-300 bg-white text-gray-800 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
                                      >
                                        {String(signingNotaId || "") === String(n.id || "")
                                          ? "Firmando..."
                                          : "Firmar"}
                                      </button>
                                    ) : (
                                      <span className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-amber-300 bg-amber-50 text-amber-800">
                                        Pendiente
                                      </span>
                                    )}
                                  </td>
                                ) : null}
                                {canEditNotas ? (
                                  <td className="py-2 pr-4 text-right">
                                    <button
                                      type="button"
                                      onClick={() => openNotaModal(n)}
                                      disabled={String(savingNotaId || "") === String(n.id || "")}
                                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
                                      aria-label="Editar nota"
                                      title="Editar nota"
                                    >
                                      {String(savingNotaId || "") === String(n.id || "") ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                      ) : (
                                        <Pencil className="h-4 w-4" />
                                      )}
                                    </button>
                                  </td>
                                ) : null}
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
                  <div className="flex items-center justify-between gap-4 mb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 bg-amber-100 rounded-lg flex items-center justify-center">
                        <Gavel className="h-6 w-6 text-amber-700" />
                      </div>
                      <div>
                        <h3 className="tile-title">Sanciones</h3>
                        <p className="tile-subtitle">
                          Historial disciplinario del alumno
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {canSignByPadre ? (
                        <Button
                          type="button"
                          onClick={() => setConfirmFirmarSancionesOpen(true)}
                          disabled={
                            signingAllSanciones ||
                            sancionesPendientesFirma.length === 0
                          }
                          className="h-9 gap-2 primary-button disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {signingAllSanciones ? "Firmando..." : "Firmar todo"}
                        </Button>
                      ) : null}
                      <Button
                        type="button"
                        onClick={handleDownloadSancionesPdf}
                        disabled={downloadingSancionesPdf}
                        className="h-9 gap-2 primary-button"
                      >
                        <Download className="h-4 w-4" />
                        {downloadingSancionesPdf ? "Generando..." : "Descargar en PDF"}
                      </Button>
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
                  {loadingSanciones && sanciones.length === 0 ? (
                    <div className="text-sm text-gray-600">Cargando sanciones...</div>
                  ) : sancionesFiltradas.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      No hay sanciones registradas.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full table-fixed text-sm">
                        <colgroup>
                          <col className={canSignByPadre ? "w-[18%]" : "w-[20%]"} />
                          <col className={canSignByPadre ? "w-[42%]" : "w-[50%]"} />
                          <col className={canSignByPadre ? "w-[20%]" : "w-[30%]"} />
                          {canSignByPadre ? <col className="w-[20%]" /> : null}
                        </colgroup>
                        <thead>
                          <tr className="text-left text-gray-600 border-b">
                            <th className="py-2 pr-4">Fecha</th>
                            <th className="py-2 pr-4">Motivo</th>
                            <th className="py-2 pr-4">Docente</th>
                            {canSignByPadre ? <th className="py-2 pr-4">Firma</th> : null}
                          </tr>
                        </thead>
                        <tbody>
                          {sancionesFiltradas.map((s, i) => {
                            const firmada = isFirmadaFromAny(s)
                            const firmadaEn = s?.firmada_en || s?.firmado_en || null
                            return (
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
                                {canSignByPadre ? (
                                  <td className="py-2 pr-4">
                                    {firmada ? (
                                      <span className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-emerald-300 bg-emerald-50 text-emerald-800">
                                        Firmada {firmadaEn ? `- ${fmtFecha(firmadaEn)}` : ""}
                                      </span>
                                    ) : (
                                      <button
                                        type="button"
                                        onClick={async () => {
                                          setSigningSancionId(String(s.id || ""))
                                          const r = await firmarSancion(s.id)
                                          setSigningSancionId(null)
                                          if (!r.ok) {
                                            alert(
                                              r.data?.detail ||
                                                `Error (HTTP ${r.status || "?"})`
                                            )
                                            return
                                          }

                                          setSanciones((prev) => {
                                            const list = Array.isArray(prev) ? prev : []
                                            const next = list.map((x) => {
                                              if (String(x?.id || "") !== String(s.id || "")) return x
                                              return {
                                                ...x,
                                                firmada: true,
                                                firmada_en:
                                                  r.data?.firmada_en || new Date().toISOString(),
                                              }
                                            })
                                            setCachedList(
                                              SANCIONES_CACHE_PREFIX,
                                              alumnoCacheId,
                                              next
                                            )
                                            return next
                                          })
                                        }}
                                        disabled={
                                          signingAllSanciones ||
                                          String(signingSancionId || "") === String(s.id || "")
                                        }
                                        className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-gray-300 bg-white text-gray-800 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
                                      >
                                        {String(signingSancionId || "") === String(s.id || "")
                                          ? "Firmando..."
                                          : "Firmar"}
                                      </button>
                                    )}
                                  </td>
                                ) : null}
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
                      </div>
                    </div>

                    {/* ✅ NUEVO: filtros mes + tipo */}
                    <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end">
                      {asistencias.length > 0 && (
                        <>
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
                        </>
                      )}

                      <div className="flex items-center gap-2">
                        {canSignByPadre ? (
                          <Button
                            type="button"
                            onClick={() => setConfirmFirmarAsistenciasOpen(true)}
                            disabled={
                              signingAllAsistencias ||
                              asistenciasPendientesFirma.length === 0
                            }
                            className="h-9 gap-2 primary-button disabled:opacity-60 disabled:cursor-not-allowed"
                          >
                            {signingAllAsistencias ? "Firmando..." : "Firmar todo"}
                          </Button>
                        ) : null}
                        <Button
                          type="button"
                          onClick={handleDownloadAsistenciasPdf}
                          disabled={downloadingAsistenciasPdf}
                          className="h-9 gap-2 primary-button"
                        >
                          <Download className="h-4 w-4" />
                          {downloadingAsistenciasPdf
                            ? "Generando..."
                            : "Descargar en PDF"}
                        </Button>
                      </div>
                    </div>
                  </div>

                  {loadingAsistencias && asistencias.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      Cargando asistencias...
                    </div>
                  ) : asistencias.length === 0 ? (
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
                          <col className="w-[18%]" />
                          <col className="w-[22%]" />
                        </colgroup>
                        <thead>
                          <tr className="text-left text-gray-600 border-b">
                            <th className="py-2 pr-4">Fecha</th>
                            <th className="py-2 pr-4">Asistencia</th>
                            <th className="py-2 pr-4">Estado</th>
                            <th className="py-2 pr-4">Justificada</th>
                            <th className="py-2 pr-4">Firma</th>
                            <th className="py-2 pr-4">Detalle</th>
                          </tr>
                        </thead>
                        <tbody>
                          {asistenciasFiltradas.map((a, i) => {
                            const tipoRaw = asistenciaTipoFromAny(a)
                            const tipoNorm = normalizeAsistenciaTipo(tipoRaw) || "clases"
                            const rowId = getAsistenciaId(a) || `${i}`
                            const asistenciaId = getAsistenciaId(a)
                            const est = estadoTexto(asistenciaEstadoFromAny(a))
                            const puedeFirmarAsistencia =
                              est === "Ausente" || est === "Tarde"
                            const puedeDetalle = canEditAsistenciaDetalle
                            const detalleTexto =
                              a.detalle || a.observaciones || a.observacion || ""
                            const firmada = isFirmadaFromAny(a)
                            const firmadaEn = a?.firmada_en || a?.firmado_en || null

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
                                <td className="py-2 pr-4">
                                  {(() => {
                                    const statusClass =
                                      est === "Presente"
                                        ? "border border-emerald-300 bg-emerald-50 text-emerald-800"
                                        : est === "Tarde"
                                        ? "border border-amber-300 bg-amber-50 text-amber-800"
                                        : est === "Ausente"
                                        ? "border border-rose-200 bg-rose-50 text-rose-700"
                                        : "border border-slate-200 bg-slate-50 text-slate-700"

                                    return (
                                      <span
                                        className={`inline-flex items-center px-3 py-1 rounded-md text-sm font-medium ${statusClass}`}
                                      >
                                        {est}
                                      </span>
                                    )
                                  })()}
                                </td>
                                <td className="py-2 pr-4">
                                  {(() => {
                                    if (!puedeFirmarAsistencia) return "—"
                                    const just = isJustificadaFromAny(a)

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
                                  {canViewFirmaEstado && puedeFirmarAsistencia ? (
                                    firmada ? (
                                      <span className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-emerald-300 bg-emerald-50 text-emerald-800">
                                        Firmada {firmadaEn ? `- ${fmtFecha(firmadaEn)}` : ""}
                                      </span>
                                    ) : canSignByPadre ? (
                                      <button
                                        type="button"
                                        onClick={async () => {
                                          setSigningAsistenciaId(String(asistenciaId || rowId))
                                          const r = await firmarAsistencia(asistenciaId)
                                          setSigningAsistenciaId(null)
                                          if (!r.ok) {
                                            alert(
                                              r.data?.detail ||
                                                `Error (HTTP ${r.status || "?"})`
                                            )
                                            return
                                          }

                                          setAsistencias((prev) => {
                                            const list = Array.isArray(prev) ? prev : []
                                            const next = list.map((x) => {
                                              const xid = getAsistenciaId(x)
                                              if (String(xid) !== String(asistenciaId)) return x
                                              return {
                                                ...x,
                                                firmada: true,
                                                firmada_en:
                                                  r.data?.firmada_en || new Date().toISOString(),
                                              }
                                            })
                                            setCachedList(
                                              ASISTENCIAS_CACHE_PREFIX,
                                              alumnoCacheId,
                                              next
                                            )
                                            return next
                                          })
                                        }}
                                        disabled={
                                          signingAllAsistencias ||
                                          !asistenciaId ||
                                          String(signingAsistenciaId || "") ===
                                            String(asistenciaId || rowId)
                                        }
                                        className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-gray-300 bg-white text-gray-800 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
                                      >
                                        {String(signingAsistenciaId || "") ===
                                        String(asistenciaId || rowId)
                                          ? "Firmando..."
                                          : "Firmar"}
                                      </button>
                                    ) : (
                                      <span className="inline-flex items-center px-3 py-1 rounded-md text-sm font-medium border border-amber-300 bg-amber-50 text-amber-800">
                                        Pendiente
                                      </span>
                                    )
                                  ) : canViewFirmaEstado ? (
                                    "—"
                                  ) : (
                                    null
                                  )}
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
                                      className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-gray-200 text-gray-600 school-icon-button disabled:opacity-50 disabled:cursor-not-allowed"
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
        open={confirmFirmarTodoOpen}
        onOpenChange={(open) => {
          if (!signingAllNotas) setConfirmFirmarTodoOpen(open)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Firmar todo</DialogTitle>
            <DialogDescription>
              Vas a firmar todas las notas pendientes de este alumno. Esta acción no
              puede deshacerse.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Notas pendientes a firmar: {notasPendientesFirma.length}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmFirmarTodoOpen(false)}
              disabled={signingAllNotas}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleFirmarTodasNotas}
              disabled={signingAllNotas || notasPendientesFirma.length === 0}
              className="primary-button"
            >
              {signingAllNotas ? "Firmando..." : "Confirmar firma"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={confirmFirmarSancionesOpen}
        onOpenChange={(open) => {
          if (!signingAllSanciones) setConfirmFirmarSancionesOpen(open)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Firmar todo</DialogTitle>
            <DialogDescription>
              Vas a firmar todas las sanciones pendientes de este alumno. Esta acción
              no puede deshacerse.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Sanciones pendientes a firmar: {sancionesPendientesFirma.length}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmFirmarSancionesOpen(false)}
              disabled={signingAllSanciones}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleFirmarTodasSanciones}
              disabled={
                signingAllSanciones || sancionesPendientesFirma.length === 0
              }
              className="primary-button"
            >
              {signingAllSanciones ? "Firmando..." : "Confirmar firma"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={confirmFirmarAsistenciasOpen}
        onOpenChange={(open) => {
          if (!signingAllAsistencias) setConfirmFirmarAsistenciasOpen(open)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Firmar todo</DialogTitle>
            <DialogDescription>
              Vas a firmar todas las inasistencias pendientes de este alumno. Esta
              acción no puede deshacerse.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Inasistencias pendientes a firmar: {asistenciasPendientesFirma.length}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmFirmarAsistenciasOpen(false)}
              disabled={signingAllAsistencias}
            >
              Cancelar
            </Button>
            <Button
              onClick={handleFirmarTodasAsistencias}
              disabled={
                signingAllAsistencias || asistenciasPendientesFirma.length === 0
              }
              className="primary-button"
            >
              {signingAllAsistencias ? "Firmando..." : "Confirmar firma"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={notaModal.open}
        onOpenChange={(open) => (!open ? closeNotaModal() : null)}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Editar nota</DialogTitle>
            <DialogDescription>
              Modifica la calificación cargada para este alumno.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <Label>Materia</Label>
              <select
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                value={notaModal.materia}
                onChange={(e) => setNotaModal((prev) => ({ ...prev, materia: e.target.value }))}
              >
                <option value="">Seleccionar</option>
                {materiasCat.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label>Tipo</Label>
              <select
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                value={notaModal.tipo}
                onChange={(e) => setNotaModal((prev) => ({ ...prev, tipo: e.target.value }))}
              >
                <option value="">Seleccionar</option>
                {NOTA_TIPOS.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {tipo}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label>Calificación</Label>
              <select
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                value={notaModal.resultado}
                onChange={(e) => setNotaModal((prev) => ({ ...prev, resultado: e.target.value }))}
              >
                <option value="">Sin entregar</option>
                {NOTA_RESULTADOS.map((resultado) => (
                  <option key={resultado.value} value={resultado.value}>
                    {resultado.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label>Nota numérica</Label>
              <input
                type="number"
                step="0.01"
                min="1"
                max="10"
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                value={notaModal.nota_numerica}
                onChange={(e) =>
                  setNotaModal((prev) => ({ ...prev, nota_numerica: e.target.value }))
                }
              />
            </div>
            <div>
              <Label>Cuatrimestre</Label>
              <select
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                value={notaModal.cuatrimestre}
                onChange={(e) =>
                  setNotaModal((prev) => ({ ...prev, cuatrimestre: e.target.value }))
                }
              >
                <option value="1">1</option>
                <option value="2">2</option>
              </select>
            </div>
            <div>
              <Label>Fecha</Label>
              <input
                type="date"
                className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                value={notaModal.fecha}
                onChange={(e) => setNotaModal((prev) => ({ ...prev, fecha: e.target.value }))}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Comentarios</Label>
            <Textarea
              value={notaModal.observaciones}
              onChange={(e) =>
                setNotaModal((prev) => ({ ...prev, observaciones: e.target.value }))
              }
              className="min-h-[120px]"
              placeholder="Comentario opcional sobre la nota"
            />
            {notaModal.error ? (
              <p className="text-sm text-red-600">{notaModal.error}</p>
            ) : null}
          </div>
          <DialogFooter>
            <Button onClick={closeNotaModal}>Cancelar</Button>
            <Button onClick={handleGuardarNota} disabled={notaModal.saving}>
              {notaModal.saving ? "Guardando..." : "Guardar cambios"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
            <Button onClick={closeDetalleModal}>
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
  const session = useSessionContext()
  const school = session?.school
  const logoUrl = school?.logo_url || LOGO_SRC
  const schoolName = school?.short_name || school?.name || "Colegio"
  const headerStyle = school?.primary_color ? { backgroundColor: school.primary_color } : undefined

  return (
    <div className="text-white px-6 py-4" style={headerStyle}>
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="inline-flex">
            <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center overflow-hidden">
              <img
                src={logoUrl}
                alt={schoolName}
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
              className="text-white hover:bg-white/15 gap-2"
            >
              <ChevronLeft className="h-4 w-4" />
              {backToAlumnosHref ? "Volver a alumnos" : "Volver"}
            </Button>
          )}

          {/* Volver a cursos */}
          {showBackCursos && (
            <Link href="/alumnos" prefetch>
              <Button variant="ghost" className="text-white hover:bg-white/15 gap-2">
                <ChevronLeft className="h-4 w-4" />
                Volver a cursos
              </Button>
            </Link>
          )}

          {/* Volver al panel: siempre */}
          <Link href="/dashboard" prefetch>
            <Button variant="ghost" className="text-white hover:bg-white/15 gap-2">
              <ChevronLeft className="h-4 w-4" />
              Volver al panel
            </Button>
          </Link>

          <NotificationBell unreadCount={unreadCount} />

          <div className="relative">
            <Link href="/mensajes" prefetch>
              <Button variant="ghost" size="icon" className="text-white hover:bg-white/15">
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
              <Button variant="ghost" className="text-white hover:bg-white/15 gap-2">
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

