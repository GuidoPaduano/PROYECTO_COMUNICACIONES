"use client"

import Link from "next/link"
import { useEffect, useMemo, useState, startTransition } from "react"
import { ArrowLeft, CheckCircle2, RefreshCcw, UserPlus, Users } from "lucide-react"

import { authFetch, useAuthGuard, useSessionContext } from "../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function courseLabel(course) {
  const code = String(course?.code || "").trim()
  const name = String(course?.name || "").trim()
  if (code && name && code !== name) return `${code} - ${name}`
  return name || code || "Curso"
}

function studentLabel(student) {
  const apellido = String(student?.apellido || "").trim()
  const nombre = String(student?.nombre || "").trim()
  const legajo = String(student?.id_alumno || "").trim()
  const course = String(student?.school_course_label || "").trim()
  const fullName = [apellido, nombre].filter(Boolean).join(", ") || student?.full_name || "Alumno"
  return [fullName, legajo ? `Legajo ${legajo}` : "", course].filter(Boolean).join(" - ")
}

const INITIAL_FORM = {
  first_name: "",
  last_name: "",
  username: "",
  email: "",
  password: "",
  password_confirm: "",
  role: "Alumnos",
  school_course_ids: [],
  alumno_id: "",
  alumno_ids: [],
}

export default function AdminCreateUserPage({
  backHref = "/admin/colegio",
  backLabel = "Volver a admin colegio",
}) {
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

  const [loading, setLoading] = useState(true)
  const [refreshTick, setRefreshTick] = useState(0)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [payload, setPayload] = useState({ school: null, courses: [], students: [], role_options: [] })
  const [form, setForm] = useState(INITIAL_FORM)
  const [studentQuery, setStudentQuery] = useState("")
  const [studentCourseFilter, setStudentCourseFilter] = useState("")

  useEffect(() => {
    if (!allowed) return

    let cancelled = false
    setLoading(true)
    setError("")

    ;(async () => {
      try {
        const res = await authFetch("/admin/users/create/", {
          headers: activeSchoolRef ? { "X-School": String(activeSchoolRef) } : undefined,
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          if (!cancelled) {
            setError(data?.detail || "No se pudo cargar la herramienta de alta.")
            setLoading(false)
          }
          return
        }
        if (cancelled) return
        startTransition(() => {
          setPayload({
            school: data?.school || null,
            courses: Array.isArray(data?.courses) ? data.courses : [],
            students: Array.isArray(data?.students) ? data.students : [],
            role_options: Array.isArray(data?.role_options) ? data.role_options : [],
          })
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
  }, [activeSchoolRef, allowed, refreshTick])

  const roleOptions = Array.isArray(payload.role_options) ? payload.role_options : []
  const courses = Array.isArray(payload.courses) ? payload.courses : []
  const students = Array.isArray(payload.students) ? payload.students : []

  const filteredStudents = useMemo(() => {
    const query = studentQuery.trim().toLowerCase()
    return students.filter((student) => {
      if (studentCourseFilter && String(student.school_course_id) !== String(studentCourseFilter)) return false
      if (!query) return true
      return [student.nombre, student.apellido, student.id_alumno, student.school_course_label]
        .some((value) => String(value || "").toLowerCase().includes(query))
    })
  }, [studentCourseFilter, studentQuery, students])

  const selectedStudent = useMemo(
    () => students.find((student) => String(student.id) === String(form.alumno_id)) || null,
    [form.alumno_id, students]
  )

  const selectedParentIds = useMemo(() => new Set(form.alumno_ids.map((value) => Number(value))), [form.alumno_ids])

  useEffect(() => {
    if (form.role !== "Alumnos" || !selectedStudent) return
    setForm((current) => {
      const next = { ...current }
      if (!next.first_name) next.first_name = String(selectedStudent.nombre || "").trim()
      if (!next.last_name) next.last_name = String(selectedStudent.apellido || "").trim()
      if (!next.username) next.username = String(selectedStudent.id_alumno || "").trim()
      return next
    })
  }, [form.role, selectedStudent])

  const setField = (name, value) => {
    setForm((current) => ({ ...current, [name]: value }))
    setError("")
    setSuccess("")
  }

  const toggleCourse = (courseId) => {
    setForm((current) => {
      const values = new Set(current.school_course_ids || [])
      if (values.has(courseId)) values.delete(courseId)
      else values.add(courseId)
      return { ...current, school_course_ids: Array.from(values).sort((a, b) => a - b) }
    })
    setError("")
    setSuccess("")
  }

  const toggleParentStudent = (studentId) => {
    setForm((current) => {
      const values = new Set(current.alumno_ids || [])
      if (values.has(studentId)) values.delete(studentId)
      else values.add(studentId)
      return { ...current, alumno_ids: Array.from(values).sort((a, b) => a - b) }
    })
    setError("")
    setSuccess("")
  }

  const handleRoleChange = (role) => {
    setForm((current) => ({
      ...current,
      role,
      school_course_ids: [],
      alumno_id: "",
      alumno_ids: [],
    }))
    setError("")
    setSuccess("")
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError("")
    setSuccess("")

    try {
      const res = await authFetch("/admin/users/create/", {
        method: "POST",
        headers: activeSchoolRef ? { "X-School": String(activeSchoolRef) } : undefined,
        body: JSON.stringify(form),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo crear el usuario.")
        setSubmitting(false)
        return
      }

      startTransition(() => {
        setSuccess(data?.detail || "Usuario creado correctamente.")
        setSubmitting(false)
        setRefreshTick((current) => current + 1)
        setForm((current) => ({
          ...INITIAL_FORM,
          role: current.role,
        }))
        setStudentQuery("")
        setStudentCourseFilter("")
      })
    } catch {
      setError("No se pudo conectar con el servidor.")
      setSubmitting(false)
    }
  }

  if (loadingSession || !allowed) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando alta de usuarios...</div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="mt-3 text-3xl font-semibold text-slate-900">Nuevo usuario</h1>
        </div>
        <Link
          href={backHref}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          {backLabel}
        </Link>
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

      {loading ? (
        <div className="rounded-3xl border border-slate-200 bg-white px-6 py-10 text-sm text-slate-600">
          Cargando configuracion del colegio...
        </div>
      ) : (
        <form className="grid gap-6 lg:grid-cols-[minmax(0,1.45fr)_360px]" onSubmit={handleSubmit}>
          <div className="space-y-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle>Datos base</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 pt-2 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="last_name">Apellido</Label>
                  <Input id="last_name" value={form.last_name} onChange={(event) => setField("last_name", event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="first_name">Nombre</Label>
                  <Input id="first_name" value={form.first_name} onChange={(event) => setField("first_name", event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="username">Usuario</Label>
                  <Input id="username" value={form.username} onChange={(event) => setField("username", event.target.value)} placeholder="Ej: legajo o identificador interno" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" value={form.email} onChange={(event) => setField("email", event.target.value)} placeholder="Opcional" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Contraseña</Label>
                  <Input id="password" type="password" value={form.password} onChange={(event) => setField("password", event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password_confirm">Confirmar contraseña</Label>
                  <Input id="password_confirm" type="password" value={form.password_confirm} onChange={(event) => setField("password_confirm", event.target.value)} />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Tipo de usuario</CardTitle>
                <CardDescription>Elegi el rol operativo con el que la cuenta entra a la plataforma.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2">
                {roleOptions.map((role) => {
                  const checked = role.value === form.role
                  return (
                    <label
                      key={role.value}
                      className={`rounded-2xl border px-4 py-4 transition ${
                        checked ? "border-[var(--school-primary)] bg-slate-50 shadow-sm" : "border-slate-200 bg-white"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="radio"
                          className="school-radio mt-1 h-4 w-4"
                          checked={checked}
                          onChange={() => handleRoleChange(role.value)}
                        />
                        <span className="space-y-1">
                          <span className="block text-sm font-semibold text-slate-900">{role.label}</span>
                          <span className="block text-sm leading-6 text-slate-600">{role.description}</span>
                        </span>
                      </div>
                    </label>
                  )
                })}
              </CardContent>
            </Card>

            {form.role === "Alumnos" ? (
              <Card>
                <CardHeader>
                  <CardTitle>Vinculo con alumno</CardTitle>
                  <CardDescription>El usuario quedara asociado al alumno seleccionado para resolver su contexto automaticamente.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
                    <div className="space-y-2">
                      <Label htmlFor="student-search">Buscar alumno</Label>
                      <Input id="student-search" value={studentQuery} onChange={(event) => setStudentQuery(event.target.value)} placeholder="Nombre, apellido o legajo" />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="student-course-filter">Curso</Label>
                      <select
                        id="student-course-filter"
                        className="select-trigger-school h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900"
                        value={studentCourseFilter}
                        onChange={(event) => setStudentCourseFilter(event.target.value)}
                      >
                        <option value="">Todos los cursos</option>
                        {courses.map((course) => (
                          <option key={course.id} value={course.id}>
                            {courseLabel(course)}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
                    {filteredStudents.map((student) => (
                      <label
                        key={student.id}
                        className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${
                          String(form.alumno_id) === String(student.id)
                            ? "border-[var(--school-primary)] bg-slate-50"
                            : "border-slate-200 bg-white"
                        } ${student.has_user ? "opacity-60" : ""}`}
                      >
                        <input
                          type="radio"
                          className="school-radio mt-1 h-4 w-4"
                          checked={String(form.alumno_id) === String(student.id)}
                          onChange={() => setField("alumno_id", String(student.id))}
                          disabled={student.has_user}
                        />
                        <span>
                          <span className="block font-medium text-slate-900">{studentLabel(student)}</span>
                          <span className="block text-xs text-slate-500">
                            {student.has_user ? "Ya tiene usuario vinculado" : "Disponible para vincular"}
                          </span>
                        </span>
                      </label>
                    ))}
                    {!filteredStudents.length ? (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                        No hay alumnos que coincidan con el filtro actual.
                      </div>
                    ) : null}
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {form.role === "Padres" ? (
              <Card>
                <CardHeader>
                  <CardTitle>Alumnos a cargo</CardTitle>
                  <CardDescription>Selecciona los alumnos que deberian quedar asociados a esta familia.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
                    <div className="space-y-2">
                      <Label htmlFor="parent-student-search">Buscar alumno</Label>
                      <Input id="parent-student-search" value={studentQuery} onChange={(event) => setStudentQuery(event.target.value)} placeholder="Nombre, apellido o legajo" />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="parent-course-filter">Curso</Label>
                      <select
                        id="parent-course-filter"
                        className="select-trigger-school h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900"
                        value={studentCourseFilter}
                        onChange={(event) => setStudentCourseFilter(event.target.value)}
                      >
                        <option value="">Todos los cursos</option>
                        {courses.map((course) => (
                          <option key={course.id} value={course.id}>
                            {courseLabel(course)}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="max-h-80 grid gap-2 overflow-y-auto pr-1">
                    {filteredStudents.map((student) => (
                      <label
                        key={student.id}
                        className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${
                          selectedParentIds.has(Number(student.id))
                            ? "border-[var(--school-primary)] bg-slate-50"
                            : "border-slate-200 bg-white"
                        } ${student.has_parent ? "opacity-60" : ""}`}
                      >
                        <input
                          type="checkbox"
                          className="school-radio mt-1 h-4 w-4"
                          checked={selectedParentIds.has(Number(student.id))}
                          onChange={() => toggleParentStudent(student.id)}
                          disabled={student.has_parent}
                        />
                        <span>
                          <span className="block font-medium text-slate-900">{studentLabel(student)}</span>
                          <span className="block text-xs text-slate-500">
                            {student.has_parent ? "Ya tiene tutor vinculado" : "Disponible para asociar"}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : null}

            {(form.role === "Profesores" || form.role === "Preceptores") ? (
              <Card>
                <CardHeader>
                  <CardTitle>Asignacion inicial a cursos</CardTitle>
                  <CardDescription>Opcional. Si los seleccionas ahora, el usuario ya queda operativo dentro del colegio.</CardDescription>
                </CardHeader>
                <CardContent className="grid gap-2 sm:grid-cols-2">
                  {courses.map((course) => {
                    const checked = form.school_course_ids.includes(course.id)
                    return (
                      <label
                        key={course.id}
                        className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${
                          checked ? "border-[var(--school-primary)] bg-slate-50" : "border-slate-200 bg-white"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="school-radio mt-1 h-4 w-4"
                          checked={checked}
                          onChange={() => toggleCourse(course.id)}
                        />
                        <span className="font-medium text-slate-900">{courseLabel(course)}</span>
                      </label>
                    )
                  })}
                </CardContent>
              </Card>
            ) : null}
          </div>

          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Acciones
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting ? "Creando usuario..." : "Crear usuario"}
                </Button>
                <Button type="button" variant="outline" className="w-full" onClick={() => setRefreshTick((current) => current + 1)}>
                  <RefreshCcw className="mr-2 h-4 w-4" />
                  Recargar datos
                </Button>
                {success ? (
                  <div className="flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>La base ya fue actualizada con este alta.</span>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        </form>
      )}
    </div>
  )
}
