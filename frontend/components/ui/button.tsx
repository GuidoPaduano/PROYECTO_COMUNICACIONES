"use client"

import * as React from "react"
import { cn } from "../../_lib/utils"

type Variant = "primary" | "secondary" | "outline" | "ghost" | "destructive" | "blueOutline"
type Size = "default" | "sm" | "lg" | "icon"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

const baseClasses =
  "inline-flex items-center justify-center rounded-lg font-medium transition " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--school-primary-soft-strong)] focus-visible:ring-offset-2 " +
  "disabled:opacity-50 disabled:pointer-events-none"

const variantClasses: Record<Variant, string> = {
  primary: "btn-school-primary",
  secondary: "btn-school-secondary",
  outline: "btn-school-outline",
  ghost: "btn-school-ghost",
  destructive: "bg-red-600 text-white hover:bg-red-700",
  blueOutline: "btn-school-outline",
}

const sizeClasses: Record<Size, string> = {
  default: "h-9 px-3 py-2 text-sm",
  sm: "h-8 px-2.5 text-xs",
  lg: "h-10 px-4 text-base",
  icon: "h-9 w-9 p-0",
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "default", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(baseClasses, variantClasses[variant], sizeClasses[size], className)}
        {...props}
      />
    )
  }
)

Button.displayName = "Button"
