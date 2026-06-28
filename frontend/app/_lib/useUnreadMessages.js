"use client"

import { useSyncExternalStore } from "react"
import { getUnreadSnapshot, subscribeUnread } from "./unread-store"

export function useUnreadMessages() {
  return useSyncExternalStore(
    subscribeUnread,
    () => Number(getUnreadSnapshot().messages || 0),
    () => Number(getUnreadSnapshot().messages || 0)
  )
}
