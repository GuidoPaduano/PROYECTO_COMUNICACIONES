"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { resolveSessionAlumnoRouteId } from "../_lib/auth"

export default function MisAsistenciasAlias() {
  const router = useRouter()

  useEffect(() => {
    ;(async () => {
      try {
        const alumnoId = await resolveSessionAlumnoRouteId()

        if (alumnoId) {
          router.replace(
            `/alumnos/${encodeURIComponent(alumnoId)}?from=mis-asistencias&tab=asistencias`
          )
        } else {
          router.replace("/dashboard")
        }
      } catch {
        router.replace("/login")
      }
    })()
  }, [router])

  return (
    <div className="flex items-center justify-center">
      <div className="surface-card surface-card-pad text-center text-gray-700 text-sm">
        Redirigiendo a <span className="font-semibold">Mis asistencias...</span>
      </div>
    </div>
  )
}
