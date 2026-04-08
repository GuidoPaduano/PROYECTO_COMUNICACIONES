"use client"

import Link from "next/link"
import { useMemo, useState } from "react"
import { ArrowLeft, Building2, CheckCircle2, Sparkles } from "lucide-react"

import {
  DEFAULT_SCHOOL_ACCENT_COLOR,
  DEFAULT_SCHOOL_PRIMARY_COLOR,
  authFetch,
  syncSessionContext,
  useAuthGuard,
  useSessionContext,
} from "../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const INITIAL_FORM = {
  name: "",
  short_name: "",
  slug: "",
  logo_url: "",
  primary_color: "",
  accent_color: "",
}

function slugPreview(value) {
  const raw = String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
  return raw || "colegio"
}

function flattenErrors(errors) {
  if (!errors || typeof errors !== "object") return []
  const lines = []
  for (const [field, value] of Object.entries(errors)) {
    const items = Array.isArray(value) ? value : [value]
    for (const item of items) {
      lines.push(`${field}: ${String(item)}`)
    }
  }
  return lines
}

export default function NuevoColegioPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loading = !sessionContext
  const allowed = !!sessionContext?.isSuperuser
  const [form, setForm] = useState(INITIAL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [created, setCreated] = useState(null)

  const generatedSlug = useMemo(
    () => slugPreview(form.slug || form.name),
    [form.name, form.slug]
  )

  const handleFieldChange = (field) => (event) => {
    const value = event?.target?.value ?? ""
    setForm((current) => ({ ...current, [field]: value }))
  }

  const handleCreateAnother = () => {
    setCreated(null)
    setError("")
    setForm(INITIAL_FORM)
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError("")

    try {
      const payload = {
        name: form.name.trim(),
        short_name: form.short_name.trim(),
        slug: form.slug.trim(),
        logo_url: form.logo_url.trim(),
        primary_color: form.primary_color.trim(),
        accent_color: form.accent_color.trim(),
        is_active: true,
      }

      const res = await authFetch("/admin/schools/", {
        method: "POST",
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))

      if (!res.ok) {
        const messages = flattenErrors(data?.errors)
        setError(messages[0] || data?.detail || "No se pudo crear el colegio.")
        return
      }

      syncSessionContext({
        school: data?.school || null,
        available_schools: data?.available_schools || [],
        is_superuser: true,
      })
      setCreated(data)
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setSubmitting(false)
    }
  }

  if (loading || !allowed) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de colegios...</div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Link
            href="/admin"
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver al panel admin
          </Link>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Nuevo colegio</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Crea un colegio nuevo, deja el branding inicial listo y siembra el catálogo base de cursos.
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card>
          <CardHeader>
            <CardTitle>Alta de colegio</CardTitle>
            <CardDescription>
              Si dejás `slug` vacío, se genera automáticamente. Los colores también pueden quedar vacíos para usar el default de la plataforma.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {created ? (
              <div className="space-y-5">
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
                    <div className="space-y-1">
                      <p className="text-sm font-semibold">Colegio creado correctamente</p>
                      <p className="text-sm">
                        {created?.school?.name} ya quedó disponible en tu sesión.
                      </p>
                      <p className="text-sm">
                        `slug`: {created?.school?.slug} · cursos creados: {created?.seeded_courses}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3">
                  <Button type="button" onClick={handleCreateAnother}>
                    Crear otro colegio
                  </Button>
                  <Link href="/dashboard">
                    <Button type="button" variant="outline">
                      Ir al dashboard con este colegio
                    </Button>
                  </Link>
                </div>
              </div>
            ) : (
              <form className="space-y-5" onSubmit={handleSubmit}>
                <div className="grid gap-5 sm:grid-cols-2">
                  <div className="space-y-2 sm:col-span-2">
                    <Label htmlFor="school-name">Nombre</Label>
                    <Input
                      id="school-name"
                      value={form.name}
                      onChange={handleFieldChange("name")}
                      placeholder="Ej. Colegio San Martin"
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="school-short-name">Nombre corto</Label>
                    <Input
                      id="school-short-name"
                      value={form.short_name}
                      onChange={handleFieldChange("short_name")}
                      placeholder="Ej. San Martin"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="school-slug">Slug</Label>
                    <Input
                      id="school-slug"
                      value={form.slug}
                      onChange={handleFieldChange("slug")}
                      placeholder={generatedSlug}
                    />
                    <p className="text-xs text-slate-500">Preview: {generatedSlug}</p>
                  </div>

                  <div className="space-y-2 sm:col-span-2">
                    <Label htmlFor="school-logo-url">Logo URL</Label>
                    <Input
                      id="school-logo-url"
                      value={form.logo_url}
                      onChange={handleFieldChange("logo_url")}
                      placeholder="/imagenes/Logo%20Color.png"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="school-primary-color">Color principal</Label>
                    <Input
                      id="school-primary-color"
                      value={form.primary_color}
                      onChange={handleFieldChange("primary_color")}
                      placeholder={DEFAULT_SCHOOL_PRIMARY_COLOR}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="school-accent-color">Color de acento</Label>
                    <Input
                      id="school-accent-color"
                      value={form.accent_color}
                      onChange={handleFieldChange("accent_color")}
                      placeholder={DEFAULT_SCHOOL_ACCENT_COLOR}
                    />
                  </div>
                </div>

                {error ? (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {error}
                  </div>
                ) : null}

                <div className="flex flex-wrap gap-3">
                  <Button type="submit" disabled={submitting}>
                    {submitting ? "Creando colegio..." : "Crear colegio"}
                  </Button>
                  <Link href="/admin">
                    <Button type="button" variant="outline">
                      Cancelar
                    </Button>
                  </Link>
                </div>
              </form>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5" />
                Qué hace esta herramienta
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
              <p>Crea el registro del colegio.</p>
              <p>Lo deja activo para que aparezca en tu selector de colegios.</p>
              <p>Siembra automáticamente el catálogo base de cursos: 1A, 1B, 2A, 2B, 3A, 3B, 4ECO, 4NAT, 5ECO, 5NAT, 6ECO y 6NAT.</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5" />
                Recomendación
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
              <p>Después del alta, el siguiente paso sano es cargar usuarios y asignaciones dentro de ese colegio.</p>
              <p>Si el colegio necesita un catálogo distinto de cursos, lo siguiente sería agregar una herramienta específica para editar esos `SchoolCourse`.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
