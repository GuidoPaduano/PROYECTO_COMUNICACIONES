"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, API_BASE } from "../_lib/auth"
import { useRouter } from "next/navigation"
import { notifyInboxChanged } from "../_lib/inbox" // ⬅️ EVENT bus para badges
import { NotificationBell } from "@/components/notification-bell"
import { useUnreadCount } from "../_lib/useUnreadCount"

import {
  Mail,
  User,
  ChevronDown,
  ChevronLeft,
  CheckCheck,
  Search,
  RefreshCcw, // ⬅️ Botón Actualizar
  Plus,
  CalendarDays,
  History,
  Reply,
  Trash2,
} from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import SuccessMessage from "@/components/ui/success-message"
import ComposeComunicadoFamilia from "./_compose-comunicado-familia"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

/* ======================== Utils ======================== */
function fmtFecha(input) {
  if (!input) return "—"
  const d1 = new Date(input)
  if (!isNaN(d1.getTime())) {
    return d1.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    })
  }
  const m = String(input).match(/(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})/)
  if (m) {
    const day = parseInt(m[1], 10)
    const mon = parseInt(m[2], 10) - 1
    const year = parseInt(m[3].length === 2 ? "20" + m[3] : m[3], 10)
    const d2 = new Date(year, mon, day)
    if (!isNaN(d2.getTime())) {
      return d2.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    }
  }
  return String(input)
}

function initials(name) {
  const s = String(name || "").trim()
  if (!s) return "✉️"
  const parts = s.split(/\s+/).slice(0, 2)
  return parts.map((p) => p[0]?.toUpperCase() || "").join("")
}

function preview(text, max = 160) {
  const t = String(text || "").replace(/\s+/g, " ").trim()
  if (t.length <= max) return t
  return t.slice(0, max - 1) + "..."
}

function stripRePrefix(s) {
  return String(s || "").replace(/^(\s*re\s*:\s*)+/i, "").trim()
}

function collapseRePrefix(s) {
  const base = stripRePrefix(s)
  if (!base) return ""
  const hasRe = /^\s*re\s*:/i.test(String(s || ""))
  return hasRe ? `Re: ${base}` : base
}

async function fetchJSON(url, opts) {
  const res = await authFetch(url, {
    ...opts,
    headers: { Accept: "application/json", ...(opts?.headers || {}) },
  })
  const ct = res.headers.get("content-type") || ""
  if (ct.includes("application/json")) {
    const data = await res.json().catch(() => ({}))
    return { ok: res.ok, status: res.status, data }
  }
  const text = await res.text()
  return { ok: res.ok, status: res.status, text }
}

/* ====== Parser HTML tolerante ====== */
function parseMensajesHTML(html) {
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(html, "text/html")

    const nodes = [
      ...doc.querySelectorAll(
        "ul li, .mensaje, .message, .list-group-item, article, .card, tr"
      ),
    ]

    const mensajes = []

    for (const el of nodes) {
      const text = (el.textContent || "").replace(/\s+/g, " ").trim()
      if (!text) continue

      const strong = el.querySelector(
        "strong, h1, h2, h3, h4, h5, h6, .asunto, .subject"
      )
      let asunto = strong ? (strong.textContent || "").trim() : ""

      let emisor = ""
      const emisorNode =
        el.querySelector(".emisor, .from, [data-emisor]") ||
        Array.from(el.querySelectorAll("small, .text-muted, .meta, span, div")).find(
          (n) => /(^|\s)(de|remitente)\s*:/i.test(n.textContent || "")
        )
      if (emisorNode) {
        const m = (emisorNode.textContent || "").match(
          /(?:de|remitente)\s*:\s*(.+)$/i
        )
        if (m) emisor = m[1].trim()
      }
      if (!emisor && strong && strong.nextSibling) {
        const tail = String(strong.nextSibling.textContent || "")
        const mm = tail.match(/-\s*de\s+(.+)/i)
        if (mm) emisor = mm[1].trim()
      }

      let fecha = ""
      const time = el.querySelector("time[datetime]") || el.querySelector("time")
      if (time) {
        fecha = time.getAttribute("datetime") || time.textContent || ""
      } else {
        const datePattern =
          /\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{4}\-\d{1,2}\-\d{1,2})\b/
        const m = text.match(datePattern)
        if (m) fecha = m[1]
      }

      let contenido = text
      if (asunto) {
        const idx = contenido.toLowerCase().indexOf(asunto.toLowerCase())
        if (idx >= 0) contenido = contenido.slice(idx + asunto.length).trim()
      }
      contenido = contenido.replace(/^(de|remitente)\s*:\s*.*?(\s|$)/i, "").trim()

      if (!asunto && contenido.length < 3) continue
      mensajes.push({ asunto: asunto || "Sin asunto", emisor, contenido, fecha })
    }

    const dedup = []
    const seen = new Set()
    for (const m of mensajes) {
      const key = [m.asunto, m.emisor, m.fecha, m.contenido.slice(0, 60)].join("||")
      if (!seen.has(key)) {
        seen.add(key)
        dedup.push(m)
      }
    }
    return dedup
  } catch {
    return []
  }
}

/* ====== Flag de NO LEÍDO para pintar fondo ====== */
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

/* ======================== Page ======================== */
export default function MensajesPage() {
  useAuthGuard()
  const router = useRouter()

  const [me, setMe] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [buscar, setBuscar] = useState("")
  const [mensajes, setMensajes] = useState([])

  const [traces, setTraces] = useState([])
  const [open, setOpen] = useState(false)
  const [msgSel, setMsgSel] = useState(null)
  const [verHiloLoading, setVerHiloLoading] = useState(false)

  // === Eliminar mensaje ===
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [deleteError, setDeleteError] = useState("")

  // === Responder ===
  const [replyMode, setReplyMode] = useState(false)
  const [replyAsunto, setReplyAsunto] = useState("")
  const [replyTexto, setReplyTexto] = useState("")
  const [replyErr, setReplyErr] = useState("")
  const [replyOk, setReplyOk] = useState("")
  const [replySending, setReplySending] = useState(false)

  const [reloadTick, setReloadTick] = useState(0)
  const [openSendPicker, setOpenSendPicker] = useState(false)
  const [newMsgOpen, setNewMsgOpen] = useState(false)
  const [composerMode, setComposerMode] = useState("familia")
  const [openAlumnoMsg, setOpenAlumnoMsg] = useState(false)
  const [loadingAlumnoMsg, setLoadingAlumnoMsg] = useState(false)
  const [alumnoMsgErr, setAlumnoMsgErr] = useState("")
  const [alumnoMsgOk, setAlumnoMsgOk] = useState("")
  const [destSel, setDestSel] = useState("")
  const [asuntoAlu, setAsuntoAlu] = useState("")
  const [contenidoAlu, setContenidoAlu] = useState("")
  const [destinatariosDoc, setDestinatariosDoc] = useState([])
  const [alumnoDestType, setAlumnoDestType] = useState("")
  const myId = me?.id ?? me?.user?.id

  const unreadCount = useUnreadCount()

  // ===== Loader único (mensajes + whoami) =====
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        setLoading(true)
        setError("")

        // whoami
        try {
          const r = await fetchJSON("/auth/whoami/")
          if (alive && r.ok) setMe(r.data)
        } catch {}

        const candidates = ["/mensajes/recibidos/", "/mensajes/listar/"]

        let list = null
        const tries = []
        for (const u of candidates) {
          try {
            const r = await fetchJSON(u)
            tries.push({ url: u, status: r.status, ok: r.ok })
            if (!r.ok) continue
            const arr = Array.isArray(r.data)
              ? r.data
              : Array.isArray(r.data?.results)
              ? r.data.results
              : Array.isArray(r.data?.mensajes)
              ? r.data.mensajes
              : null
            if (arr) {
              list = arr
              break
            }
          } catch {
            tries.push({ url: u, status: "ERR", ok: false })
          }
        }

        if (!list) {
          const ORIGIN = (API_BASE || "").replace(/\/?api\/?$/, "")
          try {
            const r = await fetch(`${ORIGIN}/ver_mensajes/`, {
              credentials: "include",
              headers: { Accept: "text/html" },
            })
            tries.push({
              url: `${ORIGIN}/ver_mensajes/`,
              status: r.status,
              ok: r.ok,
            })
            if (r.ok) {
              const html = await r.text()
              list = parseMensajesHTML(html)
            } else {
              list = []
            }
          } catch {
            tries.push({ url: `${ORIGIN}/ver_mensajes/`, status: "ERR", ok: false })
            list = []
          }
        }

        if (alive) {
          setMensajes(Array.isArray(list) ? list : [])
          setTraces(tries)
        }
      } catch (e) {
        if (alive) setError(e?.message || "No se pudieron cargar los mensajes.")
      } finally {
        if (alive) setLoading(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [reloadTick])

  // escuchar el evento global para refrescar cuando otro view cambie el inbox
  useEffect(() => {
    const handler = () => setReloadTick((t) => t + 1)
    window.addEventListener("inbox-changed", handler)
    return () => window.removeEventListener("inbox-changed", handler)
  }, [])

  const list = useMemo(() => {
    let arr = Array.isArray(mensajes) ? mensajes.slice() : []
    const q = buscar.trim().toLowerCase()
    if (q) {
      arr = arr.filter(
        (m) =>
          (m.asunto || "").toLowerCase().includes(q) ||
          (m.contenido || "").toLowerCase().includes(q) ||
          (m.emisor || "").toLowerCase().includes(q)
      )
    }
    arr.sort((a, b) => {
      const da = new Date(a.fecha || a.fecha_envio || 0).getTime()
      const db = new Date(b.fecha || b.fecha_envio || 0).getTime()
      return db - da
    })
    return arr
  }, [mensajes, buscar])

  async function marcarTodoLeido() {
    try {
      const r = await authFetch("/mensajes/marcar_todos_leidos/", { method: "POST" })
      if (r.ok) {
        setMensajes((prev) =>
          prev.map((x) => ({
            ...x,
            leido: true,
            leido_en: x.leido_en || new Date().toISOString(),
          }))
        )
        notifyInboxChanged()
        setReloadTick((t) => t + 1)
      }
    } catch {}
  }

  function pedirEliminar(m, ev) {
    try {
      ev?.stopPropagation?.()
    } catch {}
    setDeleteTarget(m || null)
    setDeleteError("")
    setDeleteOpen(true)
  }

  async function confirmarEliminar() {
    if (!deleteTarget?.id) {
      setDeleteOpen(false)
      setDeleteTarget(null)
      return
    }

    setDeleteLoading(true)
    setDeleteError("")

    try {
      let r = await authFetch(`/mensajes/${deleteTarget.id}/eliminar/`, { method: "DELETE" })

      if (!r.ok) {
        r = await authFetch(`/mensajes/${deleteTarget.id}/eliminar/`, { method: "POST" })
      }

      if (!r.ok) {
        const t = await r.text().catch(() => "")
        throw new Error(t || "No se pudo eliminar el mensaje.")
      }

      setMensajes((prev) => prev.filter((x) => x.id !== deleteTarget.id))

      setOpen((prevOpen) =>
        prevOpen && msgSel?.id === deleteTarget.id ? false : prevOpen
      )
      setMsgSel((prevSel) => (prevSel?.id === deleteTarget.id ? null : prevSel))

      setDeleteOpen(false)
      setDeleteTarget(null)

      notifyInboxChanged()
    } catch (e) {
      setDeleteError(e?.message || "Error al eliminar el mensaje.")
    } finally {
      setDeleteLoading(false)
    }
  }

  function abrirMensaje(m) {
    setMsgSel(m)
    setOpen(true)

    setReplyMode(false)
    setReplyErr("")
    setReplyOk("")
    setReplyTexto("")
    setReplyAsunto(m?.asunto ? `Re: ${stripRePrefix(m.asunto)}` : "Re:")

    try {
      const hasLeido = Object.prototype.hasOwnProperty.call(m, "leido")
      const hasLeidoEn = Object.prototype.hasOwnProperty.call(m, "leido_en")
      const hasFlags = hasLeido || hasLeidoEn
      const isMine = m?.receptor_id && myId && m.receptor_id === myId
      const isUnread =
        (hasLeido && m.leido === false) ||
        (hasLeidoEn && (m.leido_en === null || m.leido_en === undefined))
      if (hasFlags && isMine && isUnread && m?.id) {
        ;(async () => {
          const r = await fetchJSON(`/mensajes/${m.id}/marcar_leido/`, { method: "POST" })
          if (r.ok) {
            setMensajes((prev) =>
              prev.map((x) =>
                x.id === m.id
                  ? { ...x, leido: true, leido_en: x.leido_en || new Date().toISOString() }
                  : x
              )
            )
            notifyInboxChanged()
          }
        })()
      }
    } catch {}
  }

  async function handleVerHilo() {
    if (!msgSel) return
    if (msgSel.thread_id) {
      setOpen(false)
      router.push(`/mensajes/hilo/${msgSel.thread_id}`)
      return
    }
    if (!msgSel.id) return
    setVerHiloLoading(true)

    const candidates = [
      `/mensajes/conversacion/${msgSel.id}/`,
      `/mensajes/conversacion/${msgSel.id}`,
    ]

    let tid = null
    for (const url of candidates) {
      try {
        const r = await fetchJSON(url)
        if (r.ok && r.data?.thread_id) {
          tid = r.data.thread_id
          break
        }
      } catch {}
    }
    setVerHiloLoading(false)
    if (tid) {
      setOpen(false)
      router.push(`/mensajes/hilo/${tid}`)
    }
  }

  async function enviarRespuesta() {
    if (!msgSel?.id) {
      setReplyErr("No se puede responder este mensaje (no tiene identificador).")
      return
    }
    if (!replyTexto.trim()) {
      setReplyErr("Escribí un mensaje para responder.")
      return
    }

    setReplyErr("")
    setReplyOk("")
    setReplySending(true)

    const payload = {
      mensaje_id: msgSel.id,
      asunto: replyAsunto?.trim() || `Re: ${stripRePrefix(msgSel.asunto || "")}`.trim(),
      contenido: replyTexto.trim(),
    }

    const tries = ["/mensajes/responder/"]

    let ok = false,
      lastErr = "",
      threadId = null
    for (const url of tries) {
      try {
        const r = await authFetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        })
        if (r.ok) {
          try {
            const data = await r.json()
            threadId = data?.thread_id || msgSel?.thread_id || null
          } catch {}
          ok = true
          break
        }
        lastErr = `HTTP ${r.status}`
      } catch (e) {
        lastErr = e?.message || "Error de red"
      }
    }

    if (ok) {
      setReplyOk("✅ Respuesta enviada.")
      notifyInboxChanged()
      setTimeout(() => {
        setOpen(false)
        setReplyMode(false)
        setReplyTexto("")
        setReplyOk("")
        if (threadId) {
          router.push(`/mensajes/hilo/${threadId}`)
        } else {
          setReloadTick((t) => t + 1)
        }
      }, 700)
    } else {
      setReplyErr(`No se pudo enviar la respuesta. ${lastErr}`)
    }
    setReplySending(false)
  }

  const userLabel =
    (me?.full_name && String(me.full_name).trim()) ||
    me?.username ||
    [me?.user?.first_name, me?.user?.last_name].filter(Boolean).join(" ") ||
    ""

  const groups = Array.isArray(me?.groups)
    ? me.groups
    : Array.isArray(me?.grupos)
    ? me.grupos
    : []
  const isPreceptor = groups.includes("Preceptores") || groups.includes("Preceptor")
  const isAlumno = groups.includes("Alumnos") || groups.includes("Alumno")
  const isPadre = groups.includes("Padres") || groups.includes("Padre")
  const isAlumnoOrPadre = isAlumno || isPadre
  const cursosEndpoint = "/alumnos/cursos/"

  const debugFlag =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).has("debug")
  const showDebug =
    debugFlag &&
    unreadCount > 0 &&
    !loading &&
    !error &&
    (Array.isArray(list) ? list.length : 0) === 0

  const cursoChip = (msgSel?.curso_asociado || msgSel?.curso || "").toString().trim()
  const cursoSugeridoAlumno = me?.alumno?.curso || me?.curso || me?.user?.alumno?.curso || ""

  useEffect(() => {
    if (!openAlumnoMsg) return
    let alive = true
    setLoadingAlumnoMsg(true)
    setAlumnoMsgErr("")
    ;(async () => {
      try {
        const base = "/mensajes/destinatarios_docentes/"
        const withCurso = cursoSugeridoAlumno
          ? `${base}?curso=${encodeURIComponent(cursoSugeridoAlumno)}`
          : base
        const fallbacks = [withCurso, base, "/api/mensajes/destinatarios_docentes/"]
        let data = null
        for (const url of fallbacks) {
          try {
            const r = await authFetch(url, { headers: { Accept: "application/json" } })
            if (!r.ok) continue
            data = await r.json().catch(() => ({}))
            break
          } catch {}
        }

        let list = []
        if (Array.isArray(data?.profesores) || Array.isArray(data?.preceptores)) {
          const profs = Array.isArray(data?.profesores) ? data.profesores : []
          const precs = Array.isArray(data?.preceptores) ? data.preceptores : []
          list = [
            ...profs.map((u) => ({
              id: u.id,
              label: `${u.nombre || u.username || u.email} (Profesor)`,
              kind: "profesor",
            })),
            ...precs.map((u) => ({
              id: u.id,
              label: `${u.nombre || u.username || u.email} (Preceptor)`,
              kind: "preceptor",
            })),
          ]
        } else if (Array.isArray(data?.results)) {
          list = data.results.map((u) => ({
            id: u.id,
            label: `${u.nombre || u.username || u.email}`,
            kind: "docente",
          }))
        }

        if (alive) {
          const filtered =
            alumnoDestType === "profesor"
              ? list.filter((x) => x?.kind === "profesor")
              : alumnoDestType === "preceptor"
              ? list.filter((x) => x?.kind === "preceptor")
              : list
          setDestinatariosDoc(filtered.filter((x) => x?.id))
          if (filtered.length && !destSel) setDestSel(String(filtered[0].id))
        }
      } catch (e) {
        if (alive) setAlumnoMsgErr(e?.message || "No se pudieron cargar los destinatarios.")
      } finally {
        if (alive) setLoadingAlumnoMsg(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [openAlumnoMsg, cursoSugeridoAlumno, alumnoDestType, destSel])

  return (
    <div className="space-y-6">
      <div className="space-y-6">
        {showDebug && (
          <div className="mb-3 p-3 text-[12px] rounded-md border border-amber-300 bg-amber-50 text-amber-800">
            El contador indica mensajes no leídos, pero el listado quedó vacío.
            <div className="mt-2 font-mono whitespace-pre-wrap">
              {traces.map((t) => `• ${t.url} → ${t.status}${t.ok ? " ✅" : " ❌"}`).join("\n")}
            </div>
          </div>
        )}

        <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
          <CardContent className="p-6">
            {/* Acciones y búsqueda */}
            <div className="mb-4 grid grid-cols-1 sm:grid-cols-4 gap-3">
              <div className="sm:col-span-2">
                <Label htmlFor="buscar" className="text-xs text-gray-600">
                  Buscar
                </Label>
                <div className="mt-1 relative">
                  <input
                    id="buscar"
                    className="w-full border rounded-md px-3 py-2 text-sm bg-white pl-9"
                    placeholder="Asunto, contenido o emisor…"
                    value={buscar}
                    onChange={(e) => setBuscar(e.target.value)}
                  />
                  <Search className="h-4 w-4 text-gray-400 absolute left-2 top-1/2 -translate-y-1/2" />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 items-end sm:col-span-2">
                <Button
                  onClick={() => (isAlumnoOrPadre ? setOpenSendPicker(true) : setOpenSendPicker(true))}
                  className="w-full gap-2"
                >
                  <Plus className="h-4 w-4" />
                  Mensaje nuevo
                </Button>
                <Button
                  onClick={() => setReloadTick((t) => t + 1)}
                  className="w-full gap-2"
                >
                  <RefreshCcw className="h-4 w-4" />
                  Actualizar
                </Button>
                <Button onClick={marcarTodoLeido} className="w-full gap-2">
                  <CheckCheck className="h-4 w-4" />
                  Marcar todo leído
                </Button>
              </div>
            </div>

            {/* Lista */}
            {loading ? (
              <p className="text-sm text-gray-500">Cargando mensajes…</p>
            ) : error ? (
              <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm">
                {error}
              </div>
            ) : list.length === 0 ? (
              <div className="text-sm text-gray-600">No hay mensajes.</div>
            ) : (
              <div className="divide-y">
                {list.map((m, i) => (
                  <div
                    key={m.id || i}
                    role="button"
                    tabIndex={0}
                    onClick={() => abrirMensaje(m)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        abrirMensaje(m)
                      }
                    }}
                    className={[
                      "w-full text-left py-3 -mx-2 px-2 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400",
                      esNoLeido(m, myId)
                        ? "bg-[#eaf1ff] hover:bg-[#eaf1ff]/90"
                        : "hover:bg-gray-50",
                    ].join(" ")}
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-800 flex items-center justify-center font-semibold flex-shrink-0">
                        {initials(m.emisor)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            {esNoLeido(m, myId) && (
                              <span className="inline-block w-2 h-2 rounded-full bg-blue-500 flex-shrink-0" />
                            )}
                            <div
                              className={`truncate ${
                                esNoLeido(m, myId)
                                  ? "font-medium text-gray-900"
                                  : "text-gray-700"
                              }`}
                            >
                              {m.emisor || "—"}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <div className="text-xs text-gray-500">
                              {fmtFecha(m.fecha || m.fecha_envio)}
                            </div>
                            <button
                              type="button"
                              onClick={(e) => pedirEliminar(m, e)}
                              className="p-1 rounded-md border border-transparent bg-red-50/70 text-red-600 shadow-sm hover:bg-red-100 hover:text-red-700 hover:border-red-200"
                              title="Eliminar mensaje"
                              aria-label="Eliminar mensaje"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                        <div
                          className={`text-sm truncate ${
                            esNoLeido(m, myId) ? "font-semibold text-gray-900" : "text-gray-900"
                          }`}
                        >
                          {collapseRePrefix(m.asunto) || "Sin asunto"}
                        </div>
                        <div className="text-sm text-gray-600 mt-0.5 line-clamp-2 max-h-[3.2rem] overflow-hidden">
                          {preview(m.contenido || m.body || "")}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={openSendPicker} onOpenChange={setOpenSendPicker}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Enviar mensajes</DialogTitle>
            <DialogDescription>
              {isAlumnoOrPadre
                ? "Elegí si querés enviar a un profesor o preceptor."
                : "Elegí si querés enviar a un alumno en particular o a un curso entero."}
            </DialogDescription>
          </DialogHeader>

          {isAlumnoOrPadre ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => {
                  setOpenSendPicker(false)
                  setAlumnoDestType("profesor")
                  setTimeout(() => setOpenAlumnoMsg(true), 0)
                }}
                className="border rounded-xl p-4 text-left hover:border-blue-300 hover:bg-blue-50/60 transition"
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
                className="border rounded-xl p-4 text-left hover:border-blue-300 hover:bg-blue-50/60 transition"
              >
                <div className="text-sm font-semibold text-slate-900">Preceptores</div>
                <div className="text-xs text-slate-500 mt-1">Mensaje a un preceptor</div>
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <button
                type="button"
                onClick={() => {
                  setOpenSendPicker(false)
                  setComposerMode("alumno")
                  setTimeout(() => setNewMsgOpen(true), 0)
                }}
                className="border rounded-xl p-4 text-left hover:border-blue-300 hover:bg-blue-50/60 transition"
              >
                <div className="text-sm font-semibold text-slate-900">A un alumno</div>
                <div className="text-xs text-slate-500 mt-1">Mensaje individual a un alumno</div>
              </button>
              <button
                type="button"
                onClick={() => {
                  setOpenSendPicker(false)
                  setComposerMode("curso_alumnos")
                  setTimeout(() => setNewMsgOpen(true), 0)
                }}
                className="border rounded-xl p-4 text-left hover:border-blue-300 hover:bg-blue-50/60 transition"
              >
                <div className="text-sm font-semibold text-slate-900">A un curso</div>
                <div className="text-xs text-slate-500 mt-1">Mensaje grupal a un curso</div>
              </button>
              <button
                type="button"
                onClick={() => {
                  setOpenSendPicker(false)
                  setComposerMode("familia")
                  setTimeout(() => setNewMsgOpen(true), 0)
                }}
                className="border rounded-xl p-4 text-left hover:border-blue-300 hover:bg-blue-50/60 transition"
              >
                <div className="text-sm font-semibold text-slate-900">A la familia</div>
                <div className="text-xs text-slate-500 mt-1">Comunicado para padres o tutores</div>
              </button>
            </div>
          )}

          <div className="flex items-center justify-end pt-2">
            <Button onClick={() => setOpenSendPicker(false)}>Cerrar</Button>
          </div>
        </DialogContent>
      </Dialog>

      <ComposeComunicadoFamilia
        open={newMsgOpen}
        onOpenChange={setNewMsgOpen}
        cursosEndpoint={cursosEndpoint}
        defaultMode={composerMode}
        showModeSelect={false}
      />

      {/* ====== Modal alumno -> docentes/preceptores ====== */}
      <Dialog open={openAlumnoMsg} onOpenChange={setOpenAlumnoMsg}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Enviar mensaje</DialogTitle>
            <DialogDescription>
              {alumnoDestType === "profesor"
                ? "Elegí un profesor como destinatario."
                : alumnoDestType === "preceptor"
                ? "Elegí un preceptor como destinatario."
                : "Elegí un profesor o preceptor como destinatario."}
            </DialogDescription>
          </DialogHeader>

          {alumnoMsgErr && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-3">
              {alumnoMsgErr}
            </div>
          )}
          {alumnoMsgOk && <SuccessMessage className="mt-1">{alumnoMsgOk}</SuccessMessage>}

          <div className="grid gap-4">
            <div>
              <Label htmlFor="destSel">Destinatario</Label>
              <select
                id="destSel"
                className="mt-1 w-full border rounded-md px-3 py-2"
                value={destSel}
                onChange={(e) => {
                  setDestSel(e.target.value)
                  setAlumnoMsgErr("")
                }}
                disabled={loadingAlumnoMsg}
              >
                {!destinatariosDoc.length && (
                  <option value="">
                    {loadingAlumnoMsg ? "Cargando..." : "Sin destinatarios"}
                  </option>
                )}
                {destinatariosDoc.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="asuntoAlu">Asunto</Label>
              <Input
                id="asuntoAlu"
                className="mt-1"
                value={asuntoAlu}
                onChange={(e) => setAsuntoAlu(e.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="contenidoAlu">Mensaje</Label>
              <Textarea
                id="contenidoAlu"
                className="mt-1 min-h-[140px]"
                value={contenidoAlu}
                onChange={(e) => setContenidoAlu(e.target.value)}
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button onClick={() => setOpenAlumnoMsg(false)}>Cancelar</Button>
            <Button
              onClick={async () => {
                if (!destSel) return setAlumnoMsgErr("Elegí un destinatario.")
                if (!asuntoAlu.trim()) return setAlumnoMsgErr("Completá el asunto.")
                if (!contenidoAlu.trim()) return setAlumnoMsgErr("Escribí el mensaje.")
                setAlumnoMsgErr("")
                setAlumnoMsgOk("")

                const cursoSugerido =
                  me?.alumno?.curso || me?.curso || me?.user?.alumno?.curso || ""
                const payload = {
                  receptor_id: Number(destSel),
                  asunto: asuntoAlu.trim(),
                  contenido: contenidoAlu.trim(),
                  ...(cursoSugerido ? { curso: cursoSugerido } : {}),
                }

                const tries = [
                  "/mensajes/alumno/enviar/",
                  "/api/mensajes/alumno/enviar/",
                  "/mensajes/enviar/",
                  "/api/mensajes/enviar/",
                ]

                let sent = false
                let lastErr = ""
                for (const url of tries) {
                  try {
                    const r = await authFetch(url, {
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
                    window.dispatchEvent(new Event("inbox-changed"))
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
              }}
            >
              Enviar
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* ===================== MODAL LECTURA (REDISEÑADO) ===================== */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-3xl p-0 overflow-hidden">
          <DialogHeader className="px-6 pt-6 pb-4">
            <DialogTitle className="text-lg sm:text-xl font-semibold pr-10 break-words">
              {collapseRePrefix(msgSel?.asunto) || "Mensaje"}
            </DialogTitle>

            <DialogDescription className="mt-3">
              <div className="flex flex-wrap items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-50 border flex items-center justify-center font-semibold text-blue-800">
                  {initials(msgSel?.emisor)}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full border bg-white text-sm text-gray-800">
                    <User className="h-4 w-4 text-gray-500" />
                    {msgSel?.emisor || "—"}
                  </span>

                  <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full border bg-white text-sm text-gray-700">
                    <CalendarDays className="h-4 w-4 text-gray-500" />
                    {fmtFecha(msgSel?.fecha || msgSel?.fecha_envio)}
                  </span>

                  {cursoChip && (
                    <span className="inline-flex items-center px-3 py-1 rounded-full border bg-white text-sm text-gray-700">
                      {cursoChip}
                    </span>
                  )}
                </div>
              </div>
            </DialogDescription>
          </DialogHeader>

          <div className="h-px bg-gray-200" />

          <div className="px-6 py-5">
            <Label className="text-xs text-gray-600">Mensaje</Label>
            <div className="mt-2 rounded-lg border bg-gray-50 p-4 text-gray-900 whitespace-pre-wrap break-words max-h-[42vh] overflow-auto">
              {msgSel?.contenido || msgSel?.body || "—"}
            </div>

            {!replyMode && msgSel?.id && (
              <div className="mt-3 text-xs text-gray-500">
                Tip: abrí el historial para responder con contexto.
              </div>
            )}

            {!msgSel?.id && (
              <div className="mt-3 text-xs text-gray-500">
                Este mensaje proviene de una vista HTML; no admite respuesta directa.
              </div>
            )}
          </div>

          {replyMode && (
            <>
              <div className="h-px bg-gray-200" />
              <div className="px-6 py-5 bg-white">
                <div className="flex items-center gap-2 mb-3">
                  <Reply className="h-4 w-4 text-gray-500" />
                  <div className="text-sm font-medium text-gray-900">Respuesta</div>
                </div>

                {replyErr && <div className="mb-3 text-sm text-red-600">{replyErr}</div>}
                {replyOk && <SuccessMessage className="mb-3">{replyOk}</SuccessMessage>}

                <div className="space-y-4">
                  <div>
                    <Label htmlFor="replyAsunto">Asunto</Label>
                    <Input
                      id="replyAsunto"
                      value={replyAsunto}
                      onChange={(e) => setReplyAsunto(e.target.value)}
                    />
                  </div>

                  <div>
                    <Label htmlFor="replyTexto">Mensaje</Label>
                    <Textarea
                      id="replyTexto"
                      value={replyTexto}
                      onChange={(e) => setReplyTexto(e.target.value)}
                      rows={6}
                      className="whitespace-pre-wrap"
                    />
                  </div>
                </div>
              </div>
            </>
          )}

          <div className="h-px bg-gray-200" />

          <div className="px-6 py-4 flex items-center justify-end gap-2 bg-white">
            {msgSel?.id && (
              <Button
                onClick={handleVerHilo}
                disabled={verHiloLoading}
                className="gap-2"
              >
                <History className="h-4 w-4" />
                {verHiloLoading ? "Abriendo…" : "Ver mensajes anteriores"}
              </Button>
            )}

            <Button onClick={() => setOpen(false)}>
              Cerrar
            </Button>

            <Button onClick={() => setReplyMode((v) => !v)} disabled={!msgSel?.id} className="gap-2">
              <Reply className="h-4 w-4" />
              {replyMode ? "Cancelar" : "Responder"}
            </Button>

            {replyMode && (
              <Button onClick={enviarRespuesta} disabled={replySending} className="ml-2">
                {replySending ? "Enviando…" : "Enviar"}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      
{/* ===================== MODAL ELIMINAR ===================== */}
<Dialog
  open={deleteOpen}
  onOpenChange={(v) => {
    setDeleteOpen(v)
    if (!v) setDeleteTarget(null)
  }}
>
  <DialogContent
    className="p-6 text-center"
    style={{ width: "90vw", maxWidth: "360px" }}
  >
    <DialogHeader className="items-center text-center">
      <DialogTitle className="text-center">Eliminar mensaje</DialogTitle>
      <DialogDescription className="text-center">
        ¿Seguro que quieres eliminar el mensaje?
      </DialogDescription>
    </DialogHeader>

    {deleteError && (
      <div className="mt-2 text-sm text-red-600 text-center">{deleteError}</div>
    )}

    <div className="mt-6 flex items-center justify-center gap-3">
      <Button
        type="button"
        onClick={() => {
          setDeleteOpen(false)
          setDeleteTarget(null)
        }}
        className="min-w-[110px]"
        disabled={deleteLoading}
      >
        Cancelar
      </Button>

      <Button
        type="button"
        onClick={confirmarEliminar}
        disabled={deleteLoading}
        className="min-w-[110px]"
      >
        {deleteLoading ? "Eliminando..." : "Eliminar"}
      </Button>
    </div>
  </DialogContent>
</Dialog>
    </div>
  )
}

/* ======================== Topbar ======================== */
function Topbar({ userLabel, unreadCount }) {
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
          <h1 className="text-xl font-semibold">Mensajes</h1>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/dashboard">
            <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
              <ChevronLeft className="h-4 w-4" />
              Volver al panel
            </Button>
          </Link>

          {/* Campanita con menú de notificaciones */}
          <NotificationBell unreadCount={unreadCount} />

          {/* Mail con badge */}
          <div className="relative">
            <Link href="/mensajes">
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
                <User className="h-4 w-4" />
                {userLabel}
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuItem asChild className="text-sm">
                <Link href="/perfil">
                  <div className="flex items-center">
                    <User className="h-4 w-4 mr-2" />
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

