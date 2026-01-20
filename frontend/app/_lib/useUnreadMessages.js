"use client"

import { useEffect, useRef, useState } from "react"
import { authFetch } from "./auth"
import { INBOX_EVENT } from "./inbox"

/**
 * Hook para traer la cantidad de mensajes NO leidos y mantenerla actualizada.
 *
 * - Poll cada 60s
 * - Evento global INBOX_EVENT
 * - Refresco al volver a la pestaña (focus/visibilitychange)
 */
export function useUnreadMessages() {
  const [unreadCount, setUnreadCount] = useState(0)
  const lastSetRef = useRef(null)

  useEffect(() => {
    let alive = true
    let timer = null

    const fetchCountFrom = async (paths) => {
      for (const p of paths) {
        try {
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
        const mensajes = await fetchCountFrom([
          "/mensajes/unread_count/",
          "/api/mensajes/unread_count/",
        ])
        const total = Number(mensajes || 0)

        if (!alive) return
        if (lastSetRef.current !== total) {
          lastSetRef.current = total
          setUnreadCount(total)
        }
      } catch {
        // no rompemos la UI por este error
      }
    }

    loadUnread()
    timer = setInterval(loadUnread, 60000)

    const onInboxChanged = () => loadUnread()
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
