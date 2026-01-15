"use client"

import { useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { useAuthGuard } from "../../_lib/auth"

export default function GestionAlumnosCursoPage() {
  useAuthGuard()

  const router = useRouter()
  const params = useParams()
  const cursoId = params?.cursoId

  useEffect(() => {
    if (!cursoId) return
    const qs =
      typeof window !== "undefined" && window.location.search
        ? window.location.search
        : ""
    router.replace(`/mis-cursos/${cursoId}${qs}`)
  }, [cursoId, router])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white flex items-center justify-center">
      <div className="text-sm text-gray-600">Cargando…</div>
    </div>
  )
}
