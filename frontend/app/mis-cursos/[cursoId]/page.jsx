"use client"

import Link from "next/link"
import { use, useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../../_lib/auth"
import { ChevronLeft, Users, Plus } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"

async function fetchJSON(url, opts) {
  const res = await authFetch(url, opts)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

const getCursoId = (c) => c?.id ?? c?.value ?? c
const getCursoNombre = (c) => c?.nombre ?? c?.label ?? String(getCursoId(c))
const LAST_CURSO_KEY = "ultimo_curso_seleccionado"

export default function CursoDetallePage({ params }) {
  useAuthGuard()
  const { cursoId } = use(params)

  const [me, setMe] = useState(null)
  const [cursoNombre, setCursoNombre] = useState(String(cursoId))
  const [alumnos, setAlumnos] = useState([])
  const [error, setError] = useState("")
  const [busqueda, setBusqueda] = useState("")

  const [openAdd, setOpenAdd] = useState(false)
  const [idAlumno, setIdAlumno] = useState("")
  const [nombre, setNombre] = useState("")
  const [apellido, setApellido] = useState("")
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState("")

  useEffect(() => {
    try {
      if (cursoId) localStorage.setItem(LAST_CURSO_KEY, String(cursoId))
    } catch {}
  }, [cursoId])

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

  const getAlumnoKey = (a) => a?.id ?? a?.id_alumno ?? a?.legajo ?? a?.uuid ?? a?.pk

  async function handleAgregarAlumno(e) {
    e?.preventDefault?.()
    setFormError("")
    setSaving(true)
    try {
      if (!idAlumno && (!nombre || !apellido)) {
        setFormError("Completa legajo o nombre y apellido.")
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
    <div className="space-y-6">
      <div className="surface-card surface-card-pad space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            {canAgregarAlumno && (
              <Button
                variant="outline"
                onClick={() => setOpenAdd(true)}
                className="gap-2 text-indigo-600 border-indigo-200 hover:border-indigo-300"
              >
                <Plus className="h-4 w-4" />
                Agregar alumno
              </Button>
            )}
          </div>
          <div className="text-sm text-slate-500">
            Curso: <span className="font-medium text-slate-700">{cursoNombre || cursoId}</span>
          </div>
        </div>

        <Input
          placeholder="Buscar alumno por nombre o legajo"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
      </div>

      {error && (
        <div className="surface-card surface-card-pad text-red-600">{error}</div>
      )}

      {alumnosFiltrados.length === 0 ? (
        <div className="surface-card surface-card-pad text-gray-600">
          No se encontraron alumnos para este curso.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {alumnosFiltrados.map((a) => {
            const key = getAlumnoKey(a)
            const href = key
              ? `/alumnos/${encodeURIComponent(key)}?curso=${encodeURIComponent(cursoId)}`
              : null
            return href ? (
              <Link key={key} href={href} className="block">
                <Card className="hover:shadow-md transition-shadow">
                  <CardContent className="p-5">
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center flex-shrink-0">
                        <Users className="h-5 w-5 text-indigo-600" />
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
              <Card key={`nolink-${a?.nombre}-${Math.random()}`}>
                <CardContent className="p-5">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center flex-shrink-0">
                      <Users className="h-5 w-5 text-indigo-600" />
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
            className="space-y-4"
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
                  placeholder="Ej: Perez"
                />
              </div>
            </div>

            {formError && <div className="text-sm text-red-600">{formError}</div>}

            <DialogFooter className="gap-2">
              <Button type="button" variant="outline" onClick={() => setOpenAdd(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? "Guardando..." : "Guardar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
