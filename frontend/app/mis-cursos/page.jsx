"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useAuthGuard, authFetch } from "../_lib/auth"
import { Card, CardContent } from "@/components/ui/card"
import { BookOpen } from "lucide-react"

export default function MisCursosPage() {
  useAuthGuard()

  const [error, setError] = useState("")
  const [cursos, setCursos] = useState([])

  useEffect(() => {
    ;(async () => {
      try {
        const res = await authFetch("/notas/catalogos/")
        const j = await res.json().catch(() => ({}))
        if (!res.ok) {
          setError(j?.detail || `Error ${res.status}`)
          return
        }
        setCursos(j?.cursos || [])
      } catch {
        setError("No se pudieron cargar los cursos.")
      }
    })()
  }, [])

  const getCursoId = (c) => c?.id ?? c?.value ?? c
  const getCursoNombre = (c) => c?.nombre ?? c?.label ?? String(getCursoId(c))

  return (
    <div className="space-y-6">
      {error && (
        <div className="surface-card surface-card-pad text-red-600">{error}</div>
      )}

      {cursos.length === 0 ? (
        <div className="surface-card surface-card-pad text-gray-600">
          No tenes cursos asignados.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {cursos.map((curso, idx) => {
            const id = getCursoId(curso)
            const nombre = getCursoNombre(curso)
            return (
              <Link
                key={idx}
                href={`/mis-cursos/${encodeURIComponent(id)}`}
                className="block"
              >
                <Card className="hover:shadow-md transition-shadow">
                  <CardContent className="p-6">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center">
                        <BookOpen className="h-5 w-5 text-indigo-600" />
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
