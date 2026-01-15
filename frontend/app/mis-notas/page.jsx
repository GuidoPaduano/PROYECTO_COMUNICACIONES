"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { authFetch } from "../_lib/auth"

function alumnoRouteIdFromWhoami(me) {
  if (!me || typeof me !== "object") return null

  // 1) Preferimos legajo (id_alumno) si existe.
  const legajo =
    me?.alumno?.id_alumno ??
    me?.alumno_id ??
    me?.id_alumno ??
    me?.user?.alumno?.id_alumno ??
    me?.user?.alumno_id ??
    me?.user?.id_alumno

  if (legajo != null && String(legajo).trim() !== "") return String(legajo).trim()

  // 2) Si no hay legajo, caemos al PK del Alumno.
  const pk =
    me?.alumno?.id ??
    me?.alumno?.pk ??
    me?.user?.alumno?.id ??
    me?.user?.alumno?.pk

  if (pk != null && String(pk).trim() !== "") return String(pk).trim()

  // 3) Fallback útil: en muchos setups el username del alumno == legajo
  const uname = String(me?.username ?? me?.user?.username ?? "").trim()
  if (uname) return uname

  return null
}

// Alias: cualquier acceso a /mis-notas redirige a /alumnos/<identificador>
// usando el whoami del backend.
//
// IMPORTANTE:
// - /alumnos/[alumnoId] NO espera el id del User.
// - espera PK del Alumno o su legajo (id_alumno).
// - whoami ya expone un contexto estable: { alumno: { id, id_alumno, ... } }
export default function MisNotasAlias() {
  const router = useRouter()

  useEffect(() => {
    ;(async () => {
      try {
        const r = await authFetch("/auth/whoami/")
        const me = r.ok ? await r.json().catch(() => null) : null
        const alumnoId = alumnoRouteIdFromWhoami(me)

        if (alumnoId) {
          router.replace(
            `/alumnos/${encodeURIComponent(alumnoId)}?from=mis-notas&tab=notas`
          )
        } else {
          // Si no podemos inferir tu alumno, volvemos al dashboard (ahí ya hay mensaje/acción).
          router.replace("/dashboard")
        }
      } catch {
        router.replace("/login")
      }
    })()
  }, [router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      <div className="text-center text-gray-700 text-sm">
        Redirigiendo a <span className="font-semibold">Mis notas…</span>
      </div>
    </div>
  )
}
