// @ts-nocheck
"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, Building2, RefreshCw, Save, Search, ShieldCheck } from "lucide-react"

import { DEFAULT_SCHOOL_PRIMARY_COLOR, authFetch, useAuthGuard, useSessionContext } from "../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

function userDisplayName(user) {
  const name = String(user?.full_name || "").trim()
  const username = String(user?.username || "").trim()
  return name || username || "Usuario"
}

function userMeta(user) {
  return [user?.username ? `@${user.username}` : "", user?.email || ""].filter(Boolean).join(" - ")
}

function mergeUsers(...groups) {
  const out = []
  const seen = new Set()
  for (const group of groups) {
    for (const user of Array.isArray(group) ? group : []) {
      if (user?.id == null || seen.has(user.id)) continue
      seen.add(user.id)
      out.push(user)
    }
  }
  return out
}

export default function AdminsPorColegioPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loadingSession = !sessionContext
  const allowed = !!sessionContext?.isSuperuser

  const [schools, setSchools] = useState([])
  const [users, setUsers] = useState([])
  const [selectedId, setSelectedId] = useState("")
  const [schoolQuery, setSchoolQuery] = useState("")
  const [userQuery, setUserQuery] = useState("")
  const [assignedIds, setAssignedIds] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")

  const selectedSchool = useMemo(
    () => schools.find((school) => String(school.id) === String(selectedId)) || null,
    [schools, selectedId]
  )

  const visibleSchools = useMemo(() => {
    const needle = schoolQuery.trim().toLowerCase()
    if (!needle) return schools
    return schools.filter((school) =>
      [school.name, school.short_name, school.slug].some((value) =>
        String(value || "").toLowerCase().includes(needle)
      )
    )
  }, [schoolQuery, schools])

  const visibleUsers = useMemo(() => {
    return mergeUsers(selectedSchool?.admins, users).sort((a, b) =>
      userDisplayName(a).localeCompare(userDisplayName(b))
    )
  }, [selectedSchool, users])

  const loadData = async ({ keepSelection = true } = {}) => {
    setLoading(true)
    setError("")
    try {
      const params = new URLSearchParams()
      if (schoolQuery.trim()) params.set("q", schoolQuery.trim())
      if (userQuery.trim()) params.set("user_q", userQuery.trim())
      const suffix = params.toString() ? `?${params.toString()}` : ""
      const res = await authFetch(`/admin/school-admins/${suffix}`)
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudieron cargar los administradores.")
        return
      }

      const nextSchools = Array.isArray(data?.schools) ? data.schools : []
      setSchools(nextSchools)
      setUsers(Array.isArray(data?.users) ? data.users : [])
      const previous = keepSelection ? selectedId : ""
      const nextSelected =
        (previous && nextSchools.some((school) => String(school.id) === String(previous)) && previous) ||
        (nextSchools[0]?.id != null ? String(nextSchools[0].id) : "")
      setSelectedId(nextSelected)
      const nextSchool = nextSchools.find((school) => String(school.id) === String(nextSelected)) || null
      setAssignedIds((nextSchool?.admins || []).map((user) => Number(user.id)))
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
    setAssignedIds((selectedSchool?.admins || []).map((user) => Number(user.id)))
    setError("")
    setSuccess("")
  }, [selectedSchool])

  const toggleUser = (userId) => {
    setAssignedIds((current) => {
      const values = new Set(current.map((value) => Number(value)))
      const normalized = Number(userId)
      if (values.has(normalized)) values.delete(normalized)
      else values.add(normalized)
      return Array.from(values).sort((a, b) => a - b)
    })
    setError("")
    setSuccess("")
  }

  const saveAssignments = async () => {
    if (!selectedSchool?.id) return
    setSaving(true)
    setError("")
    setSuccess("")
    try {
      const res = await authFetch(`/admin/school-admins/${selectedSchool.id}`, {
        method: "PATCH",
        body: JSON.stringify({ admin_ids: assignedIds }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data?.detail || "No se pudieron guardar los administradores.")
        return
      }
      const updated = data?.school
      setSchools((current) => current.map((school) => (String(school.id) === String(updated?.id) ? updated : school)))
      setAssignedIds((updated?.admins || []).map((user) => Number(user.id)))
      setUsers((current) => mergeUsers(current, updated?.admins))
      setSuccess("Administradores actualizados.")
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setSaving(false)
    }
  }

  if (loadingSession) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de admins...</div>
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
    <div className="mx-auto max-w-7xl space-y-6 min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/admin/plataforma"
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver a admin plataforma
          </Link>
          <h2 className="mt-3 text-3xl font-semibold text-slate-900">Admins por colegio</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Asigna usuarios como administradores del colegio seleccionado.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => loadData()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Actualizar
        </Button>
      </div>

      {error ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}
      {success ? (
        <div role="status" aria-live="polite" className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      ) : null}

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.9fr)]">
        <Card className="min-w-0">
          <CardHeader className="pb-3">
            <CardTitle>Colegios</CardTitle>
            <CardDescription>Seleccioná el colegio que querés administrar.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={schoolQuery}
                onChange={(event) => setSchoolQuery(event.target.value)}
                className="pl-9"
                placeholder="Buscar colegio"
                aria-label="Buscar colegio"
              />
            </div>

            <div className="min-w-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Colegio</TableHead>
                    <TableHead>Admins</TableHead>
                    <TableHead>Estado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleSchools.map((school) => {
                    const selected = String(school.id) === String(selectedId)
                    return (
                      <TableRow
                        key={school.id}
                        onClick={() => setSelectedId(String(school.id))}
                        className={`cursor-pointer ${selected ? "bg-slate-50" : ""}`}
                      >
                        <TableCell>
                          <button
                            type="button"
                            className="flex w-full items-center gap-3 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--school-primary-soft-strong)]"
                            onClick={(event) => {
                              event.stopPropagation()
                              setSelectedId(String(school.id))
                            }}
                            aria-pressed={selected}
                          >
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
                          </button>
                        </TableCell>
                        <TableCell className="text-sm text-slate-600">{school.admins_count || 0}</TableCell>
                        <TableCell>
                          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${
                            school.is_active === false
                              ? "bg-slate-100 text-slate-600 ring-slate-200"
                              : "bg-emerald-50 text-emerald-700 ring-emerald-200"
                          }`}>
                            {school.is_active === false ? "Inactivo" : "Activo"}
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

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5" />
              Administradores
            </CardTitle>
            <CardDescription>
              {selectedSchool ? selectedSchool.name : "Seleccioná un colegio para editar sus administradores."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={userQuery}
                  onChange={(event) => setUserQuery(event.target.value)}
                  className="pl-9"
                  placeholder="Buscar usuarios por nombre, usuario o email"
                  aria-label="Buscar usuarios"
                />
              </div>
              <Button type="button" variant="outline" onClick={() => loadData()} disabled={loading}>
                Buscar
              </Button>
            </div>

            <div className="max-h-[480px] space-y-2 overflow-y-auto pr-1">
              {visibleUsers.map((user) => {
                const checked = assignedIds.includes(Number(user.id))
                return (
                  <label
                    key={user.id}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 text-sm ${
                      checked ? "border-[var(--school-primary)] bg-slate-50" : "border-slate-200 bg-white"
                    } ${user.is_active === false ? "opacity-60" : ""}`}
                  >
                    <input
                      type="checkbox"
                      className="school-radio mt-1 h-4 w-4"
                      checked={checked}
                      onChange={() => toggleUser(user.id)}
                      disabled={user.is_active === false}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-slate-900">{userDisplayName(user)}</span>
                      <span className="block truncate text-xs text-slate-500">{userMeta(user)}</span>
                    </span>
                  </label>
                )
              })}
              {!visibleUsers.length ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                  Busca un usuario para asignarlo como administrador.
                </div>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4">
              <div className="text-sm text-slate-600">
                {assignedIds.length} {assignedIds.length === 1 ? "admin seleccionado" : "admins seleccionados"}
              </div>
              <Button type="button" onClick={saveAssignments} disabled={saving || !selectedSchool}>
                <Save className="mr-2 h-4 w-4" />
                {saving ? "Guardando..." : "Guardar cambios"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}