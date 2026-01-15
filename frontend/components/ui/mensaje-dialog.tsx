"use client"

import * as React from "react"
import { History, Reply, Loader2, User, Calendar } from "lucide-react"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

type MensajeLike = {
  id?: number | string
  asunto?: string
  contenido?: string
  body?: string
  emisor?: string
  remitente?: string
  fecha_envio?: string
  fecha?: string
  curso?: string
  curso_asociado?: string
}

type Props = {
  open: boolean
  onOpenChange: (v: boolean) => void

  mensaje: MensajeLike | null

  onVerHistorial: () => void | Promise<void>
  verHiloLoading?: boolean

  canReply?: boolean
  replyMode?: boolean
  onToggleReply?: () => void

  warningText?: string

  children?: React.ReactNode
}

function initialsFromName(name: string) {
  const s = String(name || "").trim()
  if (!s) return "✉️"
  const parts = s.split(/\s+/).filter(Boolean).slice(0, 2)
  const a = parts[0]?.[0] || ""
  const b = parts[1]?.[0] || ""
  return (a + b).toUpperCase() || a.toUpperCase() || "✉️"
}

function formatDate(input?: string) {
  if (!input) return "—"
  try {
    const d = new Date(input)
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString("es-AR", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    }
  } catch {}
  return String(input)
}

export default function MensajeDialog({
  open,
  onOpenChange,
  mensaje,
  onVerHistorial,
  verHiloLoading = false,
  canReply = false,
  replyMode = false,
  onToggleReply,
  warningText,
  children,
}: Props) {
  const asunto = mensaje?.asunto || "Mensaje"
  const contenido = mensaje?.contenido || mensaje?.body || "—"
  const emisor = mensaje?.emisor || mensaje?.remitente || "—"
  const fecha = mensaje?.fecha || mensaje?.fecha_envio || ""
  const curso = mensaje?.curso || mensaje?.curso_asociado || ""

  const initials = initialsFromName(emisor)
  const prettyFecha = formatDate(fecha)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 gap-0 w-[95vw] sm:max-w-3xl overflow-hidden">
        {/* Header */}
        <DialogHeader className="px-6 pt-6 pb-4">
          <DialogTitle className="text-xl font-bold tracking-tight pr-8 break-words">
            {asunto}
          </DialogTitle>

          <DialogDescription className="mt-3">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-white border shadow-sm flex items-center justify-center text-sm font-semibold text-gray-800">
                {initials}
              </div>

              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
                  <span className="inline-flex items-center gap-2 text-gray-900">
                    <User className="h-4 w-4" />
                    <span className="font-medium break-words">{emisor}</span>
                  </span>

                  <span className="inline-flex items-center gap-2 text-gray-600">
                    <Calendar className="h-4 w-4" />
                    {prettyFecha}
                  </span>
                </div>

                {curso ? (
                  <div className="mt-2 inline-flex items-center rounded-full border bg-gray-50 px-3 py-1 text-xs text-gray-700">
                    {curso}
                  </div>
                ) : null}
              </div>
            </div>
          </DialogDescription>
        </DialogHeader>

        {/* Separator */}
        <div className="h-px bg-gray-200" />

        {/* Body */}
        <div className="px-6 py-5">
          <Card className="border bg-white shadow-sm">
            <CardContent className="p-5">
              <div className="text-sm leading-6 text-gray-900 whitespace-pre-wrap break-words">
                {contenido}
              </div>
            </CardContent>
          </Card>

          <div className="mt-3 text-xs text-gray-500">
            Tip: abrí el historial para responder con contexto.
          </div>
        </div>

        {/* Separator */}
        <div className="h-px bg-gray-200" />

        {/* Footer */}
        <div className="px-6 py-4 flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
          <div className="text-xs text-gray-500">
            {warningText ? warningText : null}
          </div>

          <div className="flex gap-2 sm:justify-end">
            {canReply ? (
              <Button
                variant="secondary"
                onClick={onVerHistorial}
                disabled={verHiloLoading}
                className="gap-2"
              >
                {verHiloLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Abriendo…
                  </>
                ) : (
                  <>
                    <History className="h-4 w-4" />
                    Ver mensajes anteriores
                  </>
                )}
              </Button>
            ) : null}

            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cerrar
            </Button>

            <Button onClick={onToggleReply} disabled={!canReply} className="gap-2">
              <Reply className="h-4 w-4" />
              {replyMode ? "Cancelar" : "Responder"}
            </Button>
          </div>
        </div>

        {/* Reply area */}
        {children ? (
          <div className="px-6 pb-6">{children}</div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
