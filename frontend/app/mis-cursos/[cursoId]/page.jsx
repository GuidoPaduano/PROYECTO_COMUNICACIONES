"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { use, useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, getSessionProfile, useSessionContext } from "../../_lib/auth"
import {
  findCourseOption,
  getCourseCode,
  getCourseLabel,
  getCourseSchoolCourseId,
  loadCourseCatalog,
  resolveCanonicalCourseValue,
} from "../../_lib/courses"
import { ChevronLeft, Users } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

async function fetchJSON(url, opts) {
  const res = await authFetch(url, opts)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

function buildMisCursoSessionProfile(session) {
  const groups = Array.isArray(session?.groups) ? session.groups : []
  const username = String(session?.username || "").trim()
  const fullName = String(session?.userLabel || "").trim()
  const hasRoleData = groups.length > 0 || !!session?.isSuperuser || !!username || !!fullName
  if (!hasRoleData) return null
  return {
    username,
    full_name: fullName,
    groups,
    rol: String(session?.role || "").trim(),
    is_superuser: !!session?.isSuperuser,
    school: session?.school || null,
  }
}

const LAST_CURSO_KEY = "ultimo_curso_seleccionado"
const MIS_CURSO_RESOURCE_MAX_AGE_MS = 10000
const misCursoResourceCache = new Map()
const misCursoResourcePromises = new Map()

function invalidateMisCursoResource(cacheKeyPrefix = "") {
  const prefix = String(cacheKeyPrefix || "").trim()
  if (!prefix) return
  for (const key of Array.from(misCursoResourceCache.keys())) {
    if (key.startsWith(prefix)) {
      misCursoResourceCache.delete(key)
    }
  }
  for (const key of Array.from(misCursoResourcePromises.keys())) {
    if (key.startsWith(prefix)) {
      misCursoResourcePromises.delete(key)
    }
  }
}

async function loadMisCursoResource(
  cacheKey,
  loader,
  { force = false, maxAgeMs = MIS_CURSO_RESOURCE_MAX_AGE_MS } = {}
) {
  const key = String(cacheKey || "").trim()
  if (!key || typeof loader !== "function") {
    return await loader()
  }

  if (force) {
    invalidateMisCursoResource(key)
  }

  const cached = misCursoResourceCache.get(key)
  if (cached && cached.expiresAt > Date.now()) {
    return cached.data
  }

  if (misCursoResourcePromises.has(key)) {
    return await misCursoResourcePromises.get(key)
  }

  const promise = (async () => {
    const data = await loader()
    misCursoResourceCache.set(key, {
      data,
      expiresAt: Date.now() + maxAgeMs,
    })
    return data
  })()

  misCursoResourcePromises.set(key, promise)

  try {
    return await promise
  } finally {
    if (misCursoResourcePromises.get(key) === promise) {
      misCursoResourcePromises.delete(key)
    }
  }
}

const getInitials = (name) => {
  const s = String(name || "").trim()
  if (!s) return "—"
  const parts = s.split(/\s+/).filter(Boolean)
  const first = parts[0]?.[0] || ""
  const last = parts.length > 1 ? parts[parts.length - 1]?.[0] || "" : ""
  return (first + last).toUpperCase() || first.toUpperCase() || "—"
}

export default function CursoDetallePage({ params }) {
  useAuthGuard()
  const session = useSessionContext()
  const { cursoId } = use(params)
  const cursoParam = String(cursoId ?? "").trim()

  const [me, setMe] = useState(null)
  const [cursoNombre, setCursoNombre] = useState(cursoParam)
  const [cursos, setCursos] = useState([])
  const [alumnos, setAlumnos] = useState([])
  const [error, setError] = useState("")
  const [loadingAlumnos, setLoadingAlumnos] = useState(true)
  const [busqueda, setBusqueda] = useState("")
  const [catalogLoaded, setCatalogLoaded] = useState(false)

  const sessionBootstrapProfile = useMemo(
    () => buildMisCursoSessionProfile(session),
    [session?.groups, session?.isSuperuser, session?.role, session?.school, session?.userLabel, session?.username]
  )
  const misCursoScopeKey = useMemo(
    () => `${session?.username || me?.username || "anon"}:${session?.school?.id || "default"}`,
    [me?.username, session?.school?.id, session?.username]
  )
  const courseCatalogCacheKey = useMemo(
    () => `mis-cursos-detalle-catalog:${misCursoScopeKey}`,
    [misCursoScopeKey]
  )

  useEffect(() => {
    try {
      if (cursoParam) localStorage.setItem(LAST_CURSO_KEY, cursoParam)
    } catch {}
  }, [cursoParam])

  const router = useRouter()
  const searchParams = useSearchParams()
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
  const cursoDetalleQuery = useMemo(
    () =>
      cursoSchoolCourseId != null
        ? `school_course_id=${encodeURIComponent(String(cursoSchoolCourseId))}`
        : "",
    [cursoSchoolCourseId]
  )

  useEffect(() => {
    ;(async () => {
      try {
        const data = sessionBootstrapProfile || (await getSessionProfile())
        setMe(data)
      } catch {}
    })()
  }, [sessionBootstrapProfile])

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
        setCursos(nextCursos)
        const match = findCourseOption(nextCursos, cursoParam)
        setCursoNombre(getCourseLabel(match) || getCourseCode(match) || cursoParam)
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

  useEffect(() => {
    if (!catalogLoaded) return
    if (!cursoCanonico || cursoCanonico === cursoParam) return
    const qs = searchParams?.toString()
    router.replace(`/mis-cursos/${encodeURIComponent(cursoCanonico)}${qs ? `?${qs}` : ""}`)
  }, [catalogLoaded, cursoCanonico, cursoParam, router, searchParams])

  async function loadAlumnos() {
    if (!cursoParam) {
      setAlumnos([])
      setError("No se pudo resolver el curso.")
      setLoadingAlumnos(false)
      return
    }
    if (!cursoQuery) {
      if (!catalogLoaded) return
      setAlumnos([])
      setError("No se pudo resolver el curso.")
      setLoadingAlumnos(false)
      return
    }

    setLoadingAlumnos(true)
    setError("")
    try {
      const data = await loadMisCursoResource(
        `mis-curso-alumnos:${misCursoScopeKey}:${cursoQuery}`,
        async () => {
          const res = await authFetch(`/alumnos/?${cursoQuery}`)
          const j = await res.json().catch(() => ({}))
          if (!res.ok) {
            throw new Error(j?.detail || `Error ${res.status}`)
          }
          return Array.isArray(j?.alumnos) ? j.alumnos : []
        }
      )
      setAlumnos(data)
    } catch (e) {
      setError(e?.message || "No se pudieron cargar los alumnos.")
    } finally {
      setLoadingAlumnos(false)
    }
  }

  useEffect(() => {
    loadAlumnos()
  }, [catalogLoaded, cursoParam, cursoQuery, misCursoScopeKey])

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

  return (
    <div className="space-y-6">
      <div className="surface-card surface-card-pad">
        <Input
          placeholder="Buscar alumno por nombre o legajo"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
      </div>

      {error && (
        <div className="surface-card surface-card-pad text-red-600">{error}</div>
      )}

      {loadingAlumnos ? (
        <div className="surface-card surface-card-pad text-gray-600">
          Cargando alumnos...
        </div>
      ) : alumnosFiltrados.length === 0 ? (
        <div className="surface-card surface-card-pad text-gray-600">
          No se encontraron alumnos para este curso.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {alumnosFiltrados.map((a) => {
            const key = getAlumnoKey(a)
            const courseQuery = cursoDetalleQuery
            const detailParams = new URLSearchParams()
            if (courseQuery) {
              const sourceParams = new URLSearchParams(courseQuery)
              const schoolCourseId = sourceParams.get("school_course_id")
              if (schoolCourseId) detailParams.set("school_course_id", schoolCourseId)
            }
            detailParams.set("from", `/mis-cursos/${encodeURIComponent(cursoParam)}`)
            const href = key
              ? `/alumnos/${encodeURIComponent(key)}?${detailParams.toString()}`
              : null
            return href ? (
              <Link key={key} href={href} className="block">
                <Card className="surface-card hover:shadow-md transition-shadow">
                  <CardContent className="surface-card-pad">
                    <div className="flex items-start gap-3">
                      <div
                        className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 font-semibold text-sm"
                        style={{
                          backgroundColor: "var(--school-accent-soft)",
                          color: "var(--school-accent)",
                        }}
                      >
                        {getInitials(a?.nombre)}
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
              <Card key={`nolink-${a?.nombre}-${Math.random()}`} className="surface-card">
                <CardContent className="surface-card-pad">
                  <div className="flex items-start gap-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 font-semibold text-sm"
                      style={{
                        backgroundColor: "var(--school-accent-soft)",
                        color: "var(--school-accent)",
                      }}
                    >
                      {getInitials(a?.nombre)}
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
  )
}

