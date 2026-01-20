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
    <div className="flex items-center justify-center">
      <div className="surface-card surface-card-pad text-sm text-gray-600">Cargando...</div>
    </div>
  )
}
