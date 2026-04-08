"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import {
  BarChart3,
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
  Shield,
  User,
  Users,
} from "lucide-react"

import { AppShell } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import {
  buildSessionContext,
  getCachedSessionProfileData,
  getSessionProfile,
  useAuthGuard,
  useSessionContext,
} from "@/app/_lib/auth"

const ROUTE_META = [
  {
    match: (p) => p === "/dashboard",
    title: (name) => `Bienvenido${name ? "," : ""} ${name || ""}`.trim(),
    subtitle: "Tenes todo en un solo lugar: mensajeria, notas y agenda.",
    icon: <Home className="w-5 h-5" />,
    actions: null,
  },
  {
    match: (p) => p.startsWith("/alumnos"),
    title: () => "Alumnos",
    subtitle: "Gestion de perfiles, notas, sanciones y asistencias.",
    icon: <Users className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/mis-cursos"),
    title: () => "Cursos",
    subtitle: "Listado de cursos y materias asignadas.",
    icon: <NotebookText className="w-5 h-5" />,
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
    icon: <CheckSquare className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/calendario"),
    title: () => "Calendario",
    subtitle: "",
    icon: <CalendarDays className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/agregar_nota"),
    title: () => "Nueva nota",
    subtitle: "Agrega una calificacion u observacion.",
    icon: <ClipboardList className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/mis-notas"),
    title: () => "Mis notas",
    subtitle: "Resumen de calificaciones por materia.",
    icon: <ClipboardList className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/mis-sanciones"),
    title: () => "Mis sanciones",
    subtitle: "Historial disciplinario personal.",
    icon: <Gavel className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/mis-asistencias"),
    title: () => "Mis asistencias",
    subtitle: "Resumen de asistencias del alumno.",
    icon: <CheckSquare className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/mis-hijos"),
    title: () => "Mis hijos",
    subtitle: "Seguimiento academico y comunicacion.",
    icon: <GraduationCap className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/reportes"),
    title: () => "Reportes",
    subtitle: "Dashboard de estadisticas de notas y asistencias.",
    icon: <BarChart3 className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/admin"),
    title: () => "Administracion",
    subtitle: "Herramientas de control y configuracion avanzada.",
    icon: <Shield className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/mensajes"),
    title: () => "Mensajes",
    subtitle: "Bandeja de entrada y enviados.",
    icon: <MessageSquare className="w-5 h-5" />,
  },
  {
    match: (p) => p.startsWith("/perfil"),
    title: () => "Perfil",
    subtitle: "Datos personales y configuracion.",
    icon: <User className="w-5 h-5" />,
  },
]

function isPublicPath(raw) {
  if (!raw) return false
  const value = String(raw)
  if (value === "/") return true
  if (/^\/(login|forgot-password|reset-password)(\/|$)/.test(value)) return true
  if (value.includes("/login")) return true
  if (value.includes("/forgot-password")) return true
  if (value.includes("/reset-password")) return true
  return false
}

function resolveMeta(pathname, userLabel) {
  const found = ROUTE_META.find((entry) => entry.match(pathname))
  if (!found) {
    return {
      title: userLabel ? `Panel de ${userLabel}` : "Panel",
      subtitle: "Plataforma de comunicaciones",
      icon: <Home className="w-5 h-5" />,
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
    icon: found.icon || <Home className="w-5 h-5" />,
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
  const isPublic = useMemo(() => {
    const browserPath =
      typeof window !== "undefined" ? window.location.pathname || "" : ""
    const browserHref =
      typeof window !== "undefined" ? window.location.href || "" : ""
    return [pathname, browserPath, browserHref].some(isPublicPath)
  }, [pathname])

  useAuthGuard({ enabled: !isPublic })

  const sessionContext = useSessionContext()
  const cachedProfile = useMemo(() => getCachedSessionProfileData(), [])
  const cachedContext = useMemo(
    () => (cachedProfile ? buildSessionContext(cachedProfile) : null),
    [cachedProfile]
  )

  const [userLabel, setUserLabel] = useState(
    () => sessionContext?.userLabel || cachedContext?.userLabel || ""
  )
  const [roles, setRoles] = useState(
    () =>
      (Array.isArray(sessionContext?.groups) ? sessionContext.groups : null) ||
      (Array.isArray(cachedContext?.groups) ? cachedContext.groups : [])
  )
  const [rolesReady, setRolesReady] = useState(() => !!sessionContext || !!cachedContext)
  const [isSuper, setIsSuper] = useState(
    () => !!sessionContext?.isSuperuser || !!cachedContext?.isSuperuser
  )

  useEffect(() => {
    if (!sessionContext) return
    setUserLabel(sessionContext.userLabel || sessionContext.username || "")
    setRoles(Array.isArray(sessionContext.groups) ? sessionContext.groups : [])
    setIsSuper(!!sessionContext.isSuperuser)
    setRolesReady(true)
  }, [sessionContext])

  useEffect(() => {
    if (isPublic || sessionContext) return
    let alive = true
    ;(async () => {
      try {
        const data = await getSessionProfile()
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
          setRolesReady(true)
        }
      } catch {}
    })()
    return () => {
      alive = false
    }
  }, [isPublic, sessionContext])

  const meta = useMemo(() => resolveMeta(pathname, userLabel), [pathname, userLabel])
  const hideHeader = useMemo(
    () => shouldHideHeader(roles, isSuper, pathname),
    [roles, isSuper, pathname]
  )
  const canAgregarAlumno = useMemo(() => {
    if (isSuper) return true
    const names = Array.isArray(roles) ? roles : []
    return names.some((r) => {
      const role = String(r || "").toLowerCase()
      return role.includes("precep") || role.includes("directiv")
    })
  }, [roles, isSuper])
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

  if (isPublic) {
    return children
  }

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
      school={sessionContext?.school || cachedContext?.school || null}
      availableSchools={sessionContext?.availableSchools || cachedContext?.availableSchools || []}
      hideHeader={hideHeader}
    >
      {children}
    </AppShell>
  )
}

export default function AppLayout({ children }) {
  const pathname = usePathname() || ""
  const [isPublic, setIsPublic] = useState(true)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const browserPath =
      typeof window !== "undefined" ? window.location.pathname || "" : ""
    const browserHref =
      typeof window !== "undefined" ? window.location.href || "" : ""
    const resolvedPath = browserPath || pathname
    const isRoutePublic =
      !resolvedPath ||
      isPublicPath(resolvedPath) ||
      isPublicPath(browserHref)
    setIsPublic(isRoutePublic)
    setReady(true)
  }, [pathname])

  if (!ready || isPublic) {
    return children
  }

  return <ProtectedShell pathname={pathname}>{children}</ProtectedShell>
}
