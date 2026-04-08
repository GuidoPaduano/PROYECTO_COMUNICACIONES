"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { use, useCallback, useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, useSessionContext } from "../../../_lib/auth"
import {
  findCourseOption,
  getCourseCode,
  getCourseLabel,
  getCourseSchoolCourseId,
  loadCourseCatalog,
  resolveCanonicalCourseValue,
} from "../../../_lib/courses"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Users as UsersIcon, User as UserIcon, Plus, ChevronLeft } from "lucide-react"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

async function fetchJSON(url, opts) {
  const res = await authFetch(url, opts)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

const CURSO_ALUMNOS_RESOURCE_MAX_AGE_MS = 10000
const cursoAlumnosResourceCache = new Map()
const cursoAlumnosResourcePromises = new Map()

function invalidateCursoAlumnosResource(cacheKeyPrefix = "") {
  const prefix = String(cacheKeyPrefix || "").trim()
  if (!prefix) return
  for (const key of Array.from(cursoAlumnosResourceCache.keys())) {
    if (key.startsWith(prefix)) {
      cursoAlumnosResourceCache.delete(key)
    }
  }
  for (const key of Array.from(cursoAlumnosResourcePromises.keys())) {
    if (key.startsWith(prefix)) {
      cursoAlumnosResourcePromises.delete(key)
    }
  }
}

async function loadCursoAlumnosResource(
  cacheKey,
  loader,
  { force = false, maxAgeMs = CURSO_ALUMNOS_RESOURCE_MAX_AGE_MS } = {}
) {
  const key = String(cacheKey || "").trim()
  if (!key || typeof loader !== "function") {
    return await loader()
  }

  if (force) {
    invalidateCursoAlumnosResource(key)
  }

  const cached = cursoAlumnosResourceCache.get(key)
  if (cached && cached.expiresAt > Date.now()) {
    return cached.data
  }

  if (cursoAlumnosResourcePromises.has(key)) {
    return await cursoAlumnosResourcePromises.get(key)
  }

  const promise = (async () => {
    const data = await loader()
    cursoAlumnosResourceCache.set(key, {
      data,
      expiresAt: Date.now() + maxAgeMs,
    })
    return data
  })()

  cursoAlumnosResourcePromises.set(key, promise)

  try {
    return await promise
  } finally {
    if (cursoAlumnosResourcePromises.get(key) === promise) {
      cursoAlumnosResourcePromises.delete(key)
    }
  }
}

export default function CursoAlumnosPage({ params }) {
  useAuthGuard()
  const session = useSessionContext()
  const { cursoId } = use(params)
  const cursoParam = String(cursoId ?? "").trim()
  const router = useRouter()
  const searchParams = useSearchParams()

  const [cursoNombre, setCursoNombre] = useState("")
  const [cursos, setCursos] = useState([])
  const [alumnos, setAlumnos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [q, setQ] = useState("")
  const [catalogLoaded, setCatalogLoaded] = useState(false)

  const [openAdd, setOpenAdd] = useState(false)
  const [idAlumno, setIdAlumno] = useState("")
  const [nombre, setNombre] = useState("")
  const [apellido, setApellido] = useState("")
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState("")
  const alumnosCursoScopeKey = useMemo(
    () => `${session?.username || "anon"}:${session?.school?.id || "default"}`,
    [session?.school?.id, session?.username]
  )
  const courseCatalogCacheKey = useMemo(
    () => `alumnos-curso-catalog:${alumnosCursoScopeKey}`,
    [alumnosCursoScopeKey]
  )

  const cursoCanonico = useMemo(
    () => resolveCanonicalCourseValue(cursoParam, cursos),
    [cursoParam, cursos]
  )
  const cursoResuelto = useMemo(
    () => findCourseOption(cursos, cursoParam) || findCourseOption(cursos, cursoCanonico),
    [cursos, cursoParam, cursoCanonico]
  )
  const cursoConsulta = useMemo(() => {
    if (cursoCanonico) return cursoCanonico
    if (/^\d+$/.test(cursoParam)) return cursoParam
    return ""
  }, [cursoCanonico, cursoParam])
  const cursoSchoolCourseId = useMemo(
    () => (cursoConsulta ? getCourseSchoolCourseId(cursoConsulta, cursos) : null),
    [cursoConsulta, cursos]
  )
  const cursoQuery = useMemo(
    () =>
      cursoSchoolCourseId != null
        ? `school_course_id=${encodeURIComponent(String(cursoSchoolCourseId))}`
        : "",
    [cursoSchoolCourseId]
  )
  const cursoCodigo = useMemo(
    () => getCourseCode(cursoResuelto || cursoConsulta, cursos) || "",
    [cursoResuelto, cursoConsulta, cursos]
  )
  const cursoDetalleQuery = useMemo(
    () =>
      cursoSchoolCourseId != null
        ? `school_course_id=${encodeURIComponent(String(cursoSchoolCourseId))}`
        : "",
    [cursoSchoolCourseId]
  )

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const nextCursos = await loadCourseCatalog({
          fetcher: authFetch,
          urls: ["/notas/catalogos/"],
          cacheKey: courseCatalogCacheKey,
        })
        if (!alive) return
        const hit = findCourseOption(nextCursos, cursoParam)
        setCursos(nextCursos)
        setCursoNombre(getCourseLabel(hit) || getCourseCode(hit) || cursoParam)
      } catch {
        if (!alive) return
        setCursoNombre(cursoParam)
      } finally {
        if (alive) setCatalogLoaded(true)
      }
    })()
    return () => {
      alive = false
    }
  }, [courseCatalogCacheKey, cursoParam])

  const loadAlumnos = useCallback(
    async (options = {}) => {
      if (!cursoParam) {
        setAlumnos([])
        setError("No se pudo resolver el curso.")
        setLoading(false)
        return
      }
      if (!cursoQuery) {
        if (!catalogLoaded) return
        setAlumnos([])
        setError("No se pudo resolver el curso.")
        setLoading(false)
        return
      }

      setLoading(true)
      setError("")
      try {
        const data = await loadCursoAlumnosResource(
          `alumnos-curso-list:${alumnosCursoScopeKey}:${cursoQuery}`,
          async () => {
            const r = await fetchJSON(`/alumnos/?${cursoQuery}`)
            if (!r.ok) throw new Error(r.data?.detail || `HTTP ${r.status}`)
            return r.data?.alumnos || []
          },
          options
        )
        setAlumnos(Array.isArray(data) ? data : [])
      } catch (e) {
        setError(e?.message || "No se pudieron cargar los alumnos.")
      } finally {
        setLoading(false)
      }
    },
    [alumnosCursoScopeKey, catalogLoaded, cursoParam, cursoQuery]
  )

  useEffect(() => {
    if (!catalogLoaded) return
    if (!cursoCanonico || cursoCanonico === cursoParam) return
    const qs = searchParams?.toString()
    router.replace(`/alumnos/curso/${encodeURIComponent(cursoCanonico)}${qs ? `?${qs}` : ""}`)
  }, [catalogLoaded, cursoCanonico, cursoParam, router, searchParams])

  useEffect(() => {
    loadAlumnos()
  }, [loadAlumnos])

  const alumnosFiltrados = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return alumnos
    return alumnos.filter((a) => {
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
      if (!cursoCodigo || cursoSchoolCourseId == null) {
        setFormError("No se pudo resolver el curso.")
        setSaving(false)
        return
      }
      if (!idAlumno && (!nombre || !apellido)) {
        setFormError("Completa legajo o nombre y apellido.")
        setSaving(false)
        return
      }
      const payload = {
        school_course_id: cursoSchoolCourseId,
        id_alumno: idAlumno || null,
        nombre: nombre || null,
        apellido: apellido || null,
      }
      const { ok, data } = await fetchJSON(
        `/api/cursos/${encodeURIComponent(cursoCodigo)}/agregar-alumno/`,
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
      invalidateCursoAlumnosResource(`alumnos-curso-list:${alumnosCursoScopeKey}:${cursoQuery}`)
      await loadAlumnos({ force: true })
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
            <Link href="/alumnos">
              <Button className="gap-2">
                <ChevronLeft className="h-4 w-4" /> Volver a Alumnos
              </Button>
            </Link>

            <Button onClick={() => setOpenAdd(true)} variant="outline" className="gap-2">
              <Plus className="h-4 w-4" />
              Agregar alumno
            </Button>
          </div>

          <div className="text-sm text-slate-500">
            Curso: <span className="font-medium text-slate-700">{cursoNombre || cursoParam}</span>
          </div>
        </div>

        <Input
          className="pill-input"
          placeholder="Buscar alumno por nombre o legajo"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-start gap-4">
            <div className="tile-icon-lg">
              <UsersIcon className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-gray-900 leading-tight">Alumnos del curso</h2>
              <p className="text-sm text-gray-600">Toca una tarjeta para abrir el perfil</p>
            </div>
          </div>

          {loading ? (
            <div className="text-sm text-gray-500">Cargando alumnos...</div>
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
                const courseQuery = cursoDetalleQuery
                const link = `/alumnos/${encodeURIComponent(alumnoId)}${
                  courseQuery ? `?${courseQuery}` : ""
                }`

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
                )}
              )}
            </ul>
          )}
        </CardContent>
      </Card>

      <Dialog open={openAdd} onOpenChange={setOpenAdd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Agregar alumno a {cursoNombre || cursoParam}</DialogTitle>
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
              <Button type="button" onClick={() => setOpenAdd(false)}>
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

