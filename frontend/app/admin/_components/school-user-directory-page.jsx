"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, GraduationCap, RefreshCw, Search, ShieldCheck, Users } from "lucide-react"

import { authFetch, useAuthGuard, useSessionContext } from "../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

const DIRECTORY_SECTIONS = {
  profesores: "profesores",
  preceptores: "preceptores",
  alumnos: "alumnos",
}

function buildCourseLabel(course) {
  const code = String(course?.code || "").trim()
  const name = String(course?.name || "").trim()
  if (code && name && code.toLowerCase() === name.toLowerCase()) return code
  return [code, name].filter(Boolean).join(" - ") || "Curso"
}

function isSchoolAdminContext(sessionContext) {
  if (sessionContext?.isSuperuser) return true
  const groups = Array.isArray(sessionContext?.groups) ? sessionContext.groups : []
  return groups.some((group) => {
    const value = String(group || "").toLowerCase()
    return value === "administradores" || value === "administrador"
  })
}

function matchQuery(values, query) {
  const needle = String(query || "").trim().toLowerCase()
  if (!needle) return true
  return values.some((value) => String(value || "").toLowerCase().includes(needle))
}

function SummaryCard({ title, value, icon, active = false, onClick, interactive = false }) {
  const content = (
    <CardContent className="flex items-center justify-between p-4 sm:p-5">
      <div>
        <div className={`text-sm ${active ? "text-slate-900" : "text-slate-500"}`}>{title}</div>
        <div className="mt-1 text-2xl font-semibold text-slate-900 sm:text-2xl">{value}</div>
      </div>
      <div
        className="inline-flex h-10 w-10 items-center justify-center rounded-2xl text-white transition sm:h-11 sm:w-11"
        style={{ backgroundColor: active ? "#0f172a" : "var(--school-primary)" }}
      >
        {icon}
      </div>
    </CardContent>
  )

  return (
    <Card
      className={
        interactive
          ? `transition ${active ? "border-slate-900 shadow-md" : "border-slate-200 hover:-translate-y-0.5 hover:shadow-md"}`
          : ""
      }
    >
      {interactive ? (
        <button type="button" onClick={onClick} className="w-full cursor-pointer text-left">
          {content}
        </button>
      ) : (
        content
      )}
    </Card>
  )
}

function StaffSection({ title, rows, emptyLabel }) {
  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle>{title}</CardTitle>
        <CardDescription>{rows.length ? `${rows.length} usuario(s)` : emptyLabel}</CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-3 md:hidden">
          {rows.map((row) => (
            <div key={row.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900">{row.full_name || row.username}</p>
                  <p className="mt-1 text-xs text-slate-500">@{row.username}</p>
                </div>
              </div>
              <div className="mt-3 space-y-2 text-sm text-slate-700">
                <div>
                  <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Email</span>
                  <span className="break-all">{row.email || "-"}</span>
                </div>
                <div>
                  <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Cursos</span>
                  <span className="block">
                    {Array.isArray(row.assigned_school_courses) && row.assigned_school_courses.length
                      ? row.assigned_school_courses.map((course) => course.code || course.name).join(", ")
                      : "-"}
                  </span>
                </div>
              </div>
            </div>
          ))}
          {!rows.length ? (
            <div className="rounded-2xl border border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
              {emptyLabel}
            </div>
          ) : null}
        </div>

        <div className="hidden min-w-0 md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Usuario</TableHead>
                <TableHead>Nombre</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Cursos</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-medium text-slate-900">{row.username}</TableCell>
                  <TableCell>{row.full_name || "-"}</TableCell>
                  <TableCell>{row.email || "-"}</TableCell>
                  <TableCell className="text-sm text-slate-600">
                    {Array.isArray(row.assigned_school_courses) && row.assigned_school_courses.length
                      ? row.assigned_school_courses.map((course) => course.code || course.name).join(", ")
                      : "-"}
                  </TableCell>
                </TableRow>
              ))}
              {!rows.length ? (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-sm text-slate-500">
                    {emptyLabel}
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function StudentsSection({ course }) {
  if (!course) return null

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardDescription>{course.students.length} alumno(s)</CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-3 md:hidden">
          {course.students.map((student) => (
            <div key={student.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900">{student.full_name || "-"}</p>
                  <p className="mt-1 text-xs text-slate-500">Legajo {student.id_alumno}</p>
                </div>
              </div>
              <div className="mt-3 space-y-2 text-sm text-slate-700">
                <div>
                  <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Usuario vinculado</span>
                  {student.linked_user?.username ? (
                    <span>{student.linked_user.username}</span>
                  ) : (
                    <span className="text-amber-700">Sin usuario</span>
                  )}
                </div>
                <div>
                  <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Email</span>
                  <span className="break-all">{student.linked_user?.email || "-"}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="hidden min-w-0 md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Legajo</TableHead>
                <TableHead>Alumno</TableHead>
                <TableHead>Usuario vinculado</TableHead>
                <TableHead>Email</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {course.students.map((student) => (
                <TableRow key={student.id}>
                  <TableCell className="font-medium text-slate-900">{student.id_alumno}</TableCell>
                  <TableCell>{student.full_name || "-"}</TableCell>
                  <TableCell>
                    {student.linked_user?.username ? (
                      <span className="text-sm text-slate-700">{student.linked_user.username}</span>
                    ) : (
                      <span className="text-sm text-amber-700">Sin usuario</span>
                    )}
                  </TableCell>
                  <TableCell>{student.linked_user?.email || "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

export default function SchoolUserDirectoryPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loadingSession = !sessionContext
  const allowed = isSchoolAdminContext(sessionContext)
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")
  const [activeSection, setActiveSection] = useState(DIRECTORY_SECTIONS.alumnos)
  const [selectedCourseKey, setSelectedCourseKey] = useState("")

  const loadData = async () => {
    setLoading(true)
    setError("")
    try {
      const res = await authFetch("/admin/school-users/")
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudo cargar el directorio del colegio.")
        return
      }
      setPayload(data)
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!allowed) return
    loadData()
  }, [allowed])

  const profesores = useMemo(() => {
    const rows = Array.isArray(payload?.profesores) ? payload.profesores : []
    return rows.filter((row) => matchQuery([row.username, row.full_name, row.email], query))
  }, [payload, query])

  const preceptores = useMemo(() => {
    const rows = Array.isArray(payload?.preceptores) ? payload.preceptores : []
    return rows.filter((row) => matchQuery([row.username, row.full_name, row.email], query))
  }, [payload, query])

  const alumnosPorCurso = useMemo(() => {
    const rows = Array.isArray(payload?.alumnos_por_curso) ? payload.alumnos_por_curso : []
    return rows
      .map((item) => ({
        ...item,
        students: (Array.isArray(item?.students) ? item.students : []).filter((student) =>
          matchQuery(
            [
              student.id_alumno,
              student.full_name,
              student.linked_user?.username,
              student.linked_user?.email,
              item?.course?.code,
              item?.course?.name,
            ],
            query
          )
        ),
      }))
      .filter((item) => item.students.length > 0)
  }, [payload, query])

  useEffect(() => {
    if (!alumnosPorCurso.length) {
      setSelectedCourseKey("")
      return
    }

    const hasCurrent = alumnosPorCurso.some((item) => {
      const itemKey = String(item?.course?.id ?? `${item?.course?.code || ""}:${item?.course?.name || ""}`)
      return itemKey === selectedCourseKey
    })
    if (!hasCurrent) {
      setSelectedCourseKey(
        String(
          alumnosPorCurso[0]?.course?.id ??
          `${alumnosPorCurso[0]?.course?.code || ""}:${alumnosPorCurso[0]?.course?.name || ""}`
        )
      )
    }
  }, [alumnosPorCurso, selectedCourseKey])

  const selectedCourse = useMemo(() => {
    if (!selectedCourseKey) return alumnosPorCurso[0] || null
    return (
      alumnosPorCurso.find((item) => {
        const itemKey = String(item?.course?.id ?? `${item?.course?.code || ""}:${item?.course?.name || ""}`)
        return itemKey === selectedCourseKey
      }) || alumnosPorCurso[0] || null
    )
  }, [alumnosPorCurso, selectedCourseKey])

  if (loadingSession || !allowed) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando directorio del colegio...</div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 min-w-0">
      <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
        <div>
          <Link
            href="/admin/colegio"
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver a admin colegio
          </Link>
          <h1 className="mt-3 text-2xl font-semibold text-slate-900 sm:text-3xl">Usuarios del colegio</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Directorio del colegio activo con profesores, preceptores y alumnos agrupados por curso.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={loadData} disabled={loading} className="w-full sm:w-auto">
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="relative w-full max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="pl-9"
          placeholder="Buscar por usuario, nombre, email o legajo"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-4">
        <SummaryCard
          title="Profesores"
          value={payload?.totals?.profesores ?? 0}
          icon={<Users className="h-5 w-5" />}
          interactive
          active={activeSection === DIRECTORY_SECTIONS.profesores}
          onClick={() => setActiveSection(DIRECTORY_SECTIONS.profesores)}
        />
        <SummaryCard
          title="Preceptores"
          value={payload?.totals?.preceptores ?? 0}
          icon={<ShieldCheck className="h-5 w-5" />}
          interactive
          active={activeSection === DIRECTORY_SECTIONS.preceptores}
          onClick={() => setActiveSection(DIRECTORY_SECTIONS.preceptores)}
        />
        <SummaryCard
          title="Alumnos"
          value={payload?.totals?.alumnos ?? 0}
          icon={<GraduationCap className="h-5 w-5" />}
          interactive
          active={activeSection === DIRECTORY_SECTIONS.alumnos}
          onClick={() => setActiveSection(DIRECTORY_SECTIONS.alumnos)}
        />
        <SummaryCard title="Cursos con alumnos" value={payload?.totals?.cursos_con_alumnos ?? 0} icon={<Users className="h-5 w-5" />} />
      </div>

      {activeSection === DIRECTORY_SECTIONS.profesores ? (
        <StaffSection
          title="Profesores"
          rows={profesores}
          emptyLabel="No hay profesores asignados en el colegio activo."
        />
      ) : null}

      {activeSection === DIRECTORY_SECTIONS.preceptores ? (
        <StaffSection
          title="Preceptores"
          rows={preceptores}
          emptyLabel="No hay preceptores asignados en el colegio activo."
        />
      ) : null}

      {activeSection === DIRECTORY_SECTIONS.alumnos ? (
        <Card>
          <CardHeader className="gap-4 pb-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <CardTitle>Alumnos por curso</CardTitle>
                <CardDescription>
                  {payload?.school?.name || "Colegio activo"}
                </CardDescription>
              </div>
              {alumnosPorCurso.length ? (
                <div className="w-full max-w-md">
                  <Select value={selectedCourseKey} onValueChange={setSelectedCourseKey}>
                    <SelectTrigger className="h-11 text-sm sm:h-12 sm:text-base">
                      <SelectValue placeholder="Seleccionar curso" />
                    </SelectTrigger>
                    <SelectContent>
                      {alumnosPorCurso.map((item) => {
                        const itemKey = String(item?.course?.id ?? `${item?.course?.code || ""}:${item?.course?.name || ""}`)
                        const itemLabel = buildCourseLabel(item?.course)
                        return (
                          <SelectItem key={itemKey} value={itemKey}>
                            {itemLabel}
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            {alumnosPorCurso.length ? (
              <>
                <StudentsSection course={selectedCourse} />
              </>
            ) : (
              <div className="rounded-lg border border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                No hay alumnos para mostrar con el filtro actual.
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
