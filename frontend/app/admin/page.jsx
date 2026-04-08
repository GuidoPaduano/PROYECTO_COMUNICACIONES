"use client"

import Link from "next/link"
import { useMemo } from "react"
import {
  ArrowRight,
  Building2,
  FolderCog,
  GraduationCap,
  KeyRound,
  Layers3,
  Settings2,
  UserCog,
  UserPlus,
} from "lucide-react"

import { API_BASE, useAuthGuard, useSessionContext } from "../_lib/auth"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

function ToolCard({ title, description, icon, href, external = false }) {
  const body = (
    <Card className="h-full border-slate-200 transition hover:-translate-y-0.5 hover:shadow-md">
      <CardHeader className="space-y-4">
        <div className="flex items-center justify-between">
          <div
            className="inline-flex h-12 w-12 items-center justify-center rounded-2xl text-white shadow-sm"
            style={{ backgroundColor: "var(--school-primary)" }}
          >
            {icon}
          </div>
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
            Disponible
          </span>
        </div>
        <div>
          <CardTitle className="text-slate-900">{title}</CardTitle>
          <CardDescription className="mt-2 text-sm leading-6 text-slate-600">
            {description}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div
          className="flex items-center text-sm font-medium"
          style={{ color: "var(--school-primary)" }}
        >
          <span>Abrir herramienta</span>
          <ArrowRight className="ml-2 h-4 w-4" />
        </div>
      </CardContent>
    </Card>
  )

  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className="block h-full">
        {body}
      </a>
    )
  }

  return (
    <Link href={href} className="block h-full">
      {body}
    </Link>
  )
}

function ToolSection({ title, description, tools }) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {tools.map((tool) => (
          <ToolCard key={tool.title} {...tool} />
        ))}
      </div>
    </section>
  )
}

export default function AdminPage() {
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

  const platformTools = isSuper ? [
    {
      title: "Nuevo colegio",
      description: "Alta asistida de un colegio nuevo con branding inicial y catalogo base de cursos.",
      href: "/admin/colegios/nuevo",
      icon: <Building2 className="h-6 w-6" />,
      external: false,
    },
    {
      title: "Django Admin",
      description: "Acceso al panel administrativo completo para modelos, usuarios y carga interna.",
      href: djangoAdminHref,
      icon: <Settings2 className="h-6 w-6" />,
      external: true,
    },
  ] : []

  const existingAdminTools = isSuper ? [
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
      title: "Roles y grupos",
      description: "Gestiona grupos y permisos base del sistema desde el modelo Group.",
      href: djangoAdminModelHref("auth/group/"),
      icon: <UserCog className="h-6 w-6" />,
      external: true,
    },
    {
      title: "Alumnos",
      description: "Consulta y corrige altas de alumnos, colegio asignado, curso y legajo.",
      href: djangoAdminModelHref("calificaciones/alumno/"),
      icon: <GraduationCap className="h-6 w-6" />,
      external: true,
    },
    {
      title: "Asignaciones de preceptores",
      description: "Vincula preceptores a cursos reales por colegio usando PreceptorCurso.",
      href: djangoAdminModelHref("calificaciones/preceptorcurso/"),
      icon: <FolderCog className="h-6 w-6" />,
      external: true,
    },
    {
      title: "Asignaciones de profesores",
      description: "Vincula profesores a cursos reales por colegio usando ProfesorCurso.",
      href: djangoAdminModelHref("calificaciones/profesorcurso/"),
      icon: <KeyRound className="h-6 w-6" />,
      external: true,
    },
  ] : []

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando panel de administracion...</div>
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
        <CardContent>
          <Link href="/dashboard" className="text-sm font-medium underline text-amber-950">
            Volver al dashboard
          </Link>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-8">
      {platformTools.length ? (
        <ToolSection
          title="Herramientas de Plataforma"
          description="Accesos reservados al superusuario para alta de colegios y operaciones globales."
          tools={platformTools}
        />
      ) : null}
      {existingAdminTools.length ? (
        <ToolSection
          title="Accesos Directos al Django Admin"
          description="Herramientas que hoy ya existen y funcionan, pero viven dentro del admin nativo del backend."
          tools={existingAdminTools}
        />
      ) : null}
    </div>
  )
}
