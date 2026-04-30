"use client"

import Image from "next/image"
import Link from "next/link"
import { useEffect, useState } from "react"
import { Search, ArrowRight, Building2 } from "lucide-react"

import {
  DEFAULT_PUBLIC_BRANDING,
  DEFAULT_SCHOOL_LOGO_URL,
  buildApiUrl,
  buildSchoolLoginHref,
  getHostSchoolSlugFromWindow,
  usePublicSchoolBranding,
} from "./_lib/auth"

const TECNOVA_DIRECTORY_LOGO_URL = "/imagenes/tecnova(1).png"

function resolveDirectorySchoolLogo(school) {
  const rawLogo = String(school?.logo_url || "").trim()
  const schoolName = String(school?.name || school?.short_name || school?.slug || "").toLowerCase()
  const normalizedLogo = rawLogo.toLowerCase()
  const isTecnova = schoolName.includes("itnova") || schoolName.includes("tecnova")
  const usesLegacyTecnovaLogo = normalizedLogo.includes("tecnova(1).png")
  const usesGenericLogo =
    !rawLogo ||
    normalizedLogo.includes("alumnix") ||
    normalizedLogo === String(DEFAULT_SCHOOL_LOGO_URL).toLowerCase()

  if (isTecnova && (usesLegacyTecnovaLogo || usesGenericLogo)) {
    return TECNOVA_DIRECTORY_LOGO_URL
  }

  return rawLogo || DEFAULT_PUBLIC_BRANDING.logo_url
}

function SchoolCard({ school }) {
  const href = buildSchoolLoginHref(school)
  const accent = school?.accent_color || DEFAULT_PUBLIC_BRANDING.accent_color
  const logoSrc = resolveDirectorySchoolLogo(school)

  return (
    <Link
      href={href}
      className="group flex h-full flex-col justify-between rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
    >
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-slate-100 p-2"
            style={{ backgroundColor: `${school?.primary_color || DEFAULT_PUBLIC_BRANDING.primary_color}12` }}
          >
            <Image
              src={logoSrc}
              alt={school?.name ? `Logo de ${school.name}` : "Logo del colegio"}
              width={56}
              height={56}
              unoptimized
              className="h-full w-full object-contain"
            />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold text-slate-950">
              {school?.short_name || school?.name || "Colegio"}
            </h2>
          </div>
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between text-sm font-medium">
        <span style={{ color: accent }}>Entrar al colegio</span>
        <ArrowRight className="h-4 w-4 text-slate-400 transition group-hover:translate-x-0.5" />
      </div>
    </Link>
  )
}

export default function HomePage() {
  const branding = usePublicSchoolBranding({ fallback: DEFAULT_PUBLIC_BRANDING })
  const [schools, setSchools] = useState([])
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    const hostSchoolSlug = getHostSchoolSlugFromWindow()
    if (!hostSchoolSlug) return
    if (typeof window !== "undefined") {
      window.location.replace("/login")
    }
  }, [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const url = new URL(buildApiUrl("/public/schools/"))
        const res = await fetch(url.toString(), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
        if (!alive) return
        setSchools(Array.isArray(data?.schools) ? data.schools : [])
        setError("")
      } catch (err) {
        if (!alive) return
        setError(err?.message || "No se pudo cargar la lista de colegios.")
      } finally {
        if (alive) setLoading(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [])

  const normalizedQuery = String(query || "").trim().toLowerCase()
  const visibleSchools = !normalizedQuery
    ? schools
    : schools.filter((school) => {
        const haystack = [school?.name, school?.short_name, school?.slug]
          .map((value) => String(value || "").toLowerCase())
          .join(" ")
        return haystack.includes(normalizedQuery)
      })

  return (
    <div
      className="min-h-screen px-4 py-10 md:px-8"
      style={{
        backgroundImage: `linear-gradient(155deg, ${branding.primary_color}14 0%, #f8fafc 36%, ${branding.accent_color}14 100%)`,
      }}
    >
      <div className="mx-auto max-w-6xl space-y-8">
        <section className="overflow-hidden rounded-[32px] border border-slate-200 bg-white/95 shadow-sm backdrop-blur">
          <div className="px-6 py-8 md:px-8">
            <div className="space-y-5">
              <div className="flex items-center gap-4">
                <div
                  className="flex h-16 w-16 items-center justify-center rounded-3xl p-3"
                  style={{ backgroundColor: `${branding.primary_color}14` }}
                >
                  <Image
                    src={branding.logo_url}
                    alt={branding.name ? `Logo de ${branding.name}` : "Logo de Alumnix"}
                    width={64}
                    height={64}
                    unoptimized
                    className="h-full w-full object-contain"
                  />
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Alumnix
                  </p>
                  <h1 className="text-3xl font-semibold tracking-tight text-slate-950 md:text-4xl">
                    Elegí tu colegio
                  </h1>
                </div>
              </div>
              <div className="relative max-w-xl">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Buscar por nombre"
                  className="h-13 w-full rounded-2xl border border-slate-200 bg-slate-50 pl-12 pr-4 text-sm text-slate-900 outline-none transition focus:border-slate-300 focus:bg-white"
                />
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Building2 className="h-5 w-5 text-slate-500" />
            <h2 className="text-lg font-semibold text-slate-950">Colegios activos</h2>
          </div>

          {loading ? (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">
              Cargando colegios...
            </div>
          ) : error ? (
            <div className="rounded-3xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 shadow-sm">
              {error}
            </div>
          ) : visibleSchools.length ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {visibleSchools.map((school) => (
                <SchoolCard
                  key={school?.id ?? school?.slug ?? school?.name}
                  school={school}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">
              No encontramos colegios para esa búsqueda.
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
