"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, useSessionContext } from "../_lib/auth"
import { parseCourseListPayload } from "../_lib/courses"
import { BookOpen, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"

function getCursoId(c: any) {
  return c?.value ?? c?.id ?? c
}

function getCursoNombre(c: any) {
  return c?.label ?? c?.nombre ?? String(getCursoId(c))
}

export default function AlumnosPage() {
  useAuthGuard()
  const session = useSessionContext()

  const [cursos, setCursos] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [reloadTick, setReloadTick] = useState(0)
  const alumnosScopeKey = useMemo(
    () => `${session?.username || "anon"}:${session?.school?.id || "default"}`,
    [session?.school?.id, session?.username]
  )

  useEffect(() => {
    let alive = true
    ;(async () => {
      if (alive) {
        setLoading(true)
        setError("")
      }
      try {
        const res = await authFetch("/alumnos/cursos/")
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          throw new Error(data?.detail || "No se pudieron cargar los cursos.")
        }
        if (alive) setCursos(parseCourseListPayload(data))
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
  }, [alumnosScopeKey, reloadTick])

  return (
    <div className="space-y-6">
      <div className="surface-card surface-card-pad">
        {loading ? (
          <div className="text-sm text-gray-500" role="status" aria-live="polite">Cargando cursos...</div>
        ) : error ? (
          <div className="space-y-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
            <div>{error}</div>
            <Button
              type="button"
              variant="outline"
              className="gap-2"
              onClick={() => setReloadTick((tick) => tick + 1)}
            >
              <RefreshCcw className="h-4 w-4" />
              Reintentar
            </Button>
          </div>
        ) : cursos.length === 0 ? (
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