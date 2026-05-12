"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, Building2, Layers3, Plus, RefreshCw, Save, Search } from "lucide-react"

import { DEFAULT_SCHOOL_PRIMARY_COLOR, authFetch, useAuthGuard, useSessionContext } from "../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const EMPTY_COURSE = {
  code: "",
  name: "",
  sort_order: 0,
  is_active: true,
}

function courseToForm(course) {
  return {
    id: course?.id ?? "",
    code: course?.code ?? "",
    name: course?.name ?? "",
    sort_order: Number(course?.sort_order || 0),
    is_active: course?.is_active !== false,
  }
}

function schoolStatusClasses(active) {
  return active
    ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
    : "bg-slate-100 text-slate-600 ring-slate-200"
}

export default function CursosPorColegioPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loadingSession = !sessionContext
  const allowed = !!sessionContext?.isSuperuser

  const [schools, setSchools] = useState([])
  const [selectedId, setSelectedId] = useState("")
  const [query, setQuery] = useState("")
  const [courseForms, setCourseForms] = useState({})
  const [newCourse, setNewCourse] = useState(EMPTY_COURSE)
  const [loading, setLoading] = useState(false)
  const [savingId, setSavingId] = useState("")
  const [creating, setCreating] = useState(false)
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

  const selectedCourses = useMemo(
    () => (Array.isArray(selectedSchool?.courses) ? selectedSchool.courses : []),
    [selectedSchool]
  )

  const loadData = async ({ keepSelection = true } = {}) => {
    setLoading(true)
    setError("")
    try {
      const params = new URLSearchParams()
      if (query.trim()) params.set("q", query.trim())
      const suffix = params.toString() ? `?${params.toString()}` : ""
      const res = await authFetch(`/admin/school-courses/${suffix}`)
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudieron cargar los cursos.")
        return
      }
      const items = Array.isArray(data?.schools) ? data.schools : []
      setSchools(items)
      const previous = keepSelection ? selectedId : ""
      const nextSelected =
        (previous && items.some((school) => String(school.id) === String(previous)) && previous) ||
        (items[0]?.id != null ? String(items[0].id) : "")
      setSelectedId(nextSelected)
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!allowed) return
    loadData({ keepSelection: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed])

  useEffect(() => {
    const nextForms = {}
    for (const course of selectedCourses) {
      nextForms[course.id] = courseToForm(course)
    }
    setCourseForms(nextForms)
    setNewCourse(EMPTY_COURSE)
    setError("")
    setSuccess("")
  }, [selectedCourses])

  const updateCourseField = (courseId, field, value) => {
    setCourseForms((current) => ({
      ...current,
      [courseId]: {
        ...courseToForm(selectedCourses.find((course) => String(course.id) === String(courseId))),
        ...(current[courseId] || {}),
        [field]: value,
      },
    }))
    setError("")
    setSuccess("")
  }

  const saveCourse = async (courseId) => {
    const form = courseForms[courseId]
    if (!form) return
    setSavingId(String(courseId))
    setError("")
    setSuccess("")
    try {
      const res = await authFetch(`/admin/school-courses/course/${courseId}`, {
        method: "PATCH",
        body: JSON.stringify({
          code: form.code,
          name: form.name,
          sort_order: form.sort_order,
          is_active: !!form.is_active,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo guardar el curso.")
        return
      }
      const updated = data?.school
      setSchools((current) => current.map((school) => (String(school.id) === String(updated?.id) ? updated : school)))
      setSuccess("Curso actualizado.")
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setSavingId("")
    }
  }

  const createCourse = async (event) => {
    event.preventDefault()
    if (!selectedSchool?.id) return
    setCreating(true)
    setError("")
    setSuccess("")
    try {
      const res = await authFetch(`/admin/school-courses/${selectedSchool.id}`, {
        method: "POST",
        body: JSON.stringify(newCourse),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo crear el curso.")
        return
      }
      const updated = data?.school
      setSchools((current) => current.map((school) => (String(school.id) === String(updated?.id) ? updated : school)))
      setNewCourse(EMPTY_COURSE)
      setSuccess("Curso creado.")
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setCreating(false)
    }
  }

  if (loadingSession || !allowed) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de cursos...</div>
      </div>
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
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Cursos por colegio</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Administra el catalogo de cursos de cada colegio.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => loadData()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}
      {success ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(620px,1.2fr)]">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Colegios</CardTitle>
            <CardDescription>Selecciona el colegio que queres editar.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="pl-9"
                placeholder="Buscar colegio"
              />
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-200">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Colegio</TableHead>
                    <TableHead>Cursos</TableHead>
                    <TableHead>Estado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleSchools.map((school) => {
                    const selected = String(school.id) === String(selectedId)
                    const active = school.is_active !== false
                    return (
                      <TableRow
                        key={school.id}
                        onClick={() => setSelectedId(String(school.id))}
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
                              <div className="truncate text-xs text-slate-500">{school.slug}</div>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-slate-600">{school.courses_count || 0}</TableCell>
                        <TableCell>
                          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${schoolStatusClasses(active)}`}>
                            {active ? "Activo" : "Inactivo"}
                          </span>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {!visibleSchools.length ? (
                    <TableRow>
                      <TableCell colSpan={3} className="py-8 text-center text-sm text-slate-500">
                        No hay colegios para mostrar.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Layers3 className="h-5 w-5" />
                Cursos
              </CardTitle>
              <CardDescription>
                {selectedSchool ? selectedSchool.name : "Selecciona un colegio para editar sus cursos."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Codigo</TableHead>
                      <TableHead>Nombre</TableHead>
                      <TableHead>Orden</TableHead>
                      <TableHead>Activo</TableHead>
                      <TableHead>Alumnos</TableHead>
                      <TableHead className="text-right">Accion</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedCourses.map((course) => {
                      const form = courseForms[course.id] || courseToForm(course)
                      return (
                        <TableRow key={course.id}>
                          <TableCell>
                            <Input
                              value={form.code}
                              onChange={(event) => updateCourseField(course.id, "code", event.target.value)}
                              className="h-9 min-w-24 font-mono text-xs"
                            />
                          </TableCell>
                          <TableCell>
                            <Input
                              value={form.name}
                              onChange={(event) => updateCourseField(course.id, "name", event.target.value)}
                              className="h-9 min-w-36"
                            />
                          </TableCell>
                          <TableCell>
                            <Input
                              type="number"
                              min="0"
                              value={form.sort_order}
                              onChange={(event) => updateCourseField(course.id, "sort_order", event.target.value)}
                              className="h-9 w-20"
                            />
                          </TableCell>
                          <TableCell>
                            <Checkbox
                              checked={form.is_active}
                              onCheckedChange={(checked) => updateCourseField(course.id, "is_active", checked === true)}
                            />
                          </TableCell>
                          <TableCell className="text-sm text-slate-600">{course.students_count || 0}</TableCell>
                          <TableCell className="text-right">
                            <Button
                              type="button"
                              size="sm"
                              onClick={() => saveCourse(course.id)}
                              disabled={savingId === String(course.id)}
                            >
                              <Save className="mr-2 h-4 w-4" />
                              {savingId === String(course.id) ? "Guardando" : "Guardar"}
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                    {!selectedCourses.length ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-8 text-center text-sm text-slate-500">
                          Este colegio todavia no tiene cursos.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Nuevo curso</CardTitle>
              <CardDescription>Agrega un curso al colegio seleccionado.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="grid gap-4 md:grid-cols-[120px_minmax(0,1fr)_100px_110px] md:items-end" onSubmit={createCourse}>
                <div className="space-y-2">
                  <Label htmlFor="new-course-code">Codigo</Label>
                  <Input
                    id="new-course-code"
                    value={newCourse.code}
                    onChange={(event) => setNewCourse((current) => ({ ...current, code: event.target.value }))}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-course-name">Nombre</Label>
                  <Input
                    id="new-course-name"
                    value={newCourse.name}
                    onChange={(event) => setNewCourse((current) => ({ ...current, name: event.target.value }))}
                    placeholder="Si queda vacio usa el codigo"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-course-order">Orden</Label>
                  <Input
                    id="new-course-order"
                    type="number"
                    min="0"
                    value={newCourse.sort_order}
                    onChange={(event) => setNewCourse((current) => ({ ...current, sort_order: event.target.value }))}
                  />
                </div>
                <Button type="submit" disabled={creating || !selectedSchool}>
                  <Plus className="mr-2 h-4 w-4" />
                  {creating ? "Creando" : "Crear"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
