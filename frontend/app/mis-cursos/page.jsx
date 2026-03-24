"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../_lib/auth"
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
    const id = String(c?.id ?? c?.curso ?? c?.value ?? c ?? "").trim()
    return CURSOS_VALIDOS.has(id)
  })
}

function parseCursosPayload(payload) {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.results)) return payload.results
  if (Array.isArray(payload?.cursos)) return payload.cursos
  return []
}

export default function MisCursosPage() {
  useAuthGuard()

  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [cursos, setCursos] = useState([])
  const cursosValidos = useMemo(() => filterCursosValidos(cursos), [cursos])

  useEffect(() => {
    ;(async () => {
      try {
        let list = []
        let isPreceptor = false

        try {
          const who = await authFetch("/auth/whoami/")
          if (who.ok) {
            const data = await who.json().catch(() => ({}))
            const groups = Array.isArray(data?.groups) ? data.groups : []
            isPreceptor = groups.some((g) => {
              const name = String(g || "").toLowerCase()
              return name.includes("precep") || name.includes("directiv")
            })
          }
        } catch {}

        const preferredEndpoints = [
          "/preceptores/mis-cursos/",
          "/preceptor/cursos/",
          "/preceptor/asistencias/cursos/",
          "/cursos/mis-cursos/",
        ]

        for (const url of preferredEndpoints) {
          const res = await authFetch(url)
          if (!res.ok) continue
          const data = await res.json().catch(() => ({}))
          list = parseCursosPayload(data)
          if (list.length > 0) break
        }

        if (!isPreceptor && list.length === 0) {
          const r1 = await authFetch("/cursos/")
          if (r1.ok) {
            const data = await r1.json().catch(() => ({}))
            list = parseCursosPayload(data)
          }
        }

        if (!isPreceptor && list.length === 0) {
          const r2 = await authFetch("/cursos/list/")
          if (r2.ok) {
            const data = await r2.json().catch(() => ({}))
            list = parseCursosPayload(data)
          }
        }

        if (!isPreceptor && list.length === 0) {
          const res = await authFetch("/notas/catalogos/")
          const j = await res.json().catch(() => ({}))
          if (!res.ok) {
            setError(j?.detail || `Error ${res.status}`)
            return
          }
          list = j?.cursos || []
        }

        setCursos(filterCursosValidos(list))
      } catch {
        setError("No se pudieron cargar los cursos.")
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const getCursoId = (c) => c?.id ?? c?.curso ?? c?.value ?? c
  const getCursoNombre = (c) => c?.nombre ?? c?.label ?? String(getCursoId(c))

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
          No tenes cursos asignados.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {cursosValidos.map((curso, idx) => {
            const id = getCursoId(curso)
            const nombre = getCursoNombre(curso)
            return (
              <Link
                key={idx}
                href={`/mis-cursos/${encodeURIComponent(id)}`}
                className="block"
              >
                <Card className="surface-card hover:shadow-md transition-shadow">
                  <CardContent className="surface-card-pad">
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
