"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useAuthGuard, authFetch } from "../_lib/auth"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { BookOpen, Users, Bell, Mail, ChevronLeft } from "lucide-react"
import { NotificationBell } from "@/components/notification-bell"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"


/* Helpers */
async function fetchJSON(url) {
  const res = await authFetch(url)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}
function getCursoId(c) { return c?.id ?? c?.value ?? c }
function getCursoNombre(c) { return c?.nombre ?? c?.label ?? String(getCursoId(c)) }
async function tryGetCursos() {
  { const r = await fetchJSON("/notas/catalogos/"); if (r.ok && Array.isArray(r.data?.cursos)) return r.data.cursos }
  { const r = await fetchJSON("/cursos/"); if (r.ok) return Array.isArray(r.data) ? r.data : (r.data?.results || []) }
  { const r = await fetchJSON("/cursos/list/"); if (r.ok) return Array.isArray(r.data) ? r.data : (r.data?.results || []) }
  return []
}

/* Page */
export default function AlumnosPage() {
  useAuthGuard()

  const [me, setMe] = useState(null)
  const [unreadCount, setUnreadCount] = useState(0)
  const [cursos, setCursos] = useState([])

  useEffect(() => {
    let alive = true
    ;(async () => {
      const who = await fetchJSON("/auth/whoami/")
      if (alive && who.ok) setMe(who.data)
    })()
    const loadUnread = async () => {
      const r = await fetchJSON("/mensajes/unread_count/")
      if (alive && r.ok && typeof r.data?.count === "number") setUnreadCount(r.data.count)
    }
    loadUnread()
    const t = setInterval(loadUnread, 60000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      const cs = await tryGetCursos()
      if (alive) setCursos(cs)
    })()
    return () => { alive = false }
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      <Topbar userLabel={me?.full_name || me?.username || "Usuario"} unreadCount={unreadCount} />

      {/* Solo la grilla, sin buscador ni botón ni subtítulo */}
      <div className="max-w-6xl mx-auto px-6 py-8">
        {cursos.length === 0 ? (
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
            <CardContent className="p-6 text-sm text-gray-600">
              No hay cursos para mostrar.
            </CardContent>
          </Card>
        ) : (
          <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {cursos.map((c) => {
              const id = getCursoId(c)
              const nombre = getCursoNombre(c)
              return (
                <li key={id}>
                  <Link href={`/alumnos/curso/${encodeURIComponent(id)}`} className="block">
                    <div className="tile-card">
                      <div className="tile-card-content">
                        <div className="tile-icon-lg">
                          <BookOpen className="h-6 w-6" />
                        </div>
                        <div className="flex-1">
                          {/* 👇 sin text-lg extra: usa solo .tile-title */}
                          <div className="tile-title">{nombre}</div>
                        </div>
                      </div>
                    </div>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

/* Topbar */
function Topbar({ userLabel, unreadCount }) {
  return (
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
          <h1 className="text-xl font-semibold">Alumnos</h1>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/dashboard">
            <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
              <ChevronLeft className="h-4 w-4" />
              Volver al panel
            </Button>
          </Link>

          <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
            <Bell className="h-5 w-5" />
          </Button>
          <div className="relative">
            <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
              <Mail className="h-5 w-5" />
            </Button>
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 text-[10px] leading-none px-1.5 py-0.5 rounded-full bg-red-600 text-white border border-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </div>
          <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
            <Users className="h-4 w-4" />
            {userLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
