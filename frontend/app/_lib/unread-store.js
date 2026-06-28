"use client"

import { authFetch } from "./auth"
import { INBOX_EVENT, INBOX_STORAGE_KEY } from "./inbox"

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
let ws = null
let wsReconnectTimer = null
let wsConnected = false

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
        fetchCountFrom(["/api/mensajes/unread_count/"]),
        fetchCountFrom(["/api/notificaciones/unread_count/"]),
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

// ── WebSocket ──────────────────────────────────────────────────────────────

function buildWsUrl() {
  if (typeof window === "undefined") return null
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/notificaciones/`
}

function connectWebSocket() {
  if (typeof window === "undefined" || ws) return

  const url = buildWsUrl()
  if (!url) return

  try {
    ws = new WebSocket(url)

    ws.addEventListener("open", () => {
      wsConnected = true
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer)
        wsReconnectTimer = null
      }
    })

    ws.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data)
        if (typeof data?.messages === "number" || typeof data?.notifications === "number") {
          const next = {
            messages: typeof data.messages === "number" ? data.messages : state.messages,
            notifications: typeof data.notifications === "number" ? data.notifications : state.notifications,
          }
          next.total = next.messages + next.notifications
          if (
            next.messages !== state.messages ||
            next.notifications !== state.notifications
          ) {
            state.messages = next.messages
            state.notifications = next.notifications
            state.total = next.total
            emit()
          }
        }
      } catch {}
    })

    ws.addEventListener("close", () => {
      wsConnected = false
      ws = null
      // Reconnect after 5s if store is still active
      if (started) {
        wsReconnectTimer = setTimeout(connectWebSocket, 5000)
      }
    })

    ws.addEventListener("error", () => {
      ws?.close()
    })
  } catch {}
}

function disconnectWebSocket() {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
  wsConnected = false
}

// ── Browser event listeners ────────────────────────────────────────────────

function setupBrowserListeners() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return () => {}
  }

  const onInboxChanged = () => refreshUnread()
  const onStorage = (event) => {
    if (event.key === INBOX_STORAGE_KEY) refreshUnread()
  }
  const onFocus = () => refreshUnread()
  const onVisibility = () => {
    if (document.visibilityState === "visible") refreshUnread()
  }

  window.addEventListener(INBOX_EVENT, onInboxChanged)
  window.addEventListener("storage", onStorage)
  window.addEventListener("focus", onFocus)
  document.addEventListener("visibilitychange", onVisibility)

  return () => {
    window.removeEventListener(INBOX_EVENT, onInboxChanged)
    window.removeEventListener("storage", onStorage)
    window.removeEventListener("focus", onFocus)
    document.removeEventListener("visibilitychange", onVisibility)
  }
}

function startStore() {
  if (started) return
  started = true
  unsubscribeBrowser = setupBrowserListeners()
  refreshUnread()
  connectWebSocket()
  // Polling as fallback (longer interval since WebSocket handles real-time)
  timer = setInterval(refreshUnread, 120000)
}

function stopStore() {
  if (!started || listeners.size > 0) return
  started = false
  if (timer) clearInterval(timer)
  timer = null
  if (unsubscribeBrowser) unsubscribeBrowser()
  unsubscribeBrowser = null
  disconnectWebSocket()
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
