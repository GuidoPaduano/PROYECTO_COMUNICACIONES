"use client"

import * as React from "react"
import { cn } from "@/_lib/utils"

export function Textarea({
  className,
  ...props
}: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "flex min-h-[96px] w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition",
        "placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--school-primary-soft-strong)] focus-visible:border-[var(--school-primary-border)]",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}
