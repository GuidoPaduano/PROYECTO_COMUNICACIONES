"use client"

import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import {
  BarChart3,
  Building2,
  CalendarDays,
  ClipboardList,
  Gavel,
  GraduationCap,
  Home,
  LogOut,
  Menu,
  MessageSquare,
  NotebookText,
  PanelsTopLeft,
  Shield,
  User,
  CheckSquare,
} from "lucide-react"

import { NotificationBell } from "@/components/notification-bell"
import { cn } from "@/_lib/utils"
import {
  DEFAULT_SCHOOL_ACCENT_COLOR,
  DEFAULT_SCHOOL_LOGO_URL,
  DEFAULT_SCHOOL_PRIMARY_COLOR,
  getPreviewRole,
  logout,
  selectSessionSchool,
} from "@/app/_lib/auth"
import { useUnreadMessages } from "@/app/_lib/useUnreadMessages"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const TECNOVA_SIDEBAR_LOGO_URL = "/imagenes/tecnova(1).png"

function hasAdminColegioAccess({ roles, isSuper }) {
  if (isSuper) return true
  return roles.has("administradores") || roles.has("administrador")
}

function normalizeHexColor(value, fallback) {
  const raw = String(value || "").trim()
  return /^#[0-9a-fA-F]{6}$/.test(raw) ? raw.toLowerCase() : fallback
}

function resolveSidebarLogoUrl(school) {
  const rawLogo = String(school?.logo_url || "").trim()
  const schoolName = String(school?.name || school?.short_name || school?.slug || "").toLowerCase()
  const normalizedLogo = rawLogo.toLowerCase()
  const looksLikeGenericAlumnixLogo =
    normalizedLogo.includes("alumnix") ||
    normalizedLogo === String(DEFAULT_SCHOOL_LOGO_URL).toLowerCase()
  const isTecnova = schoolName.includes("itnova") || schoolName.includes("tecnova")

  if (rawLogo && !looksLikeGenericAlumnixLogo) return rawLogo
  if (isTecnova) return TECNOVA_SIDEBAR_LOGO_URL
  return DEFAULT_SCHOOL_LOGO_URL
}

function hexToRgba(hexColor, alpha) {
  const normalized = normalizeHexColor(hexColor, DEFAULT_SCHOOL_PRIMARY_COLOR).replace("#", "")
  const red = Number.parseInt(normalized.slice(0, 2), 16)
  const green = Number.parseInt(normalized.slice(2, 4), 16)
  const blue = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

function darkenHexColor(hexColor, factor = 0.14) {
  const normalized = normalizeHexColor(hexColor, DEFAULT_SCHOOL_PRIMARY_COLOR).replace("#", "")
  const clamp = (value) => Math.max(0, Math.min(255, value))
  const scale = 1 - Math.max(0, Math.min(0.95, factor))
  const red = clamp(Math.round(Number.parseInt(normalized.slice(0, 2), 16) * scale))
  const green = clamp(Math.round(Number.parseInt(normalized.slice(2, 4), 16) * scale))
  const blue = clamp(Math.round(Number.parseInt(normalized.slice(4, 6), 16) * scale))
  return `#${[red, green, blue].map((channel) => channel.toString(16).padStart(2, "0")).join("")}`
}

const NAV_ITEMS = [
  { href: "/dashboard", label: "Inicio", icon: Home, public: true },
  {
    href: "/mis-cursos",
    label: "Cursos",
    icon: NotebookText,
    show: ({ roles, isSuper }) =>
      isSuper || roles.has("profesores") || roles.has("preceptores") || roles.has("directivos"),
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
      roles.has("directivos") ||
      roles.has("preceptores") ||
      roles.has("padres") ||
      roles.has("alumnos"),
  },
  {
    href: "/admin/colegio",
    label: "Admin colegio",
    icon: Building2,
    show: ({ roles, isSuper }) => hasAdminColegioAccess({ roles, isSuper }),
  },
  {
    href: "/admin/plataforma",
    label: "Admin plataforma",
    icon: Shield,
    show: ({ isSuper }) => isSuper,
  },
  { href: "/mensajes", label: "Mensajes", icon: MessageSquare, public: true },
  { href: "/perfil", label: "Perfil", icon: User, public: true },
]

export function AppShell({
  title = "",
  subtitle = "",
  icon = <PanelsTopLeft className="w-5 h-5" />,
  actions = null,
  headerContent = null,
  userLabel = "",
  roles = [],
  rolesReady = false,
  isSuper = false,
  school = null,
  availableSchools = [],
  hideHeader = false,
  unreadMessages,
  hideSidebar = false,
  maxWidthClass = "max-w-6xl",
  children,
}) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [switchingSchool, setSwitchingSchool] = useState(false)

  useEffect(() => {
    setSidebarOpen(false)
  }, [pathname])

  const fromParam = searchParams.get("from")
  const hideHeaderFromParams =
    pathname?.startsWith("/alumnos") &&
    (fromParam === "mis-hijos" || fromParam === "/mis-hijos")
  const fallbackUnread = useUnreadMessages()
  const adminOnlyMode = useMemo(() => isSuper && !getPreviewRole(), [isSuper])
  const roleSet = useMemo(() => {
    if (!Array.isArray(roles)) return new Set()
    return new Set(roles.map((role) => String(role || "").toLowerCase()).filter(Boolean))
  }, [roles])
  const roleLabel = useMemo(() => {
    if (roleSet.has("administradores") || roleSet.has("administrador")) return "Admin colegio"
    if (roleSet.has("padres")) return "Padre"
    if (roleSet.has("profesores")) return "Profesor"
    if (roleSet.has("directivos")) return "Directivo"
    if (roleSet.has("preceptores")) return "Preceptor"
    if (roleSet.has("alumnos")) return "Alumno"
    return isSuper ? "Administrador" : ""
  }, [roleSet, isSuper])
  const schoolName = useMemo(() => {
    const name = String(school?.name || "").trim()
    return name || ""
  }, [school])
  const schoolShortName = useMemo(() => {
    const value = String(school?.short_name || "").trim()
    return value || schoolName
  }, [school, schoolName])
  const schoolLogo = useMemo(() => {
    return resolveSidebarLogoUrl(school)
  }, [school])
  const brandStyle = useMemo(() => {
    const primary = normalizeHexColor(school?.primary_color, DEFAULT_SCHOOL_PRIMARY_COLOR)
    const accent = normalizeHexColor(school?.accent_color, DEFAULT_SCHOOL_ACCENT_COLOR)
    return {
      "--school-primary": primary,
      "--school-primary-hover": darkenHexColor(primary, 0.14),
      "--school-primary-soft": hexToRgba(primary, 0.12),
      "--school-primary-soft-strong": hexToRgba(primary, 0.2),
      "--school-primary-border": hexToRgba(primary, 0.24),
      "--school-accent": accent,
      "--school-accent-soft": hexToRgba(accent, 0.14),
      "--school-accent-soft-strong": hexToRgba(accent, 0.2),
    }
  }, [school])
  const showSchoolSwitcher = useMemo(
    () => !!isSuper && Array.isArray(availableSchools) && availableSchools.length > 1,
    [availableSchools, isSuper]
  )
  const selectedSchoolValue = useMemo(() => {
    if (!school) return ""
    if (school.slug) return `slug:${school.slug}`
    if (school.id != null) return `id:${school.id}`
    return ""
  }, [school])
  const sidebarEyebrow = adminOnlyMode ? "Colegio" : "Escuela"
  const sidebarTitle = schoolShortName || schoolName || "Comunicaciones"
  const hideHeaderForPadrePerfil =
    rolesReady && pathname?.startsWith("/perfil") && roleSet.has("padres")
  const hideHeaderForAlumnoDetail =
    pathname?.startsWith("/alumnos/") && pathname !== "/alumnos"
  const navItems = useMemo(() => {
    if (rolesReady && adminOnlyMode) {
      return NAV_ITEMS.filter(
        (item) =>
          item.href === "/admin/colegio" ||
          item.href === "/admin/plataforma" ||
          item.href === "/perfil"
      )
    }
    return NAV_ITEMS.filter((item) => {
      if (!rolesReady) return item.public
      if (!item.show) return true
      return item.show({ roles: roleSet, isSuper })
    })
  }, [adminOnlyMode, roleSet, rolesReady, isSuper])

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
  const canAccessAdminColegio = useMemo(
    () => hasAdminColegioAccess({ roles: roleSet, isSuper }),
    [roleSet, isSuper]
  )

  const handleLogout = () => {
    logout()
  }

  const handleSchoolChange = (value) => {
    if (!value || value === selectedSchoolValue || switchingSchool) return
    const nextContext = selectSessionSchool(value)
    if (!nextContext) return

    setSwitchingSchool(true)
    if (typeof window !== "undefined") {
      const href = `${window.location.pathname || ""}${window.location.search || ""}${window.location.hash || ""}`
      window.location.assign(href || "/admin/colegio")
    }
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
      style={brandStyle}
    >
      {!hideSidebar && (
        <aside className={cn("app-sidebar", sidebarOpen && "app-sidebar--open")}>
          <div className="sidebar-top">
            <Link href={adminOnlyMode || canAccessAdminColegio ? "/admin/colegio" : "/dashboard"} className="sidebar-brand" prefetch>
              <div className="sidebar-logo">
                <img
                  src={schoolLogo}
                  alt={schoolName ? `Logo de ${schoolName}` : "Logo del colegio"}
                  className="h-full w-full object-contain"
                  onError={(event) => {
                    if (event.currentTarget.dataset.fallbackApplied) return
                    event.currentTarget.dataset.fallbackApplied = "1"
                    event.currentTarget.src = DEFAULT_SCHOOL_LOGO_URL
                  }}
                />
              </div>
              <div>
                <p className="text-xs text-slate-300 leading-tight">{sidebarEyebrow}</p>
                <p className="text-sm font-semibold text-white leading-tight">{sidebarTitle}</p>
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
                  {item.href === "/mensajes" && !adminOnlyMode && messageBadge > 0 ? (
                    <span className="sidebar-pill">{messageBadge > 99 ? "99+" : messageBadge}</span>
                  ) : null}
                </Link>
              )
            })}
          </nav>

          <div className="sidebar-footer">
            <div className="sidebar-user">
              <div className="sidebar-avatar">{(userLabel || "User").slice(0, 2)}</div>
              <div>
                <p className="text-sm font-semibold text-white leading-tight">
                  {userLabel || "Sesion"}
                </p>
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
                onClick={() => setSidebarOpen((value) => !value)}
              >
                <Menu className="h-5 w-5" />
              </button>
              <div className="text-right">
                <div className="text-sm text-slate-600">
                  {schoolName || (userLabel ? `Hola, ${userLabel}` : "Menu")}
                </div>
                {schoolName && userLabel ? (
                  <div className="text-xs text-slate-500">{userLabel}</div>
                ) : null}
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

                <div className="app-header-actions flex flex-wrap items-center gap-3">
                  {showSchoolSwitcher ? (
                    <div className="min-w-[220px]">
                      <Select
                        value={selectedSchoolValue}
                        onValueChange={handleSchoolChange}
                        disabled={switchingSchool}
                      >
                        <SelectTrigger className="bg-white" size="sm" aria-label="Cambiar colegio activo">
                          <SelectValue placeholder="Elegir colegio" />
                        </SelectTrigger>
                        <SelectContent>
                          {availableSchools.map((item) => {
                            const value = item?.slug ? `slug:${item.slug}` : `id:${item.id}`
                            return (
                              <SelectItem key={value} value={value}>
                                {item.name}
                              </SelectItem>
                            )
                          })}
                        </SelectContent>
                      </Select>
                    </div>
                  ) : null}
                  {actions}
                </div>
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
