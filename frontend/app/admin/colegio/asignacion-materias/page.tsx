// @ts-nocheck
"use client"

import Link from "next/link"
import { useDeferredValue, useEffect, useRef, useMemo, useState, startTransition } from "react"
import { ArrowLeft, BookOpen, RefreshCcw } from "lucide-react"

import { authFetch, useAuthGuard, useSessionContext } from "../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function normalizeName(user) {
  return user?.full_name || user?.username || "Profesor"
}

function courseLabel(course) {
  const code = String(course?.code || "").trim()
  const name = String(course?.name || "").trim()
  if (code && name && code !== name) return `${code} - ${name}`
  return name || code || "Curso"
}

export default function AdminAsignacionMateriasPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loadingSession = !sessionContext
  const groups = Array.isArray(sessionContext?.groups) ? sessionContext.groups : []
  const allowed =
    !!sessionContext?.isSuperuser ||
    groups.some((group) => {
      const value = String(group || "").toLowerCase()
      return value === "administradores" || value === "administrador"
    })
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
  const [comboOpen, setComboOpen] = useState(false)
  const comboRef = useRef(null)
  const [loading, setLoading] = useState(true)
  const [refreshTick, setRefreshTick] = useState(0)
  const [error, setError] = useState("")
  const [payload, setPayload] = useState({ school: null, courses: [], materias: [], profesores: [] })

  const [selectedProfesorId, setSelectedProfesorId] = useState("")
  const [selectedCourseId, setSelectedCourseId] = useState("")

  // drafts: { [profesorId_courseId]: { materias: string[], saving, error, success } }
  const [drafts, setDrafts] = useState({})

  useEffect(() => {
    if (!allowed) return
    let cancelled = false
    setLoading(true)
    setError("")

    ;(async () => {
      try {
        const res = await authFetch("/admin/staff/materias/", {
          headers: activeSchoolRef ? { "X-School": String(activeSchoolRef) } : undefined,
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          if (!cancelled) {
            setError(data?.detail || "No se pudo cargar los profesores.")
            setLoading(false)
          }
          return
        }
        if (cancelled) return
        startTransition(() => {
          setPayload({
            school: data?.school || null,
            courses: Array.isArray(data?.courses) ? data.courses : [],
            materias: Array.isArray(data?.materias) ? data.materias : [],
            profesores: Array.isArray(data?.profesores) ? data.profesores : [],
          })
          setDrafts({})
          setLoading(false)
        })
      } catch {
        if (!cancelled) {
          setError("No se pudo conectar con el servidor.")
          setLoading(false)
        }
      }
    })()

    return () => { cancelled = true }
  }, [activeSchoolRef, allowed, refreshTick])

  useEffect(() => {
    function handleClickOutside(e) {
      if (comboRef.current && !comboRef.current.contains(e.target)) {
        setComboOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const { courses, materias, profesores } = payload

  const filteredProfesores = useMemo(() => {
    const q = deferredQuery.toLowerCase()
    return [...profesores]
      .filter((p) => {
        if (!q) return true
        return [p.username, p.full_name, p.email].some((v) =>
          String(v || "").toLowerCase().includes(q)
        )
      })
      .sort((a, b) => normalizeName(a).localeCompare(normalizeName(b)))
  }, [deferredQuery, profesores])

  const selectedProfesor = useMemo(
    () => profesores.find((p) => String(p.id) === String(selectedProfesorId)) || null,
    [profesores, selectedProfesorId]
  )

  function selectProfesor(p) {
    setSelectedProfesorId(String(p.id))
    setQuery(normalizeName(p))
    setComboOpen(false)
    setSelectedCourseId("")
  }

  const assignedCourses = useMemo(() => {
    if (!selectedProfesor) return []
    const assigned = new Set(selectedProfesor.assigned_course_ids || [])
    return courses.filter((c) => assigned.has(c.id))
  }, [selectedProfesor, courses])

  const selectedCourse = useMemo(
    () => courses.find((c) => String(c.id) === String(selectedCourseId)) || null,
    [courses, selectedCourseId]
  )

  const draftKey = selectedProfesorId && selectedCourseId
    ? `${selectedProfesorId}_${selectedCourseId}`
    : null

  useEffect(() => {
    if (!selectedProfesor || !selectedCourse) return
    const key = `${selectedProfesor.id}_${selectedCourse.id}`
    setDrafts((current) => {
      if (current[key]) return current
      const existing = (selectedProfesor.course_materias || {})[String(selectedCourse.id)] || []
      return {
        ...current,
        [key]: { materias: existing.slice(), saving: false, error: "", success: "" },
      }
    })
  }, [selectedProfesor, selectedCourse])

  const currentDraft = draftKey ? drafts[draftKey] : null

  const toggleMateria = (materia) => {
    if (!draftKey) return
    setDrafts((current) => {
      const existing = current[draftKey] || { materias: [], saving: false, error: "", success: "" }
      const set = new Set(existing.materias)
      if (set.has(materia)) set.delete(materia)
      else set.add(materia)
      return {
        ...current,
        [draftKey]: { ...existing, materias: Array.from(set), error: "", success: "" },
      }
    })
  }

  const handleSave = async () => {
    if (!selectedProfesor || !selectedCourse || !currentDraft) return
    const key = draftKey
    setDrafts((current) => ({
      ...current,
      [key]: { ...(current[key] || currentDraft), saving: true, error: "", success: "" },
    }))

    try {
      const res = await authFetch(
        `/admin/staff/${selectedProfesor.id}/materias/${selectedCourse.id}/`,
        {
          method: "PATCH",
          headers: activeSchoolRef ? { "X-School": String(activeSchoolRef) } : undefined,
          body: JSON.stringify({ materias: currentDraft.materias }),
        }
      )
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setDrafts((current) => ({
          ...current,
          [key]: {
            ...(current[key] || currentDraft),
            saving: false,
            error: data?.detail || "No se pudo guardar la asignación.",
            success: "",
          },
        }))
        return
      }

      const savedMaterias = Array.isArray(data?.materias) ? data.materias : currentDraft.materias
      startTransition(() => {
        setPayload((current) => ({
          ...current,
          profesores: current.profesores.map((p) =>
            p.id === selectedProfesor.id
              ? {
                  ...p,
                  course_materias: {
                    ...(p.course_materias || {}),
                    [String(selectedCourse.id)]: savedMaterias,
                  },
                }
              : p
          ),
        }))
        setDrafts((current) => ({
          ...current,
          [key]: {
            materias: savedMaterias.slice(),
            saving: false,
            error: "",
            success: "Materias actualizadas correctamente",
          },
        }))
      })
    } catch {
      setDrafts((current) => ({
        ...current,
        [key]: {
          ...(current[key] || currentDraft),
          saving: false,
          error: "No se pudo conectar con el servidor.",
          success: "",
        },
      }))
    }
  }

  if (loadingSession) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de materias...</div>
      </div>
    )
  }

  if (!allowed) {
    return (
      <Card className="border-amber-200 bg-amber-50">
        <CardHeader>
          <CardTitle className="text-amber-950">Acceso restringido</CardTitle>
          <CardDescription className="text-amber-800">
            Solo los administradores del colegio pueden modificar asignaciones de materias.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            href="/admin/colegio"
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver a admin colegio
          </Link>
          <h2 className="mt-3 text-3xl font-semibold text-slate-900">Materias por profesor</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Restringí qué materias puede calificar cada profesor en cada curso. Sin restricciones asignadas, el profesor puede calificar todas.
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
          <div className="font-semibold text-slate-900">
            {payload.school?.short_name || payload.school?.name || sessionContext?.school?.short_name || "Colegio activo"}
          </div>
          <div>Colegio activo</div>
        </div>
      </div>

      <Card className="min-w-0">
        <CardContent className="flex flex-col gap-3 py-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="grid min-w-0 flex-1 gap-3 md:grid-cols-[minmax(260px,1fr)_minmax(220px,1fr)]">
            <div className="space-y-2">
              <Label htmlFor="profesor-combo">Profesor</Label>
              <div className="relative" ref={comboRef}>
                <Input
                  id="profesor-combo"
                  autoComplete="off"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value)
                    setSelectedProfesorId("")
                    setSelectedCourseId("")
                    setComboOpen(true)
                  }}
                  onFocus={() => setComboOpen(true)}
                  placeholder="Escribí para buscar un profesor..."
                />
                {comboOpen && filteredProfesores.length > 0 && (
                  <ul className="absolute z-20 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-lg max-h-56 overflow-y-auto text-sm">
                    {filteredProfesores.map((p) => (
                      <li
                        key={p.id}
                        className="flex flex-col px-3 py-2 cursor-pointer hover:bg-slate-100"
                        onMouseDown={(e) => { e.preventDefault(); selectProfesor(p) }}
                      >
                        <span className="font-medium text-slate-900">{normalizeName(p)}</span>
                        {p.email ? <span className="text-xs text-slate-500">{p.email}</span> : null}
                      </li>
                    ))}
                  </ul>
                )}
                {comboOpen && query.trim() && filteredProfesores.length === 0 && (
                  <div className="absolute z-20 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-lg px-3 py-2 text-sm text-slate-500">
                    No se encontraron profesores
                  </div>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="course-selector">Curso</Label>
              <select
                id="course-selector"
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                value={selectedCourseId}
                onChange={(e) => setSelectedCourseId(e.target.value)}
                disabled={!selectedProfesor || assignedCourses.length === 0}
              >
                <option value="">— Seleccioná un curso —</option>
                {assignedCourses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {courseLabel(c)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <Button type="button" variant="outline" onClick={() => setRefreshTick((v) => v + 1)}>
            <RefreshCcw className="mr-2 h-4 w-4" />
            Recargar
          </Button>
        </CardContent>
      </Card>

      {error ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="rounded-3xl border border-slate-200 bg-white px-6 py-10 text-sm text-slate-600">
          Cargando profesores del colegio...
        </div>
      ) : null}

      {!loading && !selectedProfesor ? (
        <div className="rounded-3xl border border-slate-200 bg-white px-6 py-10 text-sm text-slate-600">
          {profesores.length === 0
            ? "No hay profesores asignados a cursos en este colegio."
            : "Seleccioná un profesor para ver y editar sus materias por curso."}
        </div>
      ) : null}

      {!loading && selectedProfesor && !selectedCourse ? (
        <div className="rounded-3xl border border-slate-200 bg-white px-6 py-10 text-sm text-slate-600">
          {assignedCourses.length === 0
            ? `${normalizeName(selectedProfesor)} no tiene cursos asignados.`
            : "Seleccioná un curso para gestionar las materias."}
        </div>
      ) : null}

      {!loading && selectedProfesor && selectedCourse ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="h-5 w-5" />
                {normalizeName(selectedProfesor)} — {courseLabel(selectedCourse)}
              </CardTitle>
              <CardDescription>
                Marcá las materias que puede calificar en este curso. Sin selección = acceso a todas.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {currentDraft?.error ? (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {currentDraft.error}
                </div>
              ) : null}
              {currentDraft?.success ? (
                <div role="status" aria-live="polite" className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  {currentDraft.success}
                </div>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-slate-900">
                    {currentDraft?.materias?.length
                      ? `${currentDraft.materias.length} materia${currentDraft.materias.length === 1 ? "" : "s"} restringida${currentDraft.materias.length === 1 ? "" : "s"}`
                      : "Sin restricciones (todas las materias)"}
                  </div>
                  <div className="text-sm text-slate-600">Los cambios se aplican cuando presionás Guardar.</div>
                </div>
                <Button type="button" onClick={handleSave} disabled={currentDraft?.saving}>
                  {currentDraft?.saving ? "Guardando..." : "Guardar materias"}
                </Button>
              </div>

              <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3">
                {materias.map((materia) => {
                  const checked = currentDraft?.materias?.includes(materia) ?? false
                  return (
                    <label
                      key={materia}
                      className={`flex items-center gap-3 rounded-2xl border px-3 py-3 text-sm transition cursor-pointer ${
                        checked
                          ? "border-slate-900 bg-slate-50 text-slate-900"
                          : "border-slate-200 bg-white text-slate-700"
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="h-4 w-4"
                        checked={checked}
                        onChange={() => toggleMateria(materia)}
                      />
                      <span className="font-medium">{materia}</span>
                    </label>
                  )
                })}
              </div>
            </CardContent>
          </Card>

          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Resumen del profesor</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
                <div>
                  <span className="font-semibold text-slate-900">{normalizeName(selectedProfesor)}</span>
                  {selectedProfesor.email ? (
                    <div className="text-xs text-slate-500">{selectedProfesor.email}</div>
                  ) : null}
                </div>
                <div>
                  <div className="font-medium text-slate-700 mb-1">Cursos asignados</div>
                  {assignedCourses.map((c) => {
                    const cm = (selectedProfesor.course_materias || {})[String(c.id)] || []
                    return (
                      <div key={c.id} className="flex items-start justify-between gap-2 py-1 border-b last:border-b-0">
                        <span>{courseLabel(c)}</span>
                        <span className="text-xs text-slate-500 text-right">
                          {cm.length ? `${cm.length} mat.` : "Todas"}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Cómo funciona</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
                <p>Si no marcás ninguna materia, el profesor puede calificar en todas las materias del curso.</p>
                <p>Si marcás una o más materias, el profesor queda restringido a solo esas materias en este curso.</p>
                <p>La restricción aplica por curso — podés configurarla de forma independiente para cada uno.</p>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  )
}
