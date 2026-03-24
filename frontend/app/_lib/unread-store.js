"use client"

import { authFetch } from "./auth"
import { INBOX_EVENT } from "./inbox"

const state = {
  messages: 0,
  notifications: 0,
  total: 0,
}

const listeners = new Set()
let started = false
let timer = null
let inflight = null
let unsubscribeBrowser = null

function emit() {
  for (const listener of listeners) {
    try {
      listener({ ...state })
    } catch {}
  }
}

async function fetchCountFrom(paths) {
  for (const p of paths) {
    try {
      const sep = p.includes("?") ? "&" : "?"
      const url = `${p}${sep}t=${Date.now()}`
      const res = await authFetch(url, { cache: "no-store" })
      if (!res.ok) continue
      const j = await res.json().catch(() => ({}))
      if (typeof j?.count === "number") return j.count
    } catch {}
  }
  return 0
}

async function refreshUnread() {
  if (inflight) return inflight

  inflight = (async () => {
    try {
      const [messages, notifications] = await Promise.all([
        fetchCountFrom(["/mensajes/unread_count/", "/api/mensajes/unread_count/"]),
        fetchCountFrom(["/notificaciones/unread_count/", "/api/notificaciones/unread_count/"]),
      ])

      const next = {
        messages: Number(messages || 0),
        notifications: Number(notifications || 0),
      }
      next.total = next.messages + next.notifications

      if (
        next.messages !== state.messages ||
        next.notifications !== state.notifications ||
        next.total !== state.total
      ) {
        state.messages = next.messages
        state.notifications = next.notifications
        state.total = next.total
        emit()
      }
    } finally {
      inflight = null
    }
  })()

  return inflight
}

function setupBrowserListeners() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return () => {}
  }

  const onInboxChanged = () => refreshUnread()
  const onFocus = () => refreshUnread()
  const onVisibility = () => {
    if (document.visibilityState === "visible") refreshUnread()
  }

  window.addEventListener(INBOX_EVENT, onInboxChanged)
  window.addEventListener("focus", onFocus)
  document.addEventListener("visibilitychange", onVisibility)

  return () => {
    window.removeEventListener(INBOX_EVENT, onInboxChanged)
    window.removeEventListener("focus", onFocus)
    document.removeEventListener("visibilitychange", onVisibility)
  }
}

function startStore() {
  if (started) return
  started = true
  unsubscribeBrowser = setupBrowserListeners()
  refreshUnread()
  timer = setInterval(refreshUnread, 60000)
}

function stopStore() {
  if (!started || listeners.size > 0) return
  started = false
  if (timer) clearInterval(timer)
  timer = null
  if (unsubscribeBrowser) unsubscribeBrowser()
  unsubscribeBrowser = null
}

export function subscribeUnread(listener) {
  listeners.add(listener)
  startStore()
  listener({ ...state })

  return () => {
    listeners.delete(listener)
    stopStore()
  }
}

export function getUnreadSnapshot() {
  return { ...state }
}

export function requestUnreadRefresh() {
  return refreshUnread()
}
