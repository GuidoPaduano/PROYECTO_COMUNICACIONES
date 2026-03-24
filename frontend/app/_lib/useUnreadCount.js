"use client"

import { useEffect, useState } from "react"
import { getUnreadSnapshot, subscribeUnread } from "./unread-store"

export function useUnreadCount() {
  const [unreadCount, setUnreadCount] = useState(() => getUnreadSnapshot().total)

  useEffect(() => {
    return subscribeUnread((next) => setUnreadCount(Number(next?.total || 0)))
  }, [])

  return unreadCount
}
