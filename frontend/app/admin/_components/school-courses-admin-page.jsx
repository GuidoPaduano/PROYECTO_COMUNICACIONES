"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, Building2, Layers3, Plus, RefreshCw, Save, Search } from "lucide-react"

import {
  DEFAULT_SCHOOL_PRIMARY_COLOR,
  authFetch,
  getRequestedSchoolIdentifierFromWindow,
  useAuthGuard,
  useSessionContext,
} from "../../_lib/auth"
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
  name: "",
  is_active: true,
}

function getCoursesCacheKey(mode, schoolRef) {
  const scope = String(schoolRef || "default").trim() || "default"
  return `admin_school_courses:${mode}:${scope}`
}

function getSchoolIdentityTokens(school) {
  const tokens = new Set()
  const push = (value) => {
    const normalized = String(value || "").trim().toLowerCase()
    if (normalized) tokens.add(normalized)
  }
  push(school?.slug)
  push(school?.id)
  push(school?.name)
  push(school?.short_name)
  return tokens
}

function matchesSchoolRef(school, schoolRefs) {
  const refs = Array.isArray(schoolRefs) ? schoolRefs : [schoolRefs]
  const normalizedRefs = refs
    .map((value) => String(value || "").trim().toLowerCase())
    .filter(Boolean)
  if (!normalizedRefs.length) return true
  const schoolTokens = getSchoolIdentityTokens(school)
  return normalizedRefs.some((ref) => schoolTokens.has(ref))
}

function readCoursesCache(mode, schoolRef) {
  try {
    if (typeof window === "undefined") return null
    const raw = window.sessionStorage.getItem(getCoursesCacheKey(mode, schoolRef))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed?.schools)) return null
    if (mode !== "platform") {
      const scoped = parsed.schools.filter((school) => matchesSchoolRef(school, schoolRef))
      return scoped.length ? { schools: scoped } : null
    }
    return parsed
  } catch {
    return null
  }
}

function writeCoursesCache(mode, schoolRef, payload) {
  try {
    if (typeof window === "undefined") return
    if (!Array.isArray(payload?.schools)) return
    window.sessionStorage.setItem(
      getCoursesCacheKey(mode, schoolRef),
      JSON.stringify({ schools: payload.schools })
    )
  } catch {}
}

function courseToForm(course) {
  return {
    id: course?.id ?? "",
    name: course?.name ?? "",
    is_active: course?.is_active !== false,
  }
}

function buildCourseCodeFromName(name = "") {
  const normalized = String(name || "")
    .trim()
    .toUpperCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Z0-9]+/g, "")
    .slice(0, 20)
  return normalized || "CURSO"
}

function schoolStatusClasses(active) {
  return active
    ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
    : "bg-slate-100 text-slate-600 ring-slate-200"
}

function isSchoolAdminContext(sessionContext) {
  if (sessionContext?.isSuperuser) return true
  const groups = Array.isArray(sessionContext?.groups) ? sessionContext.groups : []
  return groups.some((group) => {
    const value = String(group || "").toLowerCase()
    return value === "administradores" || value === "administrador"
  })
}

export function SchoolCoursesAdminPage({ mode = "platform" }) {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loadingSession = !sessionContext
  const isPlatformMode = mode === "platform"
  const allowed = isPlatformMode ? !!sessionContext?.isSuperuser : isSchoolAdminContext(sessionContext)
  const sessionSchoolRefs = useMemo(
    () => {
      if (isPlatformMode) return []
      const requested = getRequestedSchoolIdentifierFromWindow()
      const values = [
        requested,
        sessionContext?.school?.slug,
        sessionContext?.school?.id,
        sessionContext?.school?.name,
        sessionContext?.school?.short_name,
      ]
      return values
        .map((value) => String(value || "").trim())
        .filter((value, index, array) => value && array.indexOf(value) === index)
    },
    [isPlatformMode, sessionContext]
  )

  const [schools, setSchools] = useState(() => {
    const cacheRef = sessionSchoolRefs[0] || ""
    const cached = readCoursesCache(mode, cacheRef)
    return Array.isArray(cached?.schools) ? cached.schools : []
  })
  const [selectedId, setSelectedId] = useState("")
  const [query, setQuery] = useState("")
  const [courseForms, setCourseForms] = useState({})
  const [newCourse, setNewCourse] = useState(EMPTY_COURSE)
  const [loading, setLoading] = useState(false)
  const [savingId, setSavingId] = useState("")
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")

  const backHref = isPlatformMode ? "/admin/plataforma" : "/admin/colegio"
  const backLabel = isPlatformMode ? "Volver a admin plataforma" : "Volver a admin colegio"

  const selectedSchool = useMemo(
    () => schools.find((school) => String(school.id) === String(selectedId)) || null,
    [schools, selectedId]
  )

  const visibleSchools = useMemo(() => {
    if (!isPlatformMode) return schools
    const needle = query.trim().toLowerCase()
    if (!needle) return schools
    return schools.filter((school) =>
      [school.name, school.short_name, school.slug].some((value) =>
        String(value || "").toLowerCase().includes(needle)
      )
    )
  }, [isPlatformMode, query, schools])

  const selectedCourses = useMemo(
    () => (Array.isArray(selectedSchool?.courses) ? selectedSchool.courses : []),
    [selectedSchool]
  )

  const loadData = async ({ keepSelection = true } = {}) => {
    setLoading(true)
    setError("")
    try {
      const params = new URLSearchParams()
      if (isPlatformMode && query.trim()) params.set("q", query.trim())
      if (!isPlatformMode && sessionSchoolRefs[0]) params.set("school", String(sessionSchoolRefs[0]))
      const suffix = params.toString() ? `?${params.toString()}` : ""
      const res = await authFetch(`/admin/school-courses/${suffix}`, {
        headers: !isPlatformMode && sessionSchoolRefs[0] ? { "X-School": String(sessionSchoolRefs[0]) } : undefined,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudieron cargar los cursos.")
        return
      }
      const rawItems = Array.isArray(data?.schools) ? data.schools : []
      const items = !isPlatformMode ? rawItems.filter((school) => matchesSchoolRef(school, sessionSchoolRefs)) : rawItems
      if (!isPlatformMode && rawItems.length && !items.length) {
        setSchools([])
        setSelectedId("")
        setError("La herramienta recibió cursos de un colegio distinto al activo. Recargá la sesión antes de editar.")
        return
      }
      setSchools(items)
      writeCoursesCache(mode, sessionSchoolRefs[0] || "", { schools: items })
      const previous = keepSelection ? selectedId : ""
      const sessionSelectedId =
        !isPlatformMode
          ? String(
              items.find((school) => matchesSchoolRef(school, sessionSchoolRefs))?.id ?? ""
            )
          : ""
      const nextSelected =
        (sessionSelectedId && items.some((school) => String(school.id) === String(sessionSelectedId)) && sessionSelectedId) ||
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
    const cached = readCoursesCache(mode, sessionSchoolRefs[0] || "")
    if (!Array.isArray(cached?.schools) || !cached.schools.length) return
    setSchools(cached.schools)
    setSelectedId((current) => {
      if (current && cached.schools.some((school) => String(school.id) === String(current))) return current
      return cached.schools[0]?.id != null ? String(cached.schools[0].id) : ""
    })
  }, [mode, sessionSchoolRefs])

  useEffect(() => {
    if (!allowed) return
    if (!isPlatformMode && !sessionSchoolRefs.length) return
    loadData({ keepSelection: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed, isPlatformMode, sessionSchoolRefs])

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
        headers: !isPlatformMode && sessionSchoolRefs[0] ? { "X-School": String(sessionSchoolRefs[0]) } : undefined,
        body: JSON.stringify({
          name: form.name,
          is_active: !!form.is_active,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo guardar el curso.")
        return
      }
      const updated = data?.school
      setSchools((current) => {
        const next = current.map((school) => (String(school.id) === String(updated?.id) ? updated : school))
        writeCoursesCache(mode, sessionSchoolRefs[0] || "", { schools: next })
        return next
      })
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
        headers: !isPlatformMode && sessionSchoolRefs[0] ? { "X-School": String(sessionSchoolRefs[0]) } : undefined,
        body: JSON.stringify({
          code: buildCourseCodeFromName(newCourse.name),
          name: newCourse.name,
          sort_order: selectedCourses.length + 1,
          is_active: true,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo crear el curso.")
        return
      }
      const updated = data?.school
      setSchools((current) => {
        const next = current.map((school) => (String(school.id) === String(updated?.id) ? updated : school))
        writeCoursesCache(mode, sessionSchoolRefs[0] || "", { schools: next })
        return next
      })
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
    <div className="mx-auto max-w-6xl space-y-5 min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href={backHref}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            {backLabel}
          </Link>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Cursos por colegio</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            {isPlatformMode
              ? "Administra el catálogo de cursos de cada colegio."
              : "Administra el catálogo de cursos del colegio activo de la sesión."}
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

      <div className={`grid gap-5 ${isPlatformMode ? "2xl:grid-cols-[minmax(0,0.82fr)_minmax(520px,1.18fr)]" : ""}`}>
        {isPlatformMode ? (
          <Card className="min-w-0">
            <CardHeader className="pb-3">
              <CardTitle>Colegios</CardTitle>
              <CardDescription>Seleccioná el colegio que querés editar.</CardDescription>
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

              <div className="min-w-0">
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
        ) : null}

        <div className="min-w-0 space-y-6">
          <Card className="min-w-0">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2">
                <Layers3 className="h-5 w-5" />
                Cursos
              </CardTitle>
              <CardDescription>
                {selectedSchool ? selectedSchool.name : "Seleccioná un colegio para editar sus cursos."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-0">
              <div className="min-w-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[58%]">Nombre</TableHead>
                      <TableHead className="w-[12%]">Activo</TableHead>
                      <TableHead className="w-[12%]">Alumnos</TableHead>
                      <TableHead className="text-right">Acción</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedCourses.map((course) => {
                      const form = courseForms[course.id] || courseToForm(course)
                      return (
                        <TableRow key={course.id}>
                          <TableCell className="py-2.5">
                            <Input
                              value={form.name}
                              onChange={(event) => updateCourseField(course.id, "name", event.target.value)}
                              className="h-8 min-w-0"
                            />
                          </TableCell>
                          <TableCell className="py-2.5">
                            <Checkbox
                              checked={form.is_active}
                              onCheckedChange={(checked) => updateCourseField(course.id, "is_active", checked === true)}
                            />
                          </TableCell>
                          <TableCell className="py-2.5 text-sm text-slate-600">{course.students_count || 0}</TableCell>
                          <TableCell className="py-2.5 text-right">
                            <Button
                              type="button"
                              size="sm"
                              onClick={() => saveCourse(course.id)}
                              disabled={savingId === String(course.id)}
                              className="h-8 px-3"
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
                        <TableCell colSpan={4} className="py-8 text-center text-sm text-slate-500">
                          Este colegio todavía no tiene cursos.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <Card className="min-w-0">
            <CardHeader className="pb-4">
              <CardTitle>Nuevo curso</CardTitle>
              <CardDescription>
                {isPlatformMode
                  ? "Agregá un curso al colegio seleccionado."
                  : "Agregá un curso al colegio activo."}
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              <form className="grid gap-3 md:grid-cols-[minmax(0,1fr)_100px] md:items-end" onSubmit={createCourse}>
                <div className="space-y-2">
                  <Label htmlFor="new-course-name">Nombre</Label>
                  <Input
                    id="new-course-name"
                    value={newCourse.name}
                    onChange={(event) => setNewCourse((current) => ({ ...current, name: event.target.value }))}
                    className="h-9"
                    required
                  />
                </div>
                <Button type="submit" disabled={creating || !selectedSchool} className="h-9">
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
