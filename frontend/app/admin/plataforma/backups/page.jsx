"use client"

import Link from "next/link"
import { useState } from "react"
import { AlertTriangle, ArrowLeft, Download, HardDriveDownload } from "lucide-react"

import { authFetch, useAuthGuard, useSessionContext } from "../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

function filenameFromDisposition(headerValue) {
  const raw = String(headerValue || "")
  const utfMatch = raw.match(/filename\*=UTF-8''([^;]+)/i)
  if (utfMatch?.[1]) return decodeURIComponent(utfMatch[1])
  const plainMatch = raw.match(/filename="?([^"]+)"?/i)
  return plainMatch?.[1] || "global-backup.dump"
}

export default function PlataformaBackupsPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loading = !sessionContext
  const allowed = !!sessionContext?.isSuperuser
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [lastFilename, setLastFilename] = useState("")

  const generateBackup = async () => {
    setSubmitting(true)
    setError("")
    setSuccess("")

    try {
      const res = await authFetch("/admin/backups/manual/", {
        method: "POST",
        body: JSON.stringify({}),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data?.detail || "No se pudo generar el backup.")
        return
      }

      const blob = await res.blob()
      const filename = filenameFromDisposition(res.headers.get("content-disposition"))
      const objectUrl = window.URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = objectUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(objectUrl)

      setLastFilename(filename)
      setSuccess("Backup generado y descargado.")
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de backups...</div>
      </div>
    )
  }

  if (!allowed) {
    return (
      <Card className="border-amber-200 bg-amber-50">
        <CardHeader>
          <CardTitle className="text-amber-950">Acceso restringido</CardTitle>
          <CardDescription className="text-amber-900">
            Esta herramienta es exclusiva para administradores de plataforma.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <Link
          href="/admin/plataforma"
          className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver a admin plataforma
        </Link>
        <h2 className="mt-3 text-3xl font-semibold text-slate-900">Backups manuales</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Genera un dump completo de la base de datos activa. En Railway, este archivo sale desde PostgreSQL usando
          <code className="mx-1 rounded bg-slate-100 px-1.5 py-0.5 text-xs">pg_dump</code>
          y se descarga al terminar.
        </p>
      </div>

      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle>Backup completo de plataforma</CardTitle>
          <CardDescription>
            Disponible solo para superusuarios. El archivo se genera en el momento y contiene toda la base.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                Usa esta accion para respaldo puntual. No reemplaza una politica de backups automaticos ni un plan de
                restauracion probado.
              </div>
            </div>
          </div>

          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          ) : null}

          {success ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {success}
              {lastFilename ? ` Archivo: ${lastFilename}.` : ""}
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <Button type="button" disabled={submitting} onClick={generateBackup}>
              {submitting ? (
                <Download className="mr-2 h-4 w-4 animate-bounce" />
              ) : (
                <HardDriveDownload className="mr-2 h-4 w-4" />
              )}
              {submitting ? "Generando backup..." : "Generar backup completo"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
