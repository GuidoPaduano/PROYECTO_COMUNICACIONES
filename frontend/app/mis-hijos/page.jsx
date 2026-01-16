"use client"

import Link from "next/link"
import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { useAuthGuard, authFetch } from "../_lib/auth"
import { useUnreadCount } from "../_lib/useUnreadCount"
import { NotificationBell } from "@/components/notification-bell"

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

import { ChevronLeft, Mail, Users as UsersIcon } from "lucide-react"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

/* ======================== LocalStorage keys ======================== */
const LAST_TAB_KEY = "mis_hijos_last_tab" // "notas" | "sanciones" | "asistencias"
const LAST_ALUMNO_KEY = "mis_hijos_last_alumno"
const ALUMNO_DETAIL_CACHE_PREFIX = "alumno_detail_cache:"
const VALID_TABS = new Set(["notas", "sanciones", "asistencias"])

/* ======================== Helpers ======================== */
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

/* ======================== Page ======================== */
export default function MisHijosPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white flex items-center justify-center">
          <div className="text-gray-700">Cargando...</div>
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

  const [me, setMe] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const unreadCount = useUnreadCount()

  // query params (si vienen, tienen prioridad)
  const desiredAlumnoQS = sp?.get("alumno") || ""
  const desiredTabQS = (sp?.get("tab") || "").toLowerCase().trim()

  useEffect(() => {
    let alive = true

    ;(async () => {
      setLoading(true)
      setError("")

      try {
        const [who, hijosRes] = await Promise.all([
          fetchJSON("/auth/whoami/"),
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
        if (who.ok) setMe(who.data || null)

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

        // ========= TAB: QS > localStorage (solo para guardar) =========
        // ✅ FIX: NO forzar tab si no viene por QS.
        // - Si viene tab válido por QS, lo usamos y lo guardamos.
        // - Si NO viene tab por QS, NO lo mandamos al perfil (así el perfil usa su última pestaña).
        const storedTab = safeGetLS(LAST_TAB_KEY).toLowerCase().trim()

        const chosenTab =
          (VALID_TABS.has(desiredTabQS) && desiredTabQS) ||
          (VALID_TABS.has(storedTab) && storedTab) ||
          "notas"

        // si vino tab por QS y es válida, la guardamos como "última"
        if (VALID_TABS.has(desiredTabQS)) {
          safeSetLS(LAST_TAB_KEY, desiredTabQS)
        }

        // ========= ALUMNO: QS (si existe) > localStorage (si existe) > primero =========
        const storedAlumno = safeGetLS(LAST_ALUMNO_KEY).trim()

        const chosenId =
          desiredAlumnoQS && ids.includes(String(desiredAlumnoQS))
            ? String(desiredAlumnoQS)
            : storedAlumno && ids.includes(String(storedAlumno))
              ? String(storedAlumno)
              : ids[0]

        // guardamos último alumno abierto
        safeSetLS(LAST_ALUMNO_KEY, chosenId)

        const qs = new URLSearchParams()
        qs.set("from", "/mis-hijos")

        // ✅ FIX CLAVE: solo seteamos tab si realmente viene en la URL (QS).
        // Si no viene, dejamos que el perfil decida (última pestaña guardada en el perfil).
        if (VALID_TABS.has(desiredTabQS)) {
          qs.set("tab", String(desiredTabQS))
        }

        // ✅ REDIRECT DIRECTO al perfil del alumno
        router.replace(
          `/alumnos/${encodeURIComponent(String(chosenId))}?${qs.toString()}`
        )
      } catch {
        if (!alive) return
        setError("No se pudo abrir el perfil de tus hijos. Probá de nuevo.")
      } finally {
        if (alive) setLoading(false)
      }
    })()

    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desiredAlumnoQS, desiredTabQS])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      <Topbar unreadCount={unreadCount} me={me} />

      <div className="max-w-3xl mx-auto px-6 py-10">
        {error ? (
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="text-red-600">{error}</div>
              <div className="flex gap-3">
                <Link href="/dashboard">
                  <Button variant="outline">Volver al panel</Button>
                </Link>
                <Button onClick={() => window.location.reload()}>Reintentar</Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
            <CardContent className="pt-6">
              <div className="text-gray-800 font-medium">
                {loading ? "Abriendo perfil del alumno…" : "Redirigiendo…"}
              </div>
              <div className="text-sm text-gray-600 mt-1">
                Te llevo directo al perfil del alumno.
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

/* ======================== UI ======================== */
function Topbar({ unreadCount, me }) {
  const userLabel =
    (me?.full_name && String(me.full_name).trim()) ||
    me?.username ||
    [me?.user?.first_name, me?.user?.last_name].filter(Boolean).join(" ") ||
    "Usuario"

  return (
    <div className="bg-blue-600 text-white px-6 py-4">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="inline-flex">
            <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center overflow-hidden">
              <img
                src={LOGO_SRC}
                alt="Escuela Santa Teresa"
                className="h-full w-full object-contain"
              />
            </div>
          </Link>
          <h1 className="text-xl font-semibold">Perfil de alumno</h1>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/dashboard">
            <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
              <ChevronLeft className="h-4 w-4" />
              Volver al panel
            </Button>
          </Link>

          <NotificationBell unreadCount={unreadCount} />

          <div className="relative">
            <Link href="/mensajes">
              <Button
                variant="ghost"
                size="icon"
                className="text-white hover:bg-blue-700"
              >
                <Mail className="h-5 w-5" />
              </Button>
            </Link>
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 text-[10px] leading-none px-1.5 py-0.5 rounded-full bg-red-600 text-white border border-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </div>

          {/* ✅ FIX: icono correcto */}
          <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
            <UsersIcon className="h-4 w-4" />
            {userLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
