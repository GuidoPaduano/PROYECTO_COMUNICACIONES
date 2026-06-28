"use client"

import { useSyncExternalStore } from "react"
import { getUnreadSnapshot, subscribeUnread } from "./unread-store"

export function useUnreadCount() {
  return useSyncExternalStore(
    subscribeUnread,
    () => Number(getUnreadSnapshot().total || 0),
    () => Number(getUnreadSnapshot().total || 0)
  )
}
