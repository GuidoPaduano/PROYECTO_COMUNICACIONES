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
  "inline-flex items-center justify-center rounded-md font-medium transition " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300 focus-visible:ring-offset-2 " +
  "disabled:opacity-50 disabled:pointer-events-none"

const variantClasses: Record<Variant, string> = {
  // Azul clásico (equivalente a lo que tenías antes)
  primary: "bg-blue-600 text-white hover:bg-blue-700",

  // Gris claro
  secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200",

  // Contorno gris + fondo blanco (texto oscuro)
  outline: "border border-gray-300 bg-white text-gray-900 hover:bg-gray-50",

  // Sin fondo, hereda color (ideal para headers con text-white)
  ghost: "bg-transparent text-inherit hover:bg-black/5",

  // Rojo
  destructive: "bg-red-600 text-white hover:bg-red-700",

  // Contorno azul + texto azul + fondo blanco (para que siempre contraste en barras azules)
  blueOutline: "border border-blue-200 bg-white text-blue-700 hover:bg-blue-50",
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
        className={cn(
          baseClasses,
          variantClasses[variant],
          sizeClasses[size],
          className // ← va al final para permitir overrides como !text-blue-700
        )}
        {...props}
      />
    )
  }
)

Button.displayName = "Button"
