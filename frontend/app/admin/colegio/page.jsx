"use client"

import { FolderCog, KeyRound } from "lucide-react"

import { useAuthGuard, useSessionContext } from "../../_lib/auth"
import { ToolSection } from "../_components/admin-tools"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function AdminColegioPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loading = !sessionContext
  const isSuper = !!sessionContext?.isSuperuser
  const groups = Array.isArray(sessionContext?.groups) ? sessionContext.groups : []
  const isSchoolAdmin = isSuper || groups.some((group) => {
    const value = String(group || "").toLowerCase()
    return value === "administradores" || value === "administrador"
  })

  const schoolTools = isSchoolAdmin
    ? [
        {
          title: "Asignacion a preceptores",
          description: "Asigna preceptores a cursos del colegio activo desde una herramienta propia de la plataforma.",
          href: "/admin/colegio/asignacion-preceptores",
          icon: <FolderCog className="h-6 w-6" />,
          external: false,
        },
        {
          title: "Asignacion a profesores",
          description: "Asigna profesores a cursos del colegio activo desde una herramienta propia de la plataforma.",
          href: "/admin/colegio/asignacion-profesores",
          icon: <KeyRound className="h-6 w-6" />,
          external: false,
        },
      ]
    : []

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando admin del colegio...</div>
      </div>
    )
  }

  if (!isSchoolAdmin) {
    return (
      <Card className="border-amber-200 bg-amber-50">
        <CardHeader>
          <CardTitle className="text-amber-950">Acceso restringido</CardTitle>
          <CardDescription className="text-amber-900">
            Este panel es exclusivo para administradores de colegio.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <div className="space-y-8">
      <ToolSection
        title="Herramientas"
        description=""
        tools={schoolTools}
      />
    </div>
  )
}
