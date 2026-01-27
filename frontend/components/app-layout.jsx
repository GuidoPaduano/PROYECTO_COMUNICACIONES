"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import {
  CalendarDays,
  CheckSquare,
  ChevronLeft,
  ClipboardList,
  Gavel,
  GraduationCap,
  Home,
  MessageSquare,
  NotebookText,
  Plus,
  User,
  Users,
} from "lucide-react"

import { AppShell } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { authFetch, useAuthGuard } from "@/app/_lib/auth"

const ROUTE_META = [
  {
    match: (p) => p === "/dashboard",
    title: (name) => `Bienvenido${name ? "," : ""} ${name || ""}`.trim(),
    subtitle: "Tenes todo en un solo lugar: mensajeria, notas y agenda.",
    icon: <Home className="w-5 h-5 text-indigo-500" />,
    actions: null,
  },
  {
    match: (p) => p.startsWith("/alumnos"),
    title: () => "Alumnos",
    subtitle: "Gestion de perfiles, notas, sanciones y asistencias.",
    icon: <Users className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/mis-cursos"),
    title: () => "Cursos",
    subtitle: "Listado de cursos y materias asignadas.",
    icon: <NotebookText className="w-5 h-5 text-indigo-500" />,
    actions: ({ pathname }) =>
      pathname.startsWith("/mis-cursos/") ? (
        <Link href="/mis-cursos" prefetch>
          <Button variant="primary" className="gap-2">
            <ChevronLeft className="h-4 w-4" /> Volver a cursos
          </Button>
        </Link>
      ) : null,
  },
  {
    match: (p) => p.startsWith("/pasar_asistencia"),
    title: () => "Asistencia",
    subtitle: "Registra presentes, ausentes y tardanzas.",
    icon: <CheckSquare className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/calendario"),
    title: () => "Calendario",
    subtitle: "",
    icon: <CalendarDays className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/agregar_nota"),
    title: () => "Nueva nota",
    subtitle: "Agrega una calificacion u observacion.",
    icon: <ClipboardList className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/mis-notas"),
    title: () => "Mis notas",
    subtitle: "Resumen de calificaciones por materia.",
    icon: <ClipboardList className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/mis-sanciones"),
    title: () => "Mis sanciones",
    subtitle: "Historial disciplinario personal.",
    icon: <Gavel className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/mis-asistencias"),
    title: () => "Mis asistencias",
    subtitle: "Resumen de asistencias del alumno.",
    icon: <CheckSquare className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/mis-hijos"),
    title: () => "Mis hijos",
    subtitle: "Seguimiento academico y comunicacion.",
    icon: <GraduationCap className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/mensajes"),
    title: () => "Mensajes",
    subtitle: "Bandeja de entrada y enviados.",
    icon: <MessageSquare className="w-5 h-5 text-indigo-500" />,
  },
  {
    match: (p) => p.startsWith("/perfil"),
    title: () => "Perfil",
    subtitle: "Datos personales y configuracion.",
    icon: <User className="w-5 h-5 text-indigo-500" />,
  },
]

function resolveMeta(pathname, userLabel) {
  const found = ROUTE_META.find((entry) => entry.match(pathname))
  if (!found) {
    return {
      title: userLabel ? `Panel de ${userLabel}` : "Panel",
      subtitle: "Plataforma de comunicaciones",
      icon: <Home className="w-5 h-5 text-indigo-500" />,
      actions: null,
    }
  }

  const title =
    typeof found.title === "function" ? found.title(userLabel) : found.title || ""
  const actions =
    typeof found.actions === "function" ? found.actions({ pathname, userLabel }) : found.actions
  return {
    title,
    subtitle: found.subtitle || "",
    icon: found.icon || <Home className="w-5 h-5 text-indigo-500" />,
    actions: actions || null,
  }
}

function shouldHideHeader(roles, isSuper, pathname) {
  if (isSuper) return false
  if (!Array.isArray(roles) || roles.length === 0) return false
  if (pathname === "/dashboard") return false
  const set = new Set(roles.map((r) => String(r || "").toLowerCase()).filter(Boolean))
  const isAlumnoOnly =
    set.has("alumnos") &&
    !set.has("profesores") &&
    !set.has("preceptores") &&
    !set.has("padres")
  return isAlumnoOnly
}

function ProtectedShell({ children, pathname }) {
  useAuthGuard()

  const [userLabel, setUserLabel] = useState("")
  const [roles, setRoles] = useState([])
  const [rolesReady, setRolesReady] = useState(false)
  const [isSuper, setIsSuper] = useState(false)
  const [isStaff, setIsStaff] = useState(false)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const res = await authFetch("/auth/whoami/")
        if (!res.ok) return
        const data = await res.json().catch(() => ({}))
        const label = data?.full_name?.trim?.() ? data.full_name : data?.username || ""
        const rawGroups =
          (Array.isArray(data?.groups) && data.groups) ||
          (Array.isArray(data?.user?.groups) && data.user.groups) ||
          []
        const names = rawGroups
          .map((g) => (typeof g === "string" ? g : g?.name || g?.nombre || ""))
          .filter(Boolean)
        if (alive) {
          setUserLabel(label)
          setRoles(names)
          setIsSuper(!!data?.is_superuser)
          setIsStaff(!!data?.is_staff)
          setRolesReady(true)
        }
      } catch {}
    })()
    return () => {
      alive = false
    }
  }, [])

  const meta = useMemo(() => resolveMeta(pathname, userLabel), [pathname, userLabel])
  const hideHeader = useMemo(
    () => shouldHideHeader(roles, isSuper, pathname),
    [roles, isSuper, pathname]
  )
  const canAgregarAlumno = useMemo(() => {
    if (isSuper || isStaff) return true
    const names = Array.isArray(roles) ? roles : []
    return names.some((r) => String(r || "").toLowerCase().includes("precep"))
  }, [roles, isSuper, isStaff])
  const actions = useMemo(() => {
    if (pathname.startsWith("/mis-cursos/")) {
      return (
        <div className="flex items-center gap-2">
          <Link href="/mis-cursos" prefetch>
            <Button variant="primary" className="gap-2 primary-button">
              <ChevronLeft className="h-4 w-4" /> Volver a cursos
            </Button>
          </Link>
          {canAgregarAlumno && (
            <Link href={`${pathname}?add=1`} prefetch>
              <Button variant="primary" className="gap-2 primary-button">
                <Plus className="h-4 w-4" />
                Agregar alumno
              </Button>
            </Link>
          )}
        </div>
      )
    }
    return meta.actions
  }, [pathname, canAgregarAlumno, meta.actions])

  return (
    <AppShell
      title={meta.title}
      subtitle={meta.subtitle}
      icon={meta.icon}
      actions={actions}
      userLabel={userLabel}
      roles={roles}
      rolesReady={rolesReady}
      isSuper={isSuper}
      hideHeader={hideHeader}
    >
      {children}
    </AppShell>
  )
}

export default function AppLayout({ children }) {
  const pathname = usePathname() || ""
  const isAuthRoute = pathname === "/" || pathname.startsWith("/login")

  if (isAuthRoute) {
    return children
  }

  return <ProtectedShell pathname={pathname}>{children}</ProtectedShell>
}
