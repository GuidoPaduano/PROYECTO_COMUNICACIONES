"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { authFetch } from "../_lib/auth"

function alumnoRouteIdFromWhoami(me) {
  if (!me || typeof me !== "object") return null

  const legajo =
    me?.alumno?.id_alumno ??
    me?.alumno_id ??
    me?.id_alumno ??
    me?.user?.alumno?.id_alumno ??
    me?.user?.alumno_id ??
    me?.user?.id_alumno

  if (legajo != null && String(legajo).trim() !== "") return String(legajo).trim()

  const pk =
    me?.alumno?.id ??
    me?.alumno?.pk ??
    me?.user?.alumno?.id ??
    me?.user?.alumno?.pk

  if (pk != null && String(pk).trim() !== "") return String(pk).trim()

  const uname = String(me?.username ?? me?.user?.username ?? "").trim()
  if (uname) return uname

  return null
}

export default function MisAsistenciasAlias() {
  const router = useRouter()

  useEffect(() => {
    ;(async () => {
      try {
        const r = await authFetch("/auth/whoami/")
        const me = r.ok ? await r.json().catch(() => null) : null
        const alumnoId = alumnoRouteIdFromWhoami(me)

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
