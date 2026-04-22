"use client"

import { useMemo } from "react"
import { Building2, Layers3, Settings2, ShieldCheck, UserPlus } from "lucide-react"

import { API_BASE, useAuthGuard, useSessionContext } from "../../_lib/auth"
import { ToolSection } from "../_components/admin-tools"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function AdminPlataformaPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loading = !sessionContext
  const isSuper = !!sessionContext?.isSuperuser

  const djangoAdminHref = useMemo(() => {
    const base = String(API_BASE || "").replace(/\/+$/, "")
    if (/\/api$/i.test(base)) return `${base.replace(/\/api$/i, "")}/admin/`
    return "/admin/"
  }, [])

  const djangoAdminModelHref = useMemo(
    () => (relativePath = "") => `${djangoAdminHref}${String(relativePath || "").replace(/^\/+/, "")}`,
    [djangoAdminHref]
  )

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
          title: "Colegios",
          description: "Gestiona branding, slugs y estado activo de cada colegio desde el modelo School.",
          href: djangoAdminModelHref("calificaciones/school/"),
          icon: <Building2 className="h-6 w-6" />,
          external: true,
        },
        {
          title: "Cursos por colegio",
          description: "Administra el catalogo SchoolCourse de cada colegio, con nombre, codigo y orden.",
          href: djangoAdminModelHref("calificaciones/schoolcourse/"),
          icon: <Layers3 className="h-6 w-6" />,
          external: true,
        },
        {
          title: "Usuarios",
          description: "Alta, edicion y vinculo de usuarios del sistema desde el admin personalizado de User.",
          href: djangoAdminModelHref("auth/user/"),
          icon: <UserPlus className="h-6 w-6" />,
          external: true,
        },
        {
          title: "Admins por colegio",
          description: "Asigna usuarios del grupo Administradores a un colegio especifico para habilitar su admin de escuela.",
          href: djangoAdminModelHref("calificaciones/schooladmin/"),
          icon: <ShieldCheck className="h-6 w-6" />,
          external: true,
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
