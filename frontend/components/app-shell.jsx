"use client"

import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import {
  BarChart3,
  CalendarDays,
  ClipboardList,
  Gavel,
  GraduationCap,
  Home,
  LogOut,
  MessageSquare,
  PanelsTopLeft,
  Menu,
  User,
  Users,
  NotebookText,
  CheckSquare,
} from "lucide-react"

import { NotificationBell } from "@/components/notification-bell"
import { cn } from "@/_lib/utils"
import { useUnreadMessages } from "@/app/_lib/useUnreadMessages"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"
const NAV_ITEMS = [
  { href: "/dashboard", label: "Inicio", icon: Home, public: true },
  {
    href: "/mis-cursos",
    label: "Cursos",
    icon: NotebookText,
    show: ({ roles, isSuper }) => isSuper || roles.has("profesores") || roles.has("preceptores"),
  },
  {
    href: "/pasar_asistencia",
    label: "Asistencia",
    icon: CheckSquare,
    show: ({ roles, isSuper }) => isSuper || roles.has("preceptores"),
  },
  { href: "/calendario", label: "Calendario", icon: CalendarDays, public: true },
  {
    href: "/mis-notas",
    label: "Mis notas",
    icon: ClipboardList,
    show: ({ roles, isSuper }) => isSuper || roles.has("alumnos"),
  },
  {
    href: "/mis-sanciones",
    label: "Sanciones",
    icon: Gavel,
    show: ({ roles, isSuper }) => isSuper || roles.has("alumnos"),
  },
  {
    href: "/mis-asistencias",
    label: "Asistencias",
    icon: CheckSquare,
    show: ({ roles, isSuper }) => isSuper || roles.has("alumnos"),
  },
  {
    href: "/mis-hijos",
    label: "Mis hijos",
    icon: GraduationCap,
    show: ({ roles, isSuper }) => isSuper || roles.has("padres"),
  },
  {
    href: "/reportes",
    label: "Reportes",
    icon: BarChart3,
    show: ({ roles, isSuper }) =>
      isSuper ||
      roles.has("profesores") ||
      roles.has("preceptores") ||
      roles.has("padres") ||
      roles.has("alumnos"),
  },
  { href: "/mensajes", label: "Mensajes", icon: MessageSquare, public: true },
  { href: "/perfil", label: "Perfil", icon: User, public: true },
]

export function AppShell({
  title = "",
  subtitle = "",
  icon = <PanelsTopLeft className="w-5 h-5 text-indigo-500" />,
  actions = null,
  headerContent = null,
  userLabel = "",
  roles = [],
  rolesReady = false,
  isSuper = false,
  hideHeader = false,
  unreadMessages,
  hideSidebar = false,
  maxWidthClass = "max-w-6xl",
  children,
}) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    setSidebarOpen(false)
  }, [pathname])
  const fromParam = searchParams.get("from")
  const hideHeaderFromParams =
    pathname?.startsWith("/alumnos") &&
    (fromParam === "mis-hijos" || fromParam === "/mis-hijos")
  const fallbackUnread = useUnreadMessages()
  const roleSet = useMemo(() => {
    if (!Array.isArray(roles)) return new Set()
    return new Set(roles.map((r) => String(r || "").toLowerCase()).filter(Boolean))
  }, [roles])
  const roleLabel = useMemo(() => {
    if (roleSet.has("padres")) return "Padre"
    if (roleSet.has("profesores")) return "Profesor"
    if (roleSet.has("preceptores")) return "Preceptor"
    if (roleSet.has("alumnos")) return "Alumno"
    return isSuper ? "Administrador" : ""
  }, [roleSet, isSuper])
  const hideHeaderForPadrePerfil =
    rolesReady && pathname?.startsWith("/perfil") && roleSet.has("padres")
  const hideHeaderForAlumnoDetail =
    pathname?.startsWith("/alumnos/") && pathname !== "/alumnos"
  const navItems = useMemo(() => {
    return NAV_ITEMS.filter((item) => {
      if (!rolesReady) return item.public
      if (!item.show) return true
      return item.show({ roles: roleSet, isSuper })
    })
  }, [roleSet, rolesReady, isSuper])

  const activeHref = useMemo(() => {
    if (!pathname) return ""
    if (pathname.startsWith("/alumnos") && fromParam) {
      if (fromParam === "mis-notas") return "/mis-notas"
      if (fromParam === "mis-sanciones") return "/mis-sanciones"
      if (fromParam === "mis-asistencias") return "/mis-asistencias"
    }
    const match = NAV_ITEMS.find((item) =>
      item.href === "/"
        ? pathname === "/"
        : pathname === item.href || pathname.startsWith(`${item.href}/`)
    )
    return match?.href || ""
  }, [pathname, fromParam])

  const handleLogout = () => {
    try {
      localStorage.clear()
    } catch {}
    window.location.href = "/login"
  }

  const messageBadge =
    typeof unreadMessages === "number" ? unreadMessages : Number(fallbackUnread || 0)

  const resolvedHideHeader =
    hideHeader || hideHeaderFromParams || hideHeaderForPadrePerfil || hideHeaderForAlumnoDetail

  return (
    <div
      className={cn(
        "app-shell",
        hideSidebar && "app-shell--no-sidebar",
        sidebarOpen && "app-shell--sidebar-open"
      )}
    >
      {!hideSidebar && (
        <aside className={cn("app-sidebar", sidebarOpen && "app-sidebar--open")}>
          <div className="sidebar-top">
            <Link href="/dashboard" className="sidebar-brand" prefetch>
              <div className="sidebar-logo">
                <img src={LOGO_SRC} alt="Logo" className="h-full w-full object-contain" />
              </div>
              <div>
                <p className="text-xs text-slate-300 leading-tight">Escuela</p>
                <p className="text-sm font-semibold text-white leading-tight">Santa Teresa</p>
              </div>
            </Link>
            <div className="sidebar-bell">
              <NotificationBell />
            </div>
          </div>

          <nav className="sidebar-nav">
            {navItems.map((item) => {
              const Icon = item.icon
              const active = activeHref === item.href
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  prefetch
                  className={cn("sidebar-link", active && "sidebar-link--active")}
                >
                  <Icon className="w-5 h-5" />
                  <span>{item.label}</span>
                  {item.href === "/mensajes" && messageBadge > 0 && (
                    <span className="sidebar-pill">{messageBadge > 99 ? "99+" : messageBadge}</span>
                  )}
                </Link>
              )
            })}
          </nav>

          <div className="sidebar-footer">
            <div className="sidebar-user">
              <div className="sidebar-avatar">{(userLabel || "User").slice(0, 2)}</div>
              <div>
                <p className="text-sm font-semibold text-white leading-tight">{userLabel || "Sesion"}</p>
                <p className="text-xs text-slate-300 leading-tight">
                  {roleLabel || "Conectado"}
                </p>
              </div>
            </div>
            <button type="button" className="sidebar-logout" onClick={handleLogout}>
              <LogOut className="w-4 h-4" />
              <span>Salir</span>
            </button>
          </div>
        </aside>
      )}

      <main className="app-main">
        <div className={cn("app-main-inner", maxWidthClass)}>
          {!hideSidebar && (
            <div className="lg:hidden mb-4 flex items-center justify-between">
              <button
                type="button"
                className="app-icon-button"
                onClick={() => setSidebarOpen((v) => !v)}
              >
                <Menu className="h-5 w-5" />
              </button>
              <div className="text-sm text-slate-600">
                {userLabel ? `Hola, ${userLabel}` : "Menú"}
              </div>
            </div>
          )}
          {!resolvedHideHeader && (
            <>
              <div className={cn("app-header", !subtitle && "app-header--no-subtitle")}>
                <div className="app-header-left">
                  <div className="app-header-icon">{icon}</div>
                  <div>
                    {title ? <h1 className="app-header-title">{title}</h1> : null}
                    {subtitle ? <p className="app-header-subtitle">{subtitle}</p> : null}
                  </div>
                </div>

                <div className="app-header-actions">{actions}</div>
              </div>

              {headerContent}
            </>
          )}

          <div className="app-content">{children}</div>
        </div>
      </main>
    </div>
  )
}



