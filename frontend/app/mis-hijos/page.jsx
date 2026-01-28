"use client"

import Link from "next/link"
import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { useAuthGuard, authFetch } from "../_lib/auth"

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

const LAST_TAB_KEY = "mis_hijos_last_tab"
const LAST_ALUMNO_KEY = "mis_hijos_last_alumno"
const ALUMNO_DETAIL_CACHE_PREFIX = "alumno_detail_cache:"
const VALID_TABS = new Set(["notas", "sanciones", "asistencias"])

async function fetchJSON(url, opts) {
  const res = await authFetch(url, {
    ...opts,
    headers: { Accept: "application/json", ...(opts?.headers || {}) },
  })
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

function hijoRouteId(h) {
  return h?.id_alumno ?? h?.alumno_id ?? h?.legajo ?? h?.id ?? h?.pk ?? null
}

function safeGetLS(key) {
  try {
    if (typeof window === "undefined") return ""
    return localStorage.getItem(key) || ""
  } catch {
    return ""
  }
}

function safeSetLS(key, value) {
  try {
    if (typeof window === "undefined") return
    localStorage.setItem(key, String(value ?? ""))
  } catch {}
}

function safeSetLSJson(key, value) {
  try {
    if (typeof window === "undefined") return
    localStorage.setItem(key, JSON.stringify(value))
  } catch {}
}

export default function MisHijosPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center">
          <div className="surface-card surface-card-pad text-gray-700">Cargando...</div>
        </div>
      }
    >
      <MisHijosPageInner />
    </Suspense>
  )
}

function MisHijosPageInner() {
  useAuthGuard()

  const router = useRouter()
  const sp = useSearchParams()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const desiredAlumnoQS = sp?.get("alumno") || ""
  const desiredTabQS = (sp?.get("tab") || "").toLowerCase().trim()

  useEffect(() => {
    let alive = true

    ;(async () => {
      setLoading(true)
      setError("")

      try {
        const [hijosRes] = await Promise.all([
          (async () => {
            const tries = ["/padres/mis-hijos/", "/api/padres/mis-hijos/"]
            for (const url of tries) {
              try {
                const r = await fetchJSON(url)
                if (!r.ok) continue
                return r
              } catch {}
            }
            return { ok: false, data: {}, status: 0 }
          })(),
        ])

        if (!alive) return

        const arr = Array.isArray(hijosRes?.data)
          ? hijosRes.data
          : hijosRes?.data?.results || hijosRes?.data?.hijos || []

        const hijos = Array.isArray(arr) ? arr : []
        hijos.forEach((h) => {
          const id = hijoRouteId(h)
          if (!id) return
          safeSetLSJson(`${ALUMNO_DETAIL_CACHE_PREFIX}${id}`, {
            ts: Date.now(),
            data: h,
          })
        })
        const ids = hijos
          .map((h) => hijoRouteId(h))
          .filter((x) => x != null && String(x) !== "")
          .map((x) => String(x))

        if (ids.length === 0) {
          setError("No se encontraron alumnos asociados a tu cuenta.")
          return
        }

        const storedTab = safeGetLS(LAST_TAB_KEY).toLowerCase().trim()

        const chosenTab =
          (VALID_TABS.has(desiredTabQS) && desiredTabQS) ||
          (VALID_TABS.has(storedTab) && storedTab) ||
          "notas"

        if (VALID_TABS.has(desiredTabQS)) {
          safeSetLS(LAST_TAB_KEY, desiredTabQS)
        }

        const storedAlumno = safeGetLS(LAST_ALUMNO_KEY).trim()

        const chosenId =
          desiredAlumnoQS && ids.includes(String(desiredAlumnoQS))
            ? String(desiredAlumnoQS)
            : storedAlumno && ids.includes(String(storedAlumno))
              ? String(storedAlumno)
              : ids[0]

        safeSetLS(LAST_ALUMNO_KEY, chosenId)

        const qs = new URLSearchParams()
        qs.set("from", "/mis-hijos")

        if (VALID_TABS.has(desiredTabQS)) {
          qs.set("tab", String(desiredTabQS))
        }

        router.replace(`/alumnos/${encodeURIComponent(String(chosenId))}?${qs.toString()}`)
      } catch {
        if (!alive) return
        setError("No se pudo abrir el perfil de tus hijos. Proba de nuevo.")
      } finally {
        if (alive) setLoading(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [desiredAlumnoQS, desiredTabQS, router])

  return (
    <div className="space-y-6">
      {error ? (
        <Card>
          <CardContent className="space-y-4">
            <div className="text-red-600">{error}</div>
            <div className="flex gap-3">
              <Link href="/dashboard">
                <Button >Volver al panel</Button>
              </Link>
              <Button onClick={() => window.location.reload()}>Reintentar</Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent>
            <div className="text-gray-800 font-medium">
              {loading ? "Abriendo perfil del alumno..." : "Redirigiendo..."}
            </div>
            <div className="text-sm text-gray-600 mt-1">
              Te llevo directo al perfil del alumno.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

