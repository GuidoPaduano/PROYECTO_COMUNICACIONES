"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useAuthGuard, authFetch } from "../_lib/auth"
import { BookOpen } from "lucide-react"

async function fetchJSON(url) {
  const res = await authFetch(url)
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

function getCursoId(c) {
  return c?.id ?? c?.value ?? c
}

function getCursoNombre(c) {
  return c?.nombre ?? c?.label ?? String(getCursoId(c))
}

async function tryGetCursos() {
  {
    const r = await fetchJSON("/notas/catalogos/")
    if (r.ok && Array.isArray(r.data?.cursos)) return r.data.cursos
  }
  {
    const r = await fetchJSON("/cursos/")
    if (r.ok) return Array.isArray(r.data) ? r.data : r.data?.results || []
  }
  {
    const r = await fetchJSON("/cursos/list/")
    if (r.ok) return Array.isArray(r.data) ? r.data : r.data?.results || []
  }
  return []
}

export default function AlumnosPage() {
  useAuthGuard()

  const [cursos, setCursos] = useState([])

  useEffect(() => {
    let alive = true
    ;(async () => {
      const cs = await tryGetCursos()
      if (alive) setCursos(cs)
    })()
    return () => {
      alive = false
    }
  }, [])

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
