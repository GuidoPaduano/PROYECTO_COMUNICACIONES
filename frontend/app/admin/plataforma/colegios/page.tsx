// @ts-nocheck
"use client"

import Link from "next/link"
import { useEffect, useMemo, useRef, useState } from "react"
import { ArrowLeft, Building2, CheckCircle2, MoreHorizontal, RefreshCw, Save, Search, Trash2, Upload } from "lucide-react"

import {
  DEFAULT_SCHOOL_ACCENT_COLOR,
  DEFAULT_SCHOOL_LOGO_URL,
  DEFAULT_SCHOOL_PRIMARY_COLOR,
  authFetch,
  syncSessionContext,
  useAuthGuard,
  useSessionContext,
} from "../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const EMPTY_FORM = {
  id: "",
  name: "",
  short_name: "",
  slug: "",
  logo_url: "",
  primary_color: "",
  accent_color: "",
  is_active: true,
}

function normalizeSchoolForForm(school) {
  if (!school || typeof school !== "object") return EMPTY_FORM
  return {
    id: school.id ?? "",
    name: school.name ?? "",
    short_name: school.short_name ?? "",
    slug: school.slug ?? "",
    logo_url: school.logo_url ?? "",
    primary_color: school.primary_color ?? "",
    accent_color: school.accent_color ?? "",
    is_active: school.is_active !== false,
  }
}

function flattenErrors(errors) {
  if (!errors || typeof errors !== "object") return []
  const lines = []
  for (const [field, value] of Object.entries(errors)) {
    const items = Array.isArray(value) ? value : [value]
    for (const item of items) lines.push(`${field}: ${String(item)}`)
  }
  return lines
}

function schoolStatusClasses(active) {
  return active
    ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
    : "bg-slate-100 text-slate-600 ring-slate-200"
}

function readableTextColor(backgroundColor) {
  const hex = String(backgroundColor || "").replace("#", "")
  if (!/^[0-9a-f]{6}$/i.test(hex)) return "#0f172a"
  const [r, g, b] = [0, 2, 4].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255)
  const linear = [r, g, b].map((value) =>
    value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  )
  const luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
  return luminance > 0.179 ? "#0f172a" : "#ffffff"
}

const DELETE_JOB_POLL_MS = 250
const DELETE_JOB_MAX_POLLS = 80

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export default function ColegiosPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loadingSession = !sessionContext
  const allowed = !!sessionContext?.isSuperuser
  const [schools, setSchools] = useState([])
  const [selectedId, setSelectedId] = useState("")
  const [form, setForm] = useState(EMPTY_FORM)
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [logoUploading, setLogoUploading] = useState(false)
  const [deletingId, setDeletingId] = useState("")
  const [openMenuId, setOpenMenuId] = useState("")
  const [deleteTarget, setDeleteTarget] = useState(null)
  const deleteDialogTriggerRef = useRef(null)
  const logoInputRef = useRef(null)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")

  const selectedSchool = useMemo(
    () => schools.find((school) => String(school.id) === String(selectedId)) || null,
    [schools, selectedId]
  )

  const visibleSchools = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return schools
    return schools.filter((school) =>
      [school.name, school.short_name, school.slug].some((value) =>
        String(value || "").toLowerCase().includes(needle)
      )
    )
  }, [query, schools])

  const loadSchools = async ({ keepSelection = true } = {}) => {
    setLoading(true)
    setError("")
    try {
      const res = await authFetch("/admin/schools")
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudieron cargar los colegios.")
        return
      }
      const items = Array.isArray(data?.schools) ? data.schools : []
      setSchools(items)
      const previous = keepSelection ? selectedId : ""
      const nextSelected =
        (previous && items.some((item) => String(item.id) === String(previous)) && previous) ||
        (items[0]?.id != null ? String(items[0].id) : "")
      setSelectedId(nextSelected)
      const nextSchool = items.find((item) => String(item.id) === String(nextSelected)) || null
      setForm(normalizeSchoolForForm(nextSchool))
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!allowed) return
    loadSchools({ keepSelection: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed])

  useEffect(() => {
    setForm(normalizeSchoolForForm(selectedSchool))
  }, [selectedSchool])

  const setField = (field) => (event) => {
    const value = event?.target?.value ?? ""
    setForm((current) => ({ ...current, [field]: value }))
  }

  const saveSchool = async (event) => {
    event.preventDefault()
    if (!form.id) return
    setSaving(true)
    setError("")
    setSuccess("")
    try {
      const payload = {
        name: form.name.trim(),
        short_name: form.short_name.trim(),
        slug: form.slug.trim(),
        logo_url: form.logo_url.trim(),
        primary_color: form.primary_color.trim(),
        accent_color: form.accent_color.trim(),
        is_active: !!form.is_active,
      }

      const res = await authFetch(`/admin/schools/${form.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const messages = flattenErrors(data?.errors)
        setError(messages[0] || data?.detail || "No se pudo guardar el colegio.")
        return
      }

      const updated = data?.school
      setSchools((current) =>
        current
          .map((school) => (String(school.id) === String(updated?.id) ? updated : school))
          .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")))
      )
      setForm(normalizeSchoolForForm(updated))
      syncSessionContext({
        school: data?.school || sessionContext?.school || null,
        available_schools: data?.available_schools || sessionContext?.availableSchools || [],
        is_superuser: true,
      })
      setSuccess("Colegio actualizado.")
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setSaving(false)
    }
  }

  const uploadLogo = async (event) => {
    const file = event?.target?.files?.[0]
    if (!file || !form.id) return

    setLogoUploading(true)
    setError("")
    setSuccess("")
    try {
      const body = new FormData()
      body.append("logo", file)

      const res = await authFetch(`/admin/schools/${form.id}/logo/`, {
        method: "POST",
        body,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo subir el logo.")
        return
      }

      const updated = data?.school
      setSchools((current) =>
        current
          .map((school) => (String(school.id) === String(updated?.id) ? updated : school))
          .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")))
      )
      setForm(normalizeSchoolForForm(updated))
      syncSessionContext({
        school: data?.school || sessionContext?.school || null,
        available_schools: data?.available_schools || sessionContext?.availableSchools || [],
        is_superuser: true,
      })
      setSuccess("Logo actualizado.")
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setLogoUploading(false)
      if (event?.target) event.target.value = ""
    }
  }

  const deleteSchool = async (school) => {
    if (!school?.id) return

    setDeletingId(String(school.id))
    setError("")
    setSuccess("")

    try {
      const res = await authFetch(`/admin/schools/${school.id}`, {
        method: "DELETE",
      })
      const data = await res.json().catch(() => ({}))

      if (!res.ok) {
        setError(data?.detail || "No se pudo borrar el colegio.")
        return
      }

      const jobId = data?.job?.id
      if (!jobId) {
        setError("El servidor no devolvio el estado del trabajo de borrado.")
        return
      }

      setDeleteTarget(null)
      setSuccess(data?.detail || "Borrado iniciado.")

      let finalJob = data.job
      for (let attempt = 0; attempt < DELETE_JOB_MAX_POLLS; attempt += 1) {
        if (finalJob?.status === "completed" || finalJob?.status === "failed") break
        await wait(DELETE_JOB_POLL_MS)
        const statusRes = await authFetch(`/admin/school-deletion-jobs/${jobId}`)
        const statusData = await statusRes.json().catch(() => ({}))
        if (!statusRes.ok) {
          setError(statusData?.detail || "No se pudo consultar el estado del borrado.")
          return
        }
        finalJob = statusData?.job
      }

      if (finalJob?.status !== "completed") {
        const deletionError =
          finalJob?.status === "failed"
            ? finalJob?.error || "El borrado del colegio fallo."
            : "El borrado sigue en proceso. Actualiza la pagina para consultar su estado."
        await loadSchools({ keepSelection: true })
        setSuccess("")
        setError(deletionError)
        return
      }

      setSchools((current) => current.filter((item) => String(item.id) !== String(school.id)))
      if (String(selectedId) === String(school.id)) {
        setSelectedId("")
        setForm(EMPTY_FORM)
      }
      syncSessionContext({
        school: data?.available_schools?.[0] || null,
        available_schools: data?.available_schools || [],
        is_superuser: true,
      })
      setSuccess("Colegio borrado correctamente.")
      await loadSchools({ keepSelection: true })
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setDeletingId("")
    }
  }

  if (loadingSession) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de colegios...</div>
      </div>
    )
  }

  if (!allowed) {
    return (
      <Card className="border-amber-200 bg-amber-50">
        <CardHeader>
          <CardTitle className="text-amber-950">Acceso restringido</CardTitle>
          <CardDescription className="text-amber-900">
            Esta herramienta es exclusiva para administradores de plataforma.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/admin/plataforma"
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver a admin plataforma
          </Link>
          <h2 className="mt-3 text-3xl font-semibold text-slate-900">Colegios</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Gestiona branding, slug y estado activo de cada colegio.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => loadSchools()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <Card className="min-w-0">
          <CardHeader className="pb-3">
            <CardTitle>Listado</CardTitle>
            <CardDescription>
              Incluye colegios activos e inactivos para administracion global.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="pl-9"
                placeholder="Buscar por nombre, nombre corto o slug"
              />
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Colegio</TableHead>
                    <TableHead>Slug</TableHead>
                    <TableHead>Datos</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead className="w-[56px] text-right">Acciones</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleSchools.map((school) => {
                    const active = school.is_active !== false
                    const selected = String(school.id) === String(selectedId)
                    return (
                      <TableRow
                        key={school.id}
                        onClick={() => {
                          setSelectedId(String(school.id))
                          setError("")
                          setSuccess("")
                        }}
                        className={`cursor-pointer ${selected ? "bg-slate-50" : ""}`}
                      >
                        <TableCell>
                          <div className="flex items-center gap-3">
                            <div
                              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white"
                              style={{ backgroundColor: school.primary_color || DEFAULT_SCHOOL_PRIMARY_COLOR }}
                            >
                              <Building2 className="h-4 w-4" />
                            </div>
                            <div className="min-w-0">
                              <div className="truncate font-medium text-slate-900">{school.name}</div>
                              <div className="truncate text-xs text-slate-500">{school.short_name || "Sin nombre corto"}</div>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-slate-600">{school.slug}</TableCell>
                        <TableCell className="text-xs text-slate-600">
                          {school.courses_count || 0} cursos · {school.students_count || 0} alumnos
                        </TableCell>
                        <TableCell>
                          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${schoolStatusClasses(active)}`}>
                            {active ? "Activo" : "Inactivo"}
                          </span>
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu
                            open={openMenuId === String(school.id)}
                            onOpenChange={(open) => {
                              setOpenMenuId(open ? String(school.id) : "")
                            }}
                          >
                            <DropdownMenuTrigger asChild>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 cursor-pointer focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  deleteDialogTriggerRef.current = event.currentTarget
                                  if (!selected) setSelectedId(String(school.id))
                                }}
                                disabled={deletingId === String(school.id)}
                                aria-label={`Acciones para ${school.name}`}
                              >
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-48">
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setOpenMenuId("")
                                  setTimeout(() => setDeleteTarget(school), 0)
                                }}
                                disabled={deletingId === String(school.id)}
                              >
                                <Trash2 className="h-4 w-4" />
                                {deletingId === String(school.id) ? "Borrando..." : "Borrar colegio"}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {!visibleSchools.length ? (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-sm text-slate-500">
                        No hay colegios para mostrar.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Editar colegio</CardTitle>
            <CardDescription>
              Los cambios impactan en el selector de colegios, login y branding.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-5" onSubmit={saveSchool}>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="school-name">Nombre</Label>
                  <Input id="school-name" value={form.name} onChange={setField("name")} required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="school-short-name">Nombre corto</Label>
                  <Input id="school-short-name" value={form.short_name} onChange={setField("short_name")} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="school-slug">Slug</Label>
                  <Input id="school-slug" value={form.slug} onChange={setField("slug")} required />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="school-logo-url">Logo URL</Label>
                  <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                    <Input id="school-logo-url" value={form.logo_url} onChange={setField("logo_url")} />
                    <input
                      ref={logoInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/gif"
                      className="hidden"
                      onChange={uploadLogo}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => logoInputRef.current?.click()}
                      disabled={!form.id || saving || logoUploading}
                    >
                      <Upload className="mr-2 h-4 w-4" />
                      {logoUploading ? "Subiendo..." : "Subir logo"}
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="school-primary-color">Color principal</Label>
                  <div className="grid grid-cols-[44px_minmax(0,1fr)] gap-2">
                    <Input
                      id="school-primary-color-picker"
                      type="color"
                      aria-label="Selector de color principal"
                      value={form.primary_color || DEFAULT_SCHOOL_PRIMARY_COLOR}
                      onChange={setField("primary_color")}
                      className="h-10 p-1"
                    />
                    <Input
                      id="school-primary-color"
                      value={form.primary_color}
                      onChange={setField("primary_color")}
                      placeholder={DEFAULT_SCHOOL_PRIMARY_COLOR}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="school-accent-color">Color de acento</Label>
                  <div className="grid grid-cols-[44px_minmax(0,1fr)] gap-2">
                    <Input
                      id="school-accent-color-picker"
                      type="color"
                      aria-label="Selector de color de acento"
                      value={form.accent_color || DEFAULT_SCHOOL_ACCENT_COLOR}
                      onChange={setField("accent_color")}
                      className="h-10 p-1"
                    />
                    <Input
                      id="school-accent-color"
                      value={form.accent_color}
                      onChange={setField("accent_color")}
                      placeholder={DEFAULT_SCHOOL_ACCENT_COLOR}
                    />
                  </div>
                </div>
              </div>

              <label className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-3">
                <Checkbox
                  checked={!!form.is_active}
                  onCheckedChange={(checked) =>
                    setForm((current) => ({ ...current, is_active: checked === true }))
                  }
                />
                <span className="text-sm font-medium text-slate-800">Colegio activo</span>
              </label>

              <div
                className="overflow-hidden rounded-xl border border-slate-200 bg-white"
                aria-label="Vista previa del branding"
              >
                <div
                  className="h-2"
                  style={{ backgroundColor: form.primary_color || DEFAULT_SCHOOL_PRIMARY_COLOR }}
                />
                <div className="flex items-center gap-4 p-4">
                  <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white">
                    <img
                      src={form.logo_url || DEFAULT_SCHOOL_LOGO_URL}
                      alt={`Vista previa del logo de ${form.name || "colegio"}`}
                      className="h-full w-full object-contain p-1"
                      onError={(event) => {
                        if (event.currentTarget.src.endsWith(DEFAULT_SCHOOL_LOGO_URL)) return
                        event.currentTarget.src = DEFAULT_SCHOOL_LOGO_URL
                      }}
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Vista previa
                    </div>
                    <div className="truncate text-lg font-semibold text-slate-900">
                      {form.short_name || form.name || "Nombre del colegio"}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                      <span
                        className="rounded-full px-2.5 py-1 font-semibold"
                        style={{
                          backgroundColor: form.primary_color || DEFAULT_SCHOOL_PRIMARY_COLOR,
                          color: readableTextColor(form.primary_color || DEFAULT_SCHOOL_PRIMARY_COLOR),
                        }}
                      >
                        Principal
                      </span>
                      <span
                        className="rounded-full px-2.5 py-1 font-semibold"
                        style={{
                          backgroundColor: form.accent_color || DEFAULT_SCHOOL_ACCENT_COLOR,
                          color: readableTextColor(form.accent_color || DEFAULT_SCHOOL_ACCENT_COLOR),
                        }}
                      >
                        Acento
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {error ? (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              ) : null}

              {success ? (
                <div role="status" aria-live="polite" className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                  <CheckCircle2 className="h-4 w-4" />
                  {success}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={saving || !form.id}>
                  <Save className="mr-2 h-4 w-4" />
                  {saving ? "Guardando..." : "Guardar cambios"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setForm(normalizeSchoolForForm(selectedSchool))}
                  disabled={!selectedSchool || saving}
                >
                  Descartar
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>

      <Dialog open={!!deleteTarget} onOpenChange={(open) => (!open ? setDeleteTarget(null) : null)}>
        <DialogContent
          className="sm:max-w-md"
          onKeyDown={(event) => {
            if (event.key === "Escape" && !deletingId) {
              event.preventDefault()
              setDeleteTarget(null)
            }
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            deleteDialogTriggerRef.current?.focus()
          }}
        >
          <DialogHeader>
            <DialogTitle>¿Seguro que quiere borrar este colegio?</DialogTitle>
            <DialogDescription>Esta acción es irreversible.</DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={!!deletingId}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => deleteSchool(deleteTarget)}
              disabled={!deleteTarget || !!deletingId}
            >
              {deletingId ? "Borrando..." : "Borrar colegio"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}