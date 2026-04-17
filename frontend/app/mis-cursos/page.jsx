"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, getSessionProfile, useSessionContext } from "../_lib/auth"
import {
  getCourseCode,
  getCourseLabel,
  getCourseValue,
  loadCourseCatalog,
} from "../_lib/courses"
import { Card, CardContent } from "@/components/ui/card"
import { BookOpen } from "lucide-react"

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

function filterCursosValidos(list) {
  return list.filter((c) => {
    const code = String(getCourseCode(c) || getCourseValue(c) || "").trim()
    return CURSOS_VALIDOS.has(code)
  })
}

export default function MisCursosPage() {
  useAuthGuard()
  const session = useSessionContext()

  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [cursos, setCursos] = useState([])
  const cursosValidos = useMemo(() => filterCursosValidos(cursos), [cursos])
  const schoolCacheKey = useMemo(
    () =>
      `${session?.username || "anon"}:${session?.school?.id || session?.school?.slug || "default"}`,
    [session?.school?.id, session?.school?.slug, session?.username]
  )

  useEffect(() => {
    ;(async () => {
      try {
        let list = []
        const profile =
          Array.isArray(session?.groups) && (session.groups.length > 0 || session.isSuperuser)
            ? { groups: session.groups, is_superuser: session.isSuperuser }
            : await getSessionProfile().catch(() => ({}))
        const groups = Array.isArray(profile?.groups) ? profile.groups : []
        const isPreceptor = groups.some((g) => String(g || "").toLowerCase().includes("precep"))
        const isDirectivo = groups.some((g) => String(g || "").toLowerCase().includes("directiv"))

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
        })

        setCursos(filterCursosValidos(list))
      } catch {
        setError("No se pudieron cargar los cursos.")
      } finally {
        setLoading(false)
      }
    })()
  }, [schoolCacheKey, session])

  return (
    <div className="space-y-6">
      {error && (
        <div className="surface-card surface-card-pad text-red-600">{error}</div>
      )}

      {loading ? (
        <div className="surface-card surface-card-pad text-gray-600">
          Cargando cursos...
        </div>
      ) : cursosValidos.length === 0 ? (
        <div className="surface-card surface-card-pad text-gray-600">
          No tenés cursos asignados.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {cursosValidos.map((curso, idx) => {
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
                      <h3 className="font-semibold text-slate-900">{nombre}</h3>
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
