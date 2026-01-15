"use client"

import Link from "next/link"
import { use, useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../../_lib/auth"
import {
  ChevronLeft,
  Users,
  Mail,
  User as UserIcon,
  ChevronDown,
  Home,
  Plus,
} from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { NotificationBell } from "@/components/notification-bell"
import { useUnreadCount } from "../../_lib/useUnreadCount"

// ------------------------------- Helpers -------------------------------
async function fetchJSON(url, opts) {
  const res = await authFetch(url, opts)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}
const getCursoId = (c) => c?.id ?? c?.value ?? c
const getCursoNombre = (c) => c?.nombre ?? c?.label ?? String(getCursoId(c))

export default function CursoDetallePage({ params }) {
  useAuthGuard()
  const { cursoId } = use(params) // Next 14+: params puede ser Promise

  const [me, setMe] = useState(null)
  const [cursoNombre, setCursoNombre] = useState(String(cursoId))
  const [alumnos, setAlumnos] = useState([])
  const [error, setError] = useState("")
  const [busqueda, setBusqueda] = useState("")

  // Modal Agregar alumno
  const [openAdd, setOpenAdd] = useState(false)
  const [idAlumno, setIdAlumno] = useState("")
  const [nombre, setNombre] = useState("")
  const [apellido, setApellido] = useState("")
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState("")

  // contador global de no leídos
  const unreadCount = useUnreadCount()

  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || "Usuario"),
    [me]
  )


const canAgregarAlumno = useMemo(() => {
  try {
    if (!me) return false
    if (me?.is_superuser || me?.is_staff) return true

    const rawGroups =
      (Array.isArray(me?.groups) && me.groups) ||
      (Array.isArray(me?.user?.groups) && me.user.groups) ||
      []

    const names = rawGroups
      .map((g) => (typeof g === "string" ? g : g?.name || ""))
      .filter(Boolean)
      .map((s) => String(s).toLowerCase())

    const joined = names.join(" ")
    return joined.includes("precep")
  } catch {
    return false
  }
}, [me])

  // Perfil
  useEffect(() => {
    ;(async () => {
      try {
        const res = await authFetch("/auth/whoami/")
        const data = await res.json().catch(() => ({}))
        if (!res.ok) return
        setMe(data)
      } catch {}
    })()
  }, [])

  // Nombre del curso
  useEffect(() => {
    ;(async () => {
      try {
        const res = await authFetch("/notas/catalogos/")
        const j = await res.json().catch(() => ({}))
        const cursos = j?.cursos || []
        const match = cursos.find((c) => String(getCursoId(c)) === String(cursoId))
        setCursoNombre(getCursoNombre(match) || String(cursoId))
      } catch {
        setCursoNombre(String(cursoId))
      }
    })()
  }, [cursoId])

  // Alumnos del curso
  async function loadAlumnos() {
    try {
      const res = await authFetch(`/alumnos/?curso=${encodeURIComponent(cursoId)}`)
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(j?.detail || `Error ${res.status}`)
        return
      }
      setAlumnos(j?.alumnos || [])
    } catch {
      setError("No se pudieron cargar los alumnos.")
    }
  }

  useEffect(() => {
    loadAlumnos()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoId])

  const alumnosFiltrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    if (!q) return alumnos
    return alumnos.filter((a) => {
      const nombreA = (a?.nombre || "").toLowerCase()
      const idA = String(a?.id_alumno || "").toLowerCase()
      return nombreA.includes(q) || idA.includes(q)
    })
  }, [alumnos, busqueda])

  // ID robusto para el link
  const getAlumnoKey = (a) => a?.id ?? a?.id_alumno ?? a?.legajo ?? a?.uuid ?? a?.pk

  // Guardar alumno (modal)
  async function handleAgregarAlumno(e) {
    e?.preventDefault?.()
    setFormError("")
    setSaving(true)
    try {
      if (!idAlumno && (!nombre || !apellido)) {
        setFormError("Completá Legajo (o) Nombre y Apellido.")
        setSaving(false)
        return
      }
      const payload = {
        curso: cursoId,
        id_alumno: idAlumno || null,
        nombre: nombre || null,
        apellido: apellido || null,
      }
      const { ok, data } = await fetchJSON(
        `/api/cursos/${encodeURIComponent(cursoId)}/agregar-alumno/`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      )
      if (!ok) {
        setFormError(data?.detail || "No se pudo guardar el alumno.")
        setSaving(false)
        return
      }
      await loadAlumnos()
      setOpenAdd(false)
      setIdAlumno("")
      setNombre("")
      setApellido("")
    } catch {
      setFormError("No se pudo guardar el alumno.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      {/* Header */}
      <div className="bg-blue-600 text-white px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center">
              <div className="w-6 h-6 bg-blue-600 rounded-sm flex items-center justify-center">
                <span className="text-white text-xs font-bold">🎓</span>
              </div>
            </div>
            <h1 className="text-xl font-semibold">{cursoNombre || String(cursoId) || "Curso"}</h1>
          </div>
          <div className="flex items-center gap-2 sm:gap-4">
            <Link href="/mis-cursos">
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <ChevronLeft className="h-4 w-4" /> Volver
              </Button>
            </Link>
            <Link href="/dashboard">
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <Home className="h-4 w-4" /> Volver al panel
              </Button>
            </Link>

            {/* Botón “Agregar alumno” */}
            {canAgregarAlumno && (

            <button
              onClick={() => setOpenAdd(true)}
              className="inline-flex items-center gap-2 rounded-md border border-blue-200 bg-white px-3 py-2 text-sm font-medium hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-300"
              style={{ color: "#1d4ed8" }}
              title="Agregar alumno"
            >
              <Plus className="h-4 w-4" />
              Agregar alumno
            </button>

            )}
            {/* Campanita centralizada */}
            <NotificationBell unreadCount={unreadCount} />

            {/* Mail que va a /mensajes con badge */}
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
                  <UserIcon className="h-4 w-4" />
                  {userLabel}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem asChild className="text-sm">
                  <Link href="/perfil">
                    <div className="flex items-center">
                      <UserIcon className="h-4 w-4 mr-2" /> Perfil
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
                  <span className="h-4 w-4 mr-2">🚪</span> Cerrar sesión
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

        {/* Buscador */}
        <div className="mb-6">
          <Input
            placeholder="Buscar alumno por nombre o legajo…"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
          />
        </div>

        {/* Lista de alumnos */}
        {alumnosFiltrados.length === 0 ? (
          <p className="text-gray-600">No se encontraron alumnos para este curso.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {alumnosFiltrados.map((a) => {
              const key = getAlumnoKey(a)
              const href = key
                ? `/alumnos/${encodeURIComponent(key)}?curso=${encodeURIComponent(cursoId)}`
                : null
              return href ? (
                <Link key={key} href={href} className="block">
                  <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
                    <CardContent className="p-5">
                      <div className="flex items-start gap-3">
                        <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                          <Users className="h-5 w-5 text-blue-600" />
                        </div>
                        <div className="flex-1">
                          <h3 className="font-semibold text-gray-900">{a.nombre}</h3>
                          {a.id_alumno ? (
                            <p className="text-sm text-gray-600">Legajo: {a.id_alumno}</p>
                          ) : null}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ) : (
                <Card
                  key={`nolink-${a?.nombre}-${Math.random()}`}
                  className="shadow-sm border-0 bg-white/80 backdrop-blur-sm"
                >
                  <CardContent className="p-5">
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <Users className="h-5 w-5 text-blue-600" />
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold text-gray-900">{a?.nombre || "Alumno"}</h3>
                        {a?.id_alumno ? (
                          <p className="text-sm text-gray-600">Legajo: {a.id_alumno}</p>
                        ) : null}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>

      {/* Modal Agregar alumno */}
      <Dialog open={openAdd} onOpenChange={setOpenAdd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Agregar alumno a {cursoNombre}</DialogTitle>
          </DialogHeader>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleAgregarAlumno(e)
            }}
            className="space-y-4 mt-2"
          >
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <Label htmlFor="id_alumno">Legajo / ID de alumno (opcional)</Label>
                <Input
                  id="id_alumno"
                  value={idAlumno}
                  onChange={(e) => setIdAlumno(e.target.value)}
                  placeholder="Ej: 1A-024"
                />
              </div>

              <div>
                <Label htmlFor="nombre">Nombre(s)</Label>
                <Input
                  id="nombre"
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  placeholder="Ej: Juan Ignacio"
                />
              </div>

              <div>
                <Label htmlFor="apellido">Apellido(s)</Label>
                <Input
                  id="apellido"
                  value={apellido}
                  onChange={(e) => setApellido(e.target.value)}
                  placeholder="Ej: Pérez"
                />
              </div>
            </div>

            {formError && <div className="text-sm text-red-600">{formError}</div>}

            <DialogFooter className="gap-2">
              <button
                type="button"
                onClick={() => setOpenAdd(false)}
                className="inline-flex items-center rounded-md bg-gray-200 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-300"
              >
                Cancelar
              </button>
              <Button type="submit" disabled={saving} className="bg-blue-600 text-white hover:bg-blue-700">
                {saving ? "Guardando…" : "Guardar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
