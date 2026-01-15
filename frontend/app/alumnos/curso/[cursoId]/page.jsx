"use client"

import Link from "next/link"
import { use, useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../../../_lib/auth"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ChevronLeft, Users as UsersIcon, User as UserIcon, Bell, Mail, Plus } from "lucide-react"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

/* ------------------------------- Helpers ------------------------------- */
async function fetchJSON(url, opts) {
  const res = await authFetch(url, opts)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}
function getCursoId(c) { return c?.id ?? c?.value ?? c }
function getCursoNombre(c) { return c?.nombre ?? c?.label ?? String(getCursoId(c)) }

/* --------------------------------- Page -------------------------------- */
export default function CursoAlumnosPage({ params }) {
  useAuthGuard()
  const { cursoId } = use(params)

  const [me, setMe] = useState(null)
  const [unreadCount, setUnreadCount] = useState(0)

  const [cursoNombre, setCursoNombre] = useState("")
  const [alumnos, setAlumnos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [q, setQ] = useState("")

  // --- Modal Agregar Alumno
  const [openAdd, setOpenAdd] = useState(false)
  const [idAlumno, setIdAlumno] = useState("")
  const [nombre, setNombre] = useState("")
  const [apellido, setApellido] = useState("")
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState("")

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
    setLoading(true); setError("")
    ;(async () => {
      try {
        try {
          const cat = await fetchJSON("/notas/catalogos/")
          if (cat.ok && Array.isArray(cat.data?.cursos)) {
            const hit = cat.data.cursos.find(c => String(getCursoId(c)) === String(cursoId))
            if (hit) setCursoNombre(getCursoNombre(hit))
          }
        } catch {}

        const r = await fetchJSON(`/alumnos/?curso=${encodeURIComponent(cursoId)}`)
        if (!r.ok) throw new Error(r.data?.detail || `HTTP ${r.status}`)
        const arr = r.data?.alumnos || r.data?.results || (Array.isArray(r.data) ? r.data : [])
        if (alive) setAlumnos(arr || [])
      } catch (e) {
        if (alive) setError(e?.message || "No se pudieron cargar los alumnos.")
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [cursoId])

  const alumnosFiltrados = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return alumnos
    return alumnos.filter(a => {
      const nombre = [a.apellido, a.nombre].filter(Boolean).join(" ").toLowerCase()
      const legajo = String(a.id_alumno ?? a.legajo ?? a.id ?? "").toLowerCase()
      return nombre.includes(t) || legajo.includes(t)
    })
  }, [alumnos, q])

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
      const { ok, data } = await fetchJSON(`/api/cursos/${encodeURIComponent(cursoId)}/agregar-alumno/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (!ok) {
        setFormError(data?.detail || "No se pudo guardar el alumno.")
        setSaving(false)
        return
      }
      const r = await fetchJSON(`/alumnos/?curso=${encodeURIComponent(cursoId)}`)
      if (r.ok) {
        const arr = r.data?.alumnos || r.data?.results || (Array.isArray(r.data) ? r.data : [])
        setAlumnos(arr || [])
      }
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
      <Topbar
        userLabel={me?.full_name || me?.username || "Usuario"}
        unreadCount={unreadCount}
        title={cursoNombre || String(cursoId)}
      />

      <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <Button asChild variant="secondary" className="gap-2">
              <Link href="/alumnos">
                <ChevronLeft className="h-4 w-4" /> Volver a Alumnos
              </Link>
            </Button>

            {/* Botón Agregar alumno — fix robusto de contraste */}
            <Button
              variant="outline"
              onClick={() => setOpenAdd(true)}
              className="bg-white border border-blue-200 hover:bg-blue-50 focus:bg-blue-50 !text-blue-700 hover:!text-blue-700 focus:!text-blue-700 gap-2"
              style={{ color: "#1d4ed8" }} // inline gana siempre a clases
            >
              <Plus className="h-4 w-4" />
              Agregar alumno
            </Button>
          </div>

          <div className="text-sm text-gray-600">
            Curso: <span className="font-medium">{cursoNombre || cursoId}</span>
          </div>
        </div>

        {/* Buscador pill */}
        <input
          className="pill-input"
          placeholder="Buscar alumno por nombre o legajo..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />

        <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
          <CardContent className="p-6">
            <div className="flex items-start gap-4 mb-4">
              <div className="tile-icon-lg">
                <UsersIcon className="h-6 w-6" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900 leading-tight">Alumnos del curso</h2>
                <p className="text-sm text-gray-600">Tocá una tarjeta para abrir el perfil</p>
              </div>
            </div>

            {loading ? (
              <div className="text-sm text-gray-500">Cargando alumnos…</div>
            ) : error ? (
              <div className="text-sm text-red-600">{error}</div>
            ) : alumnosFiltrados.length === 0 ? (
              <div className="text-sm text-gray-600">No hay alumnos para este curso.</div>
            ) : (
              <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {alumnosFiltrados.map((a) => {
                  const alumnoId = a.id ?? a.pk ?? a.alumno_id ?? a.id_alumno
                  const apellido = (a.apellido || "").toUpperCase()
                  const nombre = a.nombre || ""
                  const nombreAlumno = [apellido, nombre].filter(Boolean).join(" ").trim()
                  const legajo = a.id_alumno ?? a.legajo ?? alumnoId
                  const link = `/alumnos/${encodeURIComponent(alumnoId)}?curso=${encodeURIComponent(cursoNombre || cursoId)}`

                  return (
                    <li key={`${alumnoId}`}>
                      <Link href={link} className="block">
                        <div className="tile-card">
                          <div className="tile-card-content">
                            <div className="tile-icon-lg">
                              <UserIcon className="h-5 w-5" />
                            </div>
                            <div className="min-w-0">
                              <div className="tile-title truncate text-[15px]">{nombreAlumno}</div>
                              <div className="tile-subtitle">Legajo: {legajo}</div>
                            </div>
                          </div>
                        </div>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Modal Agregar alumno */}
      <Dialog open={openAdd} onOpenChange={setOpenAdd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Agregar alumno a {cursoNombre || cursoId}</DialogTitle>
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
              <Button type="button" className="bg-gray-200 text-gray-700 hover:bg-gray-300" onClick={() => setOpenAdd(false)}>
                Cancelar
              </Button>
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

/* ------------------------------ Topbar UI ------------------------------ */
function Topbar({ userLabel, unreadCount, title }) {
  return (
    <div className="bg-blue-600 text-white px-6 py-4">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center">
            <div className="w-6 h-6 bg-blue-600 rounded-sm flex items-center justify-center">
              <span className="text-white text-xs font-bold">🎓</span>
            </div>
          </div>
          <h1 className="text-xl font-semibold">{title || "Curso"}</h1>
        </div>

        <div className="flex items-center gap-4">
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
            <UsersIcon className="h-4 w-4" />
            {userLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
