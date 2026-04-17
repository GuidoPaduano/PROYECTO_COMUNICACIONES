"use client"

import Link from "next/link"
import { useDeferredValue, useEffect, useMemo, useState, startTransition } from "react"
import { ArrowLeft, BookCopy, BriefcaseBusiness, RefreshCcw, Search, ShieldCheck } from "lucide-react"

import { authFetch, useAuthGuard, useSessionContext } from "../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function normalizeName(user) {
  return user?.full_name || user?.username || "Usuario"
}

function courseLabel(course) {
  const code = String(course?.code || "").trim()
  const name = String(course?.name || "").trim()
  if (code && name && code !== name) return `${code} - ${name}`
  return name || code || "Curso"
}

function roleLabel(role) {
  return role === "Preceptores" ? "preceptores" : "profesores"
}

function singularRoleLabel(role) {
  return role === "Preceptores" ? "preceptor" : "profesor"
}

export default function StaffCourseAssignmentPage({ role, title, description }) {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loadingSession = !sessionContext
  const allowed = !!sessionContext?.isSuperuser
  const activeSchoolName = sessionContext?.school?.short_name || sessionContext?.school?.name || "Colegio activo"
  const activeSchoolRef = useMemo(
    () =>
      sessionContext?.school?.slug ||
      sessionContext?.school?.id ||
      sessionContext?.availableSchools?.[0]?.slug ||
      sessionContext?.availableSchools?.[0]?.id ||
      "",
    [sessionContext]
  )

  const [query, setQuery] = useState("")
  const deferredQuery = useDeferredValue(query.trim())
  const [loading, setLoading] = useState(true)
  const [refreshTick, setRefreshTick] = useState(0)
  const [error, setError] = useState("")
  const [payload, setPayload] = useState({ school: null, courses: [], users: [] })
  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [courseDrafts, setCourseDrafts] = useState({})

  useEffect(() => {
    if (!allowed) return

    let cancelled = false
    setLoading(true)
    setError("")

    ;(async () => {
      try {
        const suffix = deferredQuery ? `?q=${encodeURIComponent(deferredQuery)}` : ""
        const res = await authFetch(`/admin/staff/${suffix}`, {
          headers: activeSchoolRef ? { "X-School": String(activeSchoolRef) } : undefined,
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          if (!cancelled) {
            setError(data?.detail || "No se pudo cargar el personal del colegio.")
            setLoading(false)
          }
          return
        }

        if (cancelled) return
        startTransition(() => {
          const nextPayload = {
            school: data?.school || null,
            courses: Array.isArray(data?.courses) ? data.courses : [],
            users: Array.isArray(data?.users) ? data.users : [],
          }
          setPayload(nextPayload)
          setSelectedCourseId((current) => {
            if (current && nextPayload.courses.some((course) => String(course.id) === String(current))) return current
            return nextPayload.courses[0] ? String(nextPayload.courses[0].id) : ""
          })
          setCourseDrafts({})
          setLoading(false)
        })
      } catch {
        if (!cancelled) {
          setError("No se pudo conectar con el servidor.")
          setLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [activeSchoolRef, allowed, deferredQuery, refreshTick])

  const users = Array.isArray(payload.users) ? payload.users : []
  const courses = Array.isArray(payload.courses) ? payload.courses : []
  const selectedCourse = useMemo(
    () => courses.find((course) => String(course.id) === String(selectedCourseId)) || null,
    [courses, selectedCourseId]
  )

  const assignedByCourse = useMemo(() => {
    const map = {}
    for (const course of courses) map[course.id] = []
    for (const user of users) {
      if (user.staff_role !== role) continue
      for (const course of user.assigned_school_courses || []) {
        if (!map[course.id]) continue
        map[course.id].push(user)
      }
    }
    return map
  }, [courses, role, users])

  useEffect(() => {
    if (!selectedCourse) return
    setCourseDrafts((current) => {
      if (current[selectedCourse.id]) return current
      const initial = assignedByCourse[selectedCourse.id] || []
      return {
        ...current,
        [selectedCourse.id]: {
          userIds: initial.map((user) => user.id),
          saving: false,
          error: "",
          success: "",
        },
      }
    })
  }, [assignedByCourse, selectedCourse])

  const currentCourseDraft = selectedCourse ? courseDrafts[selectedCourse.id] : null

  const eligibleUsers = useMemo(() => {
    const q = deferredQuery.toLowerCase()
    return [...users]
      .filter((user) => !user.staff_role || user.staff_role === role)
      .filter((user) => {
        if (!q) return true
        return [user.username, user.full_name, user.email].some((value) =>
          String(value || "").toLowerCase().includes(q)
        )
      })
      .sort((a, b) => normalizeName(a).localeCompare(normalizeName(b)))
  }, [deferredQuery, role, users])

  const selectedIds = useMemo(
    () => new Set(currentCourseDraft?.userIds || []),
    [currentCourseDraft?.userIds]
  )

  const selectedUsers = useMemo(
    () => eligibleUsers.filter((user) => selectedIds.has(user.id)),
    [eligibleUsers, selectedIds]
  )

  const handleCourseAssignmentToggle = (userId) => {
    if (!selectedCourse) return
    setCourseDrafts((current) => {
      const existing = current[selectedCourse.id] || {
        userIds: [],
        saving: false,
        error: "",
        success: "",
      }
      const values = new Set(existing.userIds || [])
      if (values.has(userId)) values.delete(userId)
      else values.add(userId)
      return {
        ...current,
        [selectedCourse.id]: {
          ...existing,
          userIds: Array.from(values).sort((a, b) => a - b),
          error: "",
          success: "",
        },
      }
    })
  }

  const handleSaveCourse = async () => {
    if (!selectedCourse || !currentCourseDraft) return
    const userIds = currentCourseDraft.userIds || []
    setCourseDrafts((current) => ({
      ...current,
      [selectedCourse.id]: {
        ...(current[selectedCourse.id] || currentCourseDraft),
        saving: true,
        error: "",
        success: "",
      },
    }))

    try {
      const res = await authFetch(`/admin/staff/course/${selectedCourse.id}/`, {
        method: "PATCH",
        headers: activeSchoolRef ? { "X-School": String(activeSchoolRef) } : undefined,
        body: JSON.stringify({
          staff_role: role,
          user_ids: userIds,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setCourseDrafts((current) => ({
          ...current,
          [selectedCourse.id]: {
            ...(current[selectedCourse.id] || currentCourseDraft),
            saving: false,
            error: data?.detail || "No se pudo guardar la asignación del curso.",
            success: "",
          },
        }))
        return
      }

      const nextUsers = Array.isArray(data?.users) ? data.users : users
      startTransition(() => {
        setPayload((current) => ({ ...current, users: nextUsers }))
        setCourseDrafts((current) => ({
          ...current,
          [selectedCourse.id]: {
            userIds: userIds.slice(),
            saving: false,
            error: "",
            success: `Asignación de ${roleLabel(role)} actualizada`,
          },
        }))
      })
    } catch {
      setCourseDrafts((current) => ({
        ...current,
        [selectedCourse.id]: {
          ...(current[selectedCourse.id] || currentCourseDraft),
          saving: false,
          error: "No se pudo conectar con el servidor.",
          success: "",
        },
      }))
    }
  }

  if (loadingSession || !allowed) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de asignaciones...</div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            href="/admin"
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver al panel admin
          </Link>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
          <div className="font-semibold text-slate-900">{payload.school?.short_name || payload.school?.name || activeSchoolName}</div>
          <div>Colegio activo</div>
        </div>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 py-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="grid flex-1 gap-3 sm:grid-cols-[minmax(240px,340px)_minmax(240px,1fr)]">
            <div className="space-y-2">
              <Label htmlFor="course-selector">Curso</Label>
              <select
                id="course-selector"
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                value={selectedCourseId}
                onChange={(event) => setSelectedCourseId(event.target.value)}
              >
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {courseLabel(course)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="staff-search">Buscar {singularRoleLabel(role)}</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
                <Input
                  id="staff-search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Nombre, usuario o email"
                  className="pl-9"
                />
              </div>
            </div>
          </div>
          <Button type="button" variant="outline" onClick={() => setRefreshTick((value) => value + 1)}>
            <RefreshCcw className="mr-2 h-4 w-4" />
            Recargar
          </Button>
        </CardContent>
      </Card>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="rounded-3xl border border-slate-200 bg-white px-6 py-10 text-sm text-slate-600">
          Cargando {roleLabel(role)} del colegio...
        </div>
      ) : null}

      {!loading ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookCopy className="h-5 w-5" />
                {selectedCourse ? courseLabel(selectedCourse) : "Curso"}
              </CardTitle>
              <CardDescription>
                Selecciona los {roleLabel(role)} que deben quedar asignados a este curso.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {!selectedCourse ? (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                  No hay cursos disponibles para este colegio.
                </div>
              ) : (
                <>
                  {currentCourseDraft?.error ? (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                      {currentCourseDraft.error}
                    </div>
                  ) : null}
                  {currentCourseDraft?.success ? (
                    <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                      {currentCourseDraft.success}
                    </div>
                  ) : null}

                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-lg font-semibold text-slate-900">
                        {selectedUsers.length} {roleLabel(role)} asignados
                      </div>
                      <div className="text-sm text-slate-600">
                        Los cambios se aplican cuando presionas Guardar.
                      </div>
                    </div>
                    <Button type="button" onClick={handleSaveCourse} disabled={currentCourseDraft?.saving}>
                      {currentCourseDraft?.saving ? "Guardando..." : "Guardar asignación"}
                    </Button>
                  </div>

                  {!eligibleUsers.length ? (
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                      No hay usuarios disponibles con este filtro.
                    </div>
                  ) : null}

                  <div className="grid gap-2 sm:grid-cols-2">
                    {eligibleUsers.map((user) => {
                      const checked = selectedIds.has(user.id)
                      return (
                        <label
                          key={`${role}-${user.id}`}
                          className={`flex items-start gap-3 rounded-2xl border px-3 py-3 text-sm transition ${
                            checked
                              ? "border-slate-900 bg-slate-50 text-slate-900"
                              : "border-slate-200 bg-white text-slate-700"
                          }`}
                        >
                          <input
                            type="checkbox"
                            className="mt-1 h-4 w-4"
                            checked={checked}
                            onChange={() => handleCourseAssignmentToggle(user.id)}
                          />
                          <span>
                            <span className="block font-medium">{normalizeName(user)}</span>
                            <span className="block text-xs text-slate-500">
                              @{user.username}
                              {user.email ? ` - ${user.email}` : ""}
                            </span>
                          </span>
                        </label>
                      )
                    })}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BriefcaseBusiness className="h-5 w-5" />
                  Alcance
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
                <p>La asignación trabaja sobre el curso seleccionado y el colegio activo.</p>
                <p>Agregar un usuario desde esta pantalla también lo posiciona en el rol correspondiente.</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5" />
                  Importante
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
                <p>Si asignas una persona a este rol, se limpian sus asignaciones incompatibles en el colegio activo.</p>
                <p>Usa la búsqueda para encontrar usuarios que todavía no aparecen en el listado inicial.</p>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  )
}
