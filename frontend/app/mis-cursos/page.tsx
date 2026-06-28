"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, getSessionProfile, useSessionContext } from "../_lib/auth"
import {
  getCourseCode,
  getCourseLabel,
  getCourseValue,
  invalidateCourseCatalogCache,
  loadCourseCatalog,
} from "../_lib/courses"
import { Card, CardContent } from "@/components/ui/card"
import { BookOpen, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"

const CURSOS_VALIDOS = new Set([
  "1A",
  "1B",
  "2A",
  "2B",
  "3A",
  "3B",
  "4ECO",
  "4NAT",
  "5ECO",
  "5NAT",
  "6ECO",
  "6NAT",
])

function filterCursosValidos(list: any[]) {
  return list.filter((c: any) => {
    const code = String(getCourseCode(c) || getCourseValue(c) || "").trim()
    return CURSOS_VALIDOS.has(code)
  })
}

export default function MisCursosPage() {
  useAuthGuard()
  const session = useSessionContext()

  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [cursos, setCursos] = useState<any[]>([])
  const [reloadTick, setReloadTick] = useState(0)
  const cursosValidos = useMemo(() => filterCursosValidos(cursos), [cursos])
  const schoolCacheKey = useMemo(
    () =>
      `${session?.username || "anon"}:${session?.school?.id || session?.school?.slug || "default"}`,
    [session?.school?.id, session?.school?.slug, session?.username]
  )

  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoading(true)
      setError("")
      try {
        let list = []
        const profile =
          Array.isArray(session?.groups) && (session.groups.length > 0 || session.isSuperuser)
            ? { groups: session.groups, is_superuser: session.isSuperuser }
            : await getSessionProfile().catch(() => ({}))
        const groups = Array.isArray(profile?.groups) ? profile.groups : []
        const isPreceptor = groups.some((g: any) => String(g || "").toLowerCase().includes("precep"))
        const isDirectivo = groups.some((g: any) => String(g || "").toLowerCase().includes("directiv"))

        const preferredEndpoints = isDirectivo
          ? ["/api/notas/catalogos/", "/api/alumnos/cursos/"]
          : isPreceptor
          ? [
              "/api/preceptor/asistencias/cursos/",
              "/api/preceptor/cursos/",
              "/api/cursos/mis-cursos/",
            ]
          : [
              "/api/preceptor/asistencias/cursos/",
              "/api/preceptor/cursos/",
              "/api/cursos/mis-cursos/",
              "/api/notas/catalogos/",
            ]

        list = await loadCourseCatalog({
          fetcher: authFetch,
          urls: preferredEndpoints,
          cacheKey: `mis-cursos:${schoolCacheKey}:${isDirectivo ? "directivo" : isPreceptor ? "preceptor" : "docente"}`,
          force: reloadTick > 0,
          throwOnError: true,
        })

        if (alive) setCursos(filterCursosValidos(list))
      } catch (e) {
        if (alive) {
          setCursos([])
          setError((e instanceof Error ? e.message : null) || "No se pudieron cargar los cursos.")
        }
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [reloadTick, schoolCacheKey, session])

  return (
    <div className="space-y-6">
      {loading ? (
        <div className="surface-card surface-card-pad text-gray-600" role="status" aria-live="polite">
          Cargando cursos...
        </div>
      ) : error ? (
        <div className="surface-card surface-card-pad space-y-3 text-red-600" role="alert">
          <div>{error}</div>
          <Button
            type="button"
            variant="outline"
            className="gap-2"
            onClick={() => {
              invalidateCourseCatalogCache()
              setReloadTick((tick) => tick + 1)
            }}
          >
            <RefreshCcw className="h-4 w-4" />
            Reintentar
          </Button>
        </div>
      ) : cursosValidos.length === 0 ? (
        <div className="surface-card surface-card-pad text-gray-600">
          No tenés cursos asignados.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {cursosValidos.map((curso: any, idx: number) => {
            const id = getCourseValue(curso)
            const nombre = getCourseLabel(curso)
            return (
              <Link
                key={idx}
                href={`/mis-cursos/${encodeURIComponent(id)}`}
                className="block"
              >
                <Card className="surface-card hover:shadow-md transition-shadow">
                  <CardContent className="surface-card-pad">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-10 h-10 rounded-lg flex items-center justify-center"
                        style={{ backgroundColor: "var(--school-accent-soft)" }}
                      >
                        <BookOpen className="h-5 w-5" style={{ color: "var(--school-accent)" }} />
                      </div>
                      <h2 className="font-semibold text-slate-900">{nombre}</h2>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}