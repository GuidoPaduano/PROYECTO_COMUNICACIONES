"use client"

import { useEffect, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { resolveSessionAlumnoRouteId } from "../_lib/auth"

export default function MisNotasAlias() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const tabParam = useMemo(() => {
    const raw = String(searchParams.get("tab") || "").toLowerCase().trim()
    return raw === "sanciones" || raw === "asistencias" ? raw : "notas"
  }, [searchParams])

  useEffect(() => {
    ;(async () => {
      try {
        const alumnoId = await resolveSessionAlumnoRouteId()

        if (alumnoId) {
          router.replace(
            `/alumnos/${encodeURIComponent(alumnoId)}?from=mis-notas&tab=${encodeURIComponent(tabParam)}`
          )
        } else {
          router.replace("/dashboard")
        }
      } catch {
        router.replace("/login")
      }
    })()
  }, [router, tabParam])

  return (
    <div className="flex items-center justify-center">
      <div className="surface-card surface-card-pad text-center text-gray-700 text-sm">
        Redirigiendo a <span className="font-semibold">Mis notas...</span>
      </div>
    </div>
  )
}
