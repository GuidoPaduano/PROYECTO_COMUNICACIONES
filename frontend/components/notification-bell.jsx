// frontend/components/notification-bell.jsx
"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { Bell } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import { authFetch } from "@/app/_lib/auth"
import { INBOX_EVENT } from "@/app/_lib/inbox"

/**
 * Campanita reutilizable (NOTIFICACIONES del sistema).
 *
 * - items: opcional. Si se provee, se usa como lista y el badge usa unreadCount.
 * - unreadCount: solo se usa cuando `items` viene seteado (modo controlado).
 *
 * Si NO se provee `items`, la campanita:
 * - calcula su propio contador desde /notificaciones/unread_count/
 * - trae un preview desde /notificaciones/recientes/?solo_no_leidas=1
 */
export function NotificationBell({ unreadCount = 0, items = null, maxPreview = 5 }) {
  const router = useRouter()
  const [autoItems, setAutoItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [notifCount, setNotifCount] = useState(0)
  const [markAllLoading, setMarkAllLoading] = useState(false)

  const shownItems = useMemo(() => {
    return Array.isArray(items) ? items : autoItems
  }, [items, autoItems])

  const badgeCount = Array.isArray(items) ? Number(unreadCount || 0) : Number(notifCount || 0)

  function normalizeText(s) {
    return String(s || "")
      .replace(/\s+/g, " ")
      .trim()
  }

  function removeISODateSuffix(s) {
    // Quita sufijos de fecha comunes al final del texto.
    // Ejemplos: " — 2026-01-13", " - 13/01/2026", " — 13-01-2026"
    return String(s || "")
      .replace(/\s*[—-]\s*\d{4}-\d{2}-\d{2}\s*$/g, "")
      .replace(/\s*[—-]\s*\d{2}[\/-]\d{2}[\/-]\d{4}\s*$/g, "")
      .replace(/\s*[—-]\s*\d{2}[\/-]\d{2}[\/-]\d{2}\s*$/g, "")
      .trim()
  }

  function truncate(s, n = 90) {
    const t = normalizeText(s)
    if (t.length <= n) return t
    return t.slice(0, n - 1).trimEnd() + "…"
  }

  function buildTitle(obj) {
    const a = removeISODateSuffix(normalizeText((obj?.titulo || obj?.asunto) || ""))

    if (a.toLowerCase().startsWith("nueva sanción para ")) {
      const nombre = a.slice("nueva sanción para ".length).trim()
      if (nombre) return `${nombre} recibió una sanción`
    }

    if (a.toLowerCase().startsWith("nueva nota para ")) {
      const nombre = a.slice("nueva nota para ".length).trim()
      if (nombre) return `${nombre} recibió una nota`
    }

    if (a.toLowerCase().startsWith("nuevas notas para ")) {
      const nombre = a.slice("nuevas notas para ".length).trim()
      if (nombre) return `${nombre} recibió nuevas notas`
    }

    return a || "Notificación"
  }

  function buildDescription(obj) {
    // A veces el backend manda una línea "Fecha: ..." o agrega la fecha al final.
    // La limpiamos para que la notificación sea compacta y consistente.
    const raw = String((obj?.descripcion ?? obj?.contenido) || "")
    const c = removeISODateSuffix(
      normalizeText(
        raw
          .replace(/^\s*Fecha\s*:\s*.*$/gim, "")
          .replace(/^\s*Fecha\s*de\s*la\s*nota\s*:\s*.*$/gim, "")
      )
    )

    const m = c.match(/^\s*Motivo:\s*(.+)$/im)
    if (m && m[1]) {
      const clean = removeISODateSuffix(normalizeText(m[1]))
      return truncate(clean, 100)
    }

    const cal = c.match(/^\s*Calificación:\s*(.+)$/im)
    if (cal && cal[1]) {
      const clean = removeISODateSuffix(normalizeText(`Calificación: ${cal[1]}`))
      return truncate(clean, 100)
    }

    const bullet = c.match(/^\s*•\s*(.+)$/m)
    if (bullet && bullet[1]) {
      const clean = removeISODateSuffix(normalizeText(bullet[1]))
      return truncate(clean, 100)
    }

    const cleanFallback = removeISODateSuffix(normalizeText(c))
    return truncate(cleanFallback, 100)
  }

  function buildHref(obj) {
    // 1) Notificaciones del sistema traen url directa.
    const direct = obj?.url
    if (direct) return direct

    // 2) Fallback por tipo/meta (por si el backend manda versiones viejas)
    const tipo = String(obj?.tipo || "").toLowerCase().trim()
    const alumnoId = obj?.meta?.alumno_id ?? obj?.alumno_id ?? null
    if (alumnoId && (tipo === "nota" || tipo === "sancion" || tipo === "asistencia")) {
      const tab = tipo === "nota" ? "notas" : tipo === "sancion" ? "sanciones" : "asistencias"
      return `/alumnos/${alumnoId}/?tab=${tab}`
    }

    // 3) Mensajes: ir al hilo
    const tid = obj?.thread_id
    if (tid) return `/mensajes/hilo/${tid}`
    const id = obj?.id
    if (id != null) return `/mensajes/hilo/${id}`
    return "/mensajes"
  }

  async function fetchJSON(url) {
    // cache-busting + no-store (evita que el badge quede “pegado” por cache HTTP)
    const sep = String(url).includes("?") ? "&" : "?"
    const finalUrl = `${url}${sep}t=${Date.now()}`
    const res = await authFetch(finalUrl, { cache: "no-store" })
    const data = await res.json().catch(() => null)
    return { ok: res.ok, status: res.status, data }
  }

  async function markNotifRead(notifId) {
    const urls = [
      `/notificaciones/${notifId}/marcar_leida/`,
      `/api/notificaciones/${notifId}/marcar_leida/`,
      `/notificaciones/${notifId}/marcar_leida`,
      `/api/notificaciones/${notifId}/marcar_leida`,
    ]

    for (const u of urls) {
      try {
        const r = await authFetch(u, { method: "POST" })
        if (r.ok) break
      } catch {
        // seguimos
      }
    }

    try {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(INBOX_EVENT))
      }
    } catch {
      // ignore
    }
  }

  async function markAllNotifsRead() {
    setMarkAllLoading(true)

    const urls = [
      "/notificaciones/marcar_todas_leidas/",
      "/api/notificaciones/marcar_todas_leidas/",
      "/notificaciones/marcar_todas_leidas",
      "/api/notificaciones/marcar_todas_leidas",
    ]

    try {
      for (const u of urls) {
        try {
          const r = await authFetch(u, { method: "POST" })
          if (r.ok) break
        } catch {
          // seguimos
        }
      }

      // UI: bajar badge y limpiar preview
      if (!Array.isArray(items)) {
        setNotifCount(0)
        setAutoItems([])
      }

      try {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event(INBOX_EVENT))
        }
      } catch {
        // ignore
      }
    } finally {
      setMarkAllLoading(false)
    }
  }

  async function markMensajeRead(mensajeId) {
    const urls = [
      `/mensajes/${mensajeId}/marcar_leido/`,
      `/api/mensajes/${mensajeId}/marcar_leido/`,
      `/mensajes/${mensajeId}/marcar_leido`,
      `/api/mensajes/${mensajeId}/marcar_leido`,
    ]

    for (const u of urls) {
      try {
        const r = await authFetch(u, { method: "POST" })
        if (r.ok) break
      } catch {
        // seguimos
      }
    }

    try {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(INBOX_EVENT))
      }
    } catch {
      // ignore
    }
  }

  async function markAllNotifsRead() {
    if (Array.isArray(items)) {
      // Modo controlado: no podemos mutar items, pero igual intentamos marcar en backend.
    }

    if (markAllLoading) return
    setMarkAllLoading(true)

    const urls = [
      "/notificaciones/marcar_todas_leidas/",
      "/api/notificaciones/marcar_todas_leidas/",
      "/notificaciones/marcar_todas_leidas",
      "/api/notificaciones/marcar_todas_leidas",
    ]

    let ok = false
    for (const u of urls) {
      try {
        const r = await authFetch(u, { method: "POST" })
        if (r.ok) {
          ok = true
          break
        }
      } catch {
        // seguimos
      }
    }

    if (ok) {
      // Bajamos el badge al toque.
      setNotifCount(0)
      setAutoItems((prev) => prev.map((x) => ({ ...x, unread: false })))

      try {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event(INBOX_EVENT))
        }
      } catch {
        // ignore
      }

      // Refrescamos preview para que no queden items viejos visibles.
      try {
        await loadNotifCount()
        await loadPreview()
      } catch {
        // ignore
      }
    }

    setMarkAllLoading(false)
  }

  async function handleOpen(item) {
    const href = item?.href || "/mensajes"

    // Marcamos como leído ANTES de navegar (best-effort) para que el contador baje al toque.
    try {
      if (item?.kind === "notificacion" && item?.unread && item?.id != null) {
        await markNotifRead(item.id)
        setAutoItems((prev) =>
          prev.map((x) => (x.kind === "notificacion" && x.id === item.id ? { ...x, unread: false } : x))
        )
      }

      if (item?.kind === "mensaje" && item?.unread && item?.id != null) {
        await markMensajeRead(item.id)
        setAutoItems((prev) =>
          prev.map((x) => (x.kind === "mensaje" && x.id === item.id ? { ...x, unread: false } : x))
        )
      }
    } catch {
      // no frenamos navegación por esto
    }

    router.push(href)
  }

  async function loadNotifCount() {
    if (Array.isArray(items)) return

    const urls = [
      "/notificaciones/unread_count/",
      "/api/notificaciones/unread_count/",
      "/notificaciones/unread_count",
      "/api/notificaciones/unread_count",
    ]

    for (const u of urls) {
      try {
        const sep = u.includes("?") ? "&" : "?"
        const finalUrl = `${u}${sep}t=${Date.now()}`
        const res = await authFetch(finalUrl, { cache: "no-store" })
        if (!res.ok) continue
        const j = await res.json().catch(() => ({}))
        if (typeof j?.count === "number") {
          setNotifCount(Number(j.count || 0))
          return
        }
      } catch {
        // seguimos
      }
    }

    // fallback seguro
    setNotifCount(0)
  }

  async function loadPreview() {
    if (Array.isArray(items)) return

    setLoading(true)
    try {
      const limit = Math.max(1, Math.min(Number(maxPreview) || 5, 12))
      const urls = [
        `/notificaciones/recientes/?solo_no_leidas=1&limit=${limit}`,
        `/api/notificaciones/recientes/?solo_no_leidas=1&limit=${limit}`,
        `/notificaciones/recientes?solo_no_leidas=1&limit=${limit}`,
        `/api/notificaciones/recientes?solo_no_leidas=1&limit=${limit}`,
      ]

      let list = null
      for (const u of urls) {
        try {
          const r = await fetchJSON(u)
          if (!r.ok) continue
          if (Array.isArray(r.data)) {
            list = r.data
            break
          }
          if (Array.isArray(r.data?.mensajes)) {
            list = r.data.mensajes
            break
          }
        } catch {
          // seguimos
        }
      }

      if (!Array.isArray(list)) {
        setAutoItems([])
        return
      }

      const mapped = list.slice(0, limit).map((obj) => {
        const unread = !Boolean(obj?.leida)
        const href = buildHref(obj)

        return {
          id: obj?.id ?? `${Math.random()}`,
          kind: "notificacion",
          unread,
          title: buildTitle(obj),
          description: buildDescription(obj),
          href,
        }
      })

      setAutoItems(mapped)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let timer = null
    let alive = true

    const run = async () => {
      if (!alive) return
      await loadNotifCount()
      await loadPreview()
    }

    run()
    timer = setInterval(run, 60000)

    const handler = () => run()
    if (typeof window !== "undefined") {
      window.addEventListener(INBOX_EVENT, handler)
    }

    return () => {
      alive = false
      if (timer) clearInterval(timer)
      if (typeof window !== "undefined") {
        window.removeEventListener(INBOX_EVENT, handler)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, maxPreview])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative text-white hover:bg-white/15">
          <Bell className="h-5 w-5" />
          {badgeCount > 0 && (
            <span className="absolute -top-1 -right-1 text-[10px] px-1.5 py-0.5 rounded-full bg-red-600 text-white border border-white">
              {badgeCount > 99 ? "99+" : badgeCount}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        side="right"
        align="start"
        sideOffset={12}
        className="w-96 p-2"
      >
        <DropdownMenuLabel className="px-2">Notificaciones</DropdownMenuLabel>
        <DropdownMenuSeparator />

        {shownItems.length === 0 ? (
          <div className="px-2 py-2 text-sm text-gray-500">
            {loading ? "Cargando…" : "No tenés notificaciones por ahora."}
          </div>
        ) : (
          shownItems.map((n, idx) => {
            const isLast = idx === shownItems.length - 1
            return (
              <DropdownMenuItem
                key={`${n.kind}-${n.id}`}
                onSelect={(e) => {
                  e.preventDefault()
                  handleOpen(n)
                }}
                className="p-0 cursor-pointer focus:bg-transparent"
              >
                <div
                  className={
                    // "Tarjetita" para que no queden todas pegadas.
                    "w-full flex gap-3 px-3 py-3 items-start text-left rounded-xl border border-gray-200 bg-white shadow-sm " +
                    "hover:bg-gray-50 focus:bg-gray-50 " +
                    (isLast ? "" : "mb-2")
                  }
                >
                  {/* Puntito azul solo si está no leído */}
                  <span
                    className={
                      "mt-1.5 h-2 w-2 rounded-full flex-none " +
                      (n.unread ? "bg-blue-600" : "bg-transparent")
                    }
                  />

                  <div className="min-w-0 flex-1 flex flex-col gap-1 text-left">
                    <span className="w-full text-sm font-medium leading-snug">{n.title}</span>
                    {n.description && (
                      <span className="w-full text-xs text-gray-500 leading-snug">{n.description}</span>
                    )}
                  </div>
                </div>
              </DropdownMenuItem>
            )
          })
        )}

        <DropdownMenuSeparator />

        <div className="px-2 py-1 flex items-center justify-between gap-2">
          <Link href="/mensajes" className="text-sm font-medium hover:underline">
            Ver bandeja de mensajes
          </Link>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={markAllNotifsRead}
            disabled={markAllLoading || badgeCount === 0}
            className="h-8"
          >
            {markAllLoading ? "Marcando…" : "Marcar todas leídas"}
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
