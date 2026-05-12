"use client"

import { useMemo } from "react"
import { Building2, FileSpreadsheet, Layers3, Settings2, ShieldCheck } from "lucide-react"

import { buildBackendUrl, useAuthGuard, useSessionContext } from "../../_lib/auth"
import { ToolSection } from "../_components/admin-tools"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function AdminPlataformaPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loading = !sessionContext
  const isSuper = !!sessionContext?.isSuperuser

  const djangoAdminHref = useMemo(() => {
    return buildBackendUrl("/admin/")
  }, [])

  const platformTools = isSuper
    ? [
        {
          title: "Nuevo colegio",
          description: "Alta asistida de un colegio nuevo con branding inicial y catalogo base de cursos.",
          href: "/admin/plataforma/colegios/nuevo",
          icon: <Building2 className="h-6 w-6" />,
          external: false,
        },
        {
          title: "Importar alumnos",
          description: "Carga alumnos por colegio desde un Excel o CSV con validacion previa de cursos y legajos.",
          href: "/admin/plataforma/alumnos/importar",
          icon: <FileSpreadsheet className="h-6 w-6" />,
          external: false,
        },
        {
          title: "Colegios",
          description: "Gestiona branding, slugs y estado activo de cada colegio desde el modelo School.",
          href: "/admin/plataforma/colegios",
          icon: <Building2 className="h-6 w-6" />,
          external: false,
        },
        {
          title: "Cursos por colegio",
          description: "Administra el catalogo SchoolCourse de cada colegio, con nombre, codigo y orden.",
          href: "/admin/plataforma/cursos",
          icon: <Layers3 className="h-6 w-6" />,
          external: false,
        },
        {
          title: "Admins por colegio",
          description: "Asigna usuarios del grupo Administradores a un colegio especifico para habilitar su admin de escuela.",
          href: "/admin/plataforma/admins",
          icon: <ShieldCheck className="h-6 w-6" />,
          external: false,
        },
        {
          title: "Django Admin",
          description: "Acceso al panel administrativo completo para modelos, usuarios y carga interna.",
          href: djangoAdminHref,
          icon: <Settings2 className="h-6 w-6" />,
          external: true,
        },
      ]
    : []

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando admin de plataforma...</div>
      </div>
    )
  }

  if (!isSuper) {
    return (
      <Card className="border-amber-200 bg-amber-50">
        <CardHeader>
          <CardTitle className="text-amber-950">Acceso restringido</CardTitle>
          <CardDescription className="text-amber-900">
            Este panel es exclusivo para el usuario administrador.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <div className="space-y-8">
      <ToolSection
        title="Herramientas globales"
        tools={platformTools}
      />
    </div>
  )
}
