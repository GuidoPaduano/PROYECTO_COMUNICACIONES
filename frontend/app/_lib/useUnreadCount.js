"use client"

import { useEffect, useRef, useState } from "react"
import { authFetch } from "./auth"
import { INBOX_EVENT } from "./inbox"

/**
 * Hook reutilizable para traer la cantidad de NO leídos (mensajes + notificaciones)
 * y mantenerla actualizada.
 *
 * - Poll cada 60s
 * - Evento global INBOX_EVENT (cuando se marca leído / llega algo nuevo)
 * - Refresco extra al volver a la pestaña (focus/visibilitychange)
 *
 * Nota: forzamos NO-CACHE porque el browser puede cachear GET y dejar el badge “pegado”.
 */
export function useUnreadCount() {
  const [unreadCount, setUnreadCount] = useState(0)
  const lastSetRef = useRef(null)

  useEffect(() => {
    let alive = true
    let timer = null

    const fetchCountFrom = async (paths) => {
      for (const p of paths) {
        try {
          // cache-busting + no-store (doble cinturón, por las dudas)
          const sep = p.includes("?") ? "&" : "?"
          const url = `${p}${sep}t=${Date.now()}`
          const res = await authFetch(url, { cache: "no-store" })
          if (!res.ok) continue
          const j = await res.json().catch(() => ({}))
          if (typeof j?.count === "number") return j.count
        } catch {
          // seguimos probando otras rutas
        }
      }
      return 0
    }

    const loadUnread = async () => {
      try {
        const [mensajes, notifs] = await Promise.all([
          fetchCountFrom(["/mensajes/unread_count/", "/api/mensajes/unread_count/"]),
          fetchCountFrom(["/notificaciones/unread_count/", "/api/notificaciones/unread_count/"]),
        ])

        const total = Number(mensajes || 0) + Number(notifs || 0)

        if (!alive) return

        // Evitar renders extra si no cambió
        if (lastSetRef.current !== total) {
          lastSetRef.current = total
          setUnreadCount(total)
        }
      } catch {
        // no rompemos la UI por este error
      }
    }

    // Primer load
    loadUnread()

    // Poll
    timer = setInterval(loadUnread, 60000)

    // Evento global
    const onInboxChanged = () => loadUnread()

    // Refrescos “humanos”
    const onFocus = () => loadUnread()
    const onVisibility = () => {
      if (document.visibilityState === "visible") loadUnread()
    }

    if (typeof window !== "undefined") {
      window.addEventListener(INBOX_EVENT, onInboxChanged)
      window.addEventListener("focus", onFocus)
      document.addEventListener("visibilitychange", onVisibility)
    }

    return () => {
      alive = false
      if (timer) clearInterval(timer)
      if (typeof window !== "undefined") {
        window.removeEventListener(INBOX_EVENT, onInboxChanged)
        window.removeEventListener("focus", onFocus)
        document.removeEventListener("visibilitychange", onVisibility)
      }
    }
  }, [])

  return unreadCount
}
