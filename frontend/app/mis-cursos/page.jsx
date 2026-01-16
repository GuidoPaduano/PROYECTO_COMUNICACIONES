"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../_lib/auth"
import { BookOpen, Mail, User, ChevronDown, ChevronLeft } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { NotificationBell } from "@/components/notification-bell"
import { useUnreadCount } from "../_lib/useUnreadCount"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

export default function MisCursosPage() {
  useAuthGuard()

  const [me, setMe] = useState(null)
  const [error, setError] = useState("")
  const [cursos, setCursos] = useState([])

  // contador global de mensajes no leídos
  const unreadCount = useUnreadCount()

  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || ""),
    [me]
  )

  // Perfil
  useEffect(() => {
    ;(async () => {
      try {
        const res = await authFetch("/auth/whoami/")
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          setError(data?.detail || `Error ${res.status}`)
          return
        }
        setMe(data)
      } catch {
        setError("No se pudo obtener el perfil")
      }
    })()
  }, [])

  // Cursos
  useEffect(() => {
    ;(async () => {
      try {
        const res = await authFetch("/notas/catalogos/")
        const j = await res.json().catch(() => ({}))
        if (!res.ok) {
          setError(j?.detail || `Error ${res.status}`)
          return
        }
        setCursos(j?.cursos || [])
      } catch {
        setError("No se pudieron cargar los cursos.")
      }
    })()
  }, [])

  const getCursoId = (c) => (c?.id ?? c?.value ?? c)
  const getCursoNombre = (c) => (c?.nombre ?? c?.label ?? String(getCursoId(c)))

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      {/* Header igual al dashboard + botón Volver al panel */}
      <div className="bg-blue-600 text-white px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="inline-flex">
              <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center overflow-hidden">
                <img
                  src={LOGO_SRC}
                  alt="Escuela Santa Teresa"
                  className="h-full w-full object-contain"
                />
              </div>
            </Link>
            <h1 className="text-xl font-semibold">Mis cursos</h1>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            <Link href="/dashboard">
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <ChevronLeft className="h-4 w-4" />
                Volver al panel
              </Button>
            </Link>

            {/* Campanita centralizada */}
            <NotificationBell unreadCount={unreadCount} />

            {/* Mail apuntando a /mensajes con badge */}
            <div className="relative">
              <Link href="/mensajes">
                <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
                  <Mail className="h-5 w-5" />
                </Button>
              </Link>
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 text-[10px] leading-none px-1.5 py-0.5 rounded-full bg-red-600 text-white border border-white">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </div>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                  <User className="h-4 w-4" />
                  {userLabel}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem asChild className="text-sm">
                  <Link href="/perfil">
                    <div className="flex items-center">
                      <User className="h-4 w-4 mr-2" />
                      Perfil
                    </div>
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => {
                    try {
                      localStorage.clear()
                    } catch {}
                    window.location.href = "/login"
                  }}
                >
                  <span className="h-4 w-4 mr-2">🚪</span>
                  Cerrar sesión
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>

      {/* Contenido */}
      <div className="max-w-6xl mx-auto px-6 py-8">
        {error && (
          <div className="text-red-600 bg-red-100 border border-red-200 rounded-md p-3 mb-6">
            {error}
          </div>
        )}

        {cursos.length === 0 ? (
          <p className="text-gray-600">No tenés cursos asignados.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {cursos.map((curso, idx) => {
              const id = getCursoId(curso)
              const nombre = getCursoNombre(curso)
              return (
                <Link
                  key={idx}
                  href={`/mis-cursos/${encodeURIComponent(id)}`}
                  className="block"
                >
                  <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
                    <CardContent className="p-6">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                          <BookOpen className="h-5 w-5 text-blue-600" />
                        </div>
                        <h3 className="font-semibold text-gray-900">{nombre}</h3>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
