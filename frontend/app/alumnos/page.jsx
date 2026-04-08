"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, useSessionContext } from "../_lib/auth"
import { loadCourseCatalog } from "../_lib/courses"
import { BookOpen } from "lucide-react"

function getCursoId(c) {
  return c?.value ?? c?.id ?? c
}

function getCursoNombre(c) {
  return c?.label ?? c?.nombre ?? String(getCursoId(c))
}

export default function AlumnosPage() {
  useAuthGuard()
  const session = useSessionContext()

  const [cursos, setCursos] = useState([])
  const alumnosScopeKey = useMemo(
    () => `${session?.username || "anon"}:${session?.school?.id || "default"}`,
    [session?.school?.id, session?.username]
  )

  useEffect(() => {
    let alive = true
    ;(async () => {
      const cs = await loadCourseCatalog({
        cacheKey: `alumnos-cursos:${alumnosScopeKey}`,
        urls: ["/alumnos/cursos/"],
        fetcher: (url) => authFetch(url),
      })
      if (alive) setCursos(cs)
    })()
    return () => {
      alive = false
    }
  }, [alumnosScopeKey])

  return (
    <div className="space-y-6">
      <div className="surface-card surface-card-pad">
        {cursos.length === 0 ? (
          <div className="text-sm text-gray-600">No hay cursos para mostrar.</div>
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
