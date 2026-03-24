"use client"

import { useEffect, useState } from "react"
import { getUnreadSnapshot, subscribeUnread } from "./unread-store"

export function useUnreadMessages() {
  const [unreadCount, setUnreadCount] = useState(() => getUnreadSnapshot().messages)

  useEffect(() => {
    return subscribeUnread((next) => setUnreadCount(Number(next?.messages || 0)))
  }, [])

  return unreadCount
}
