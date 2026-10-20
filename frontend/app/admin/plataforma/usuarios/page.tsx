"use client"

import Link from "next/link"
import { FormEvent, useEffect, useMemo, useState } from "react"
import { ArrowLeft, RefreshCw, Search, Users } from "lucide-react"

import StudentEditor from "../../_components/student-editor"
import { authFetch, buildBackendUrl, useAuthGuard, useSessionContext } from "../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

type School = { id: number; name: string; short_name?: string; slug: string }
type Account = {
  id: number
  username: string
  full_name: string
  email: string
  is_active: boolean
}
type DirectoryUser = Account & {
  first_name: string
  last_name: string
  assigned_school_courses?: { id: number; code: string; name: string }[]
  children?: { id: number; full_name: string }[]
}
type DirectoryStudent = {
  id: number
  id_alumno: string
  full_name: string
  linked_user: Account | null
  parent_user: { full_name: string } | null
}
type CourseGroup = { course: { id: number | null; code: string; name: string }; students: DirectoryStudent[] }
type Directory = {
  school: School
  administradores: DirectoryUser[]
  profesores: DirectoryUser[]
  preceptores: DirectoryUser[]
  eoe: DirectoryUser[]
  integracion: DirectoryUser[]
  directivos: DirectoryUser[]
  padres: DirectoryUser[]
  alumnos_por_curso: CourseGroup[]
  totals: Record<string, number>
}

const sections = [
  ["administradores", "Administradores"],
  ["profesores", "Profesores"],
  ["preceptores", "Preceptores"],
  ["eoe", "EOE"],
  ["integracion", "Integración"],
  ["directivos", "Directivos"],
  ["alumnos", "Alumnos"],
  ["padres", "Padres"],
] as const

function courseKey(group: CourseGroup) {
  return String(group.course.id ?? group.course.code ?? group.course.name)
}

function includesQuery(values: (string | undefined)[], query: string) {
  return values.some((value) => String(value || "").toLocaleLowerCase().includes(query))
}

async function fetchDirectory(path: string) {
  try {
    return await authFetch(path)
  } catch (error) {
    const directUrl = buildBackendUrl(`/api${path}`)
    if (!/^https?:\/\//i.test(directUrl)) throw error
    const url = new URL(directUrl)
    if (typeof window !== "undefined" &&
        ["localhost", "127.0.0.1"].includes(url.hostname) &&
        ["localhost", "127.0.0.1"].includes(window.location.hostname)) {
      url.hostname = window.location.hostname
    }
    return authFetch(url.toString())
  }
}

export default function UsuariosPorColegioPage() {
  useAuthGuard()
  const session = useSessionContext()
  const allowed = !!session?.isSuperuser
  const [schools, setSchools] = useState<School[]>([])
  const [schoolId, setSchoolId] = useState("")
  const [directory, setDirectory] = useState<Directory | null>(null)
  const [section, setSection] = useState<(typeof sections)[number][0]>("profesores")
  const [courseId, setCourseId] = useState("")
  const [query, setQuery] = useState("")
  const [loadingSchools, setLoadingSchools] = useState(false)
  const [loadingDirectory, setLoadingDirectory] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [reload, setReload] = useState(0)
  const [editingUser, setEditingUser] = useState<DirectoryUser | null>(null)
  const [editForm, setEditForm] = useState({ first_name: "", last_name: "", email: "" })
  const [editError, setEditError] = useState("")
  const [editSaving, setEditSaving] = useState(false)
  const [passwordUser, setPasswordUser] = useState<Account | null>(null)
  const [passwordForm, setPasswordForm] = useState({ new_password: "", new_password_confirm: "" })
  const [passwordError, setPasswordError] = useState("")
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [editingStudent, setEditingStudent] = useState<number | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)

  useEffect(() => {
    if (!allowed) return
    let cancelled = false
    setLoadingSchools(true)
    fetchDirectory("/admin/platform-school-users/")
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data.detail || "No se pudieron cargar los colegios.")
        if (cancelled) return
        const next = Array.isArray(data.schools) ? data.schools as School[] : []
        setSchools(next)
        setSchoolId((current) => next.some((school) => String(school.id) === current) ? current : String(next[0]?.id || ""))
      })
      .catch(() => { if (!cancelled) setError("No se pudieron cargar los colegios. Revisá la conexión con el servidor.") })
      .finally(() => { if (!cancelled) setLoadingSchools(false) })
    return () => { cancelled = true }
  }, [allowed, reload])

  useEffect(() => {
    if (!allowed || !schoolId) return
    let cancelled = false
    setDirectory(null)
    setLoadingDirectory(true)
    setError("")
    fetchDirectory(`/admin/platform-school-users/${schoolId}/`)
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data.detail || "No se pudieron cargar los usuarios.")
        if (!cancelled) {
          setDirectory(data as Directory)
          setCourseId(data.alumnos_por_curso?.[0] ? courseKey(data.alumnos_por_curso[0]) : "")
        }
      })
      .catch(() => { if (!cancelled) setError("No se pudieron cargar los usuarios. Revisá la conexión con el servidor.") })
      .finally(() => { if (!cancelled) setLoadingDirectory(false) })
    return () => { cancelled = true }
  }, [allowed, schoolId, reload])

  const selectedCourse = useMemo(() => directory?.alumnos_por_curso.find((group) => courseKey(group) === courseId), [directory, courseId])
  const needle = query.trim().toLocaleLowerCase()
  const users = section === "alumnos" ? [] : (directory?.[section] || []).filter((user) =>
    includesQuery([user.full_name, user.username, user.email, ...(user.children || []).map((child) => child.full_name)], needle)
  )
  const students = (selectedCourse?.students || []).filter((student) =>
    includesQuery([student.full_name, student.id_alumno, student.linked_user?.username], needle)
  )

  function selectedSchoolHeaders() {
    return { "X-School": String(directory?.school.id || schoolId) }
  }

  function openEdit(user: DirectoryUser) {
    setEditingUser(user)
    setEditForm({ first_name: user.first_name || "", last_name: user.last_name || "", email: user.email || "" })
    setEditError("")
    setSuccess("")
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingUser || !directory || editSaving) return
    setEditSaving(true)
    setEditError("")
    try {
      const response = await authFetch(`/admin/school-users/${editingUser.id}/`, {
        method: "PATCH",
        headers: { ...selectedSchoolHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(editForm),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || "No se pudo actualizar el usuario.")
      setEditingUser(null)
      setSuccess(data.detail || "Usuario actualizado correctamente.")
      setReload((value) => value + 1)
    } catch (cause) {
      setEditError(cause instanceof Error ? cause.message : "No se pudo actualizar el usuario.")
    } finally {
      setEditSaving(false)
    }
  }

  function openPassword(user: Account) {
    setPasswordUser(user)
    setPasswordForm({ new_password: "", new_password_confirm: "" })
    setPasswordError("")
    setSuccess("")
  }

  async function resetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!passwordUser || !directory || passwordSaving) return
    if (passwordForm.new_password !== passwordForm.new_password_confirm) {
      setPasswordError("Las contraseñas no coinciden.")
      return
    }
    setPasswordSaving(true)
    setPasswordError("")
    try {
      const response = await authFetch(`/admin/platform-school-users/${directory.school.id}/${passwordUser.id}/reset-password/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(passwordForm),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.join(" ") : data.detail || "No se pudo blanquear la contraseña.")
      setPasswordUser(null)
      setPasswordForm({ new_password: "", new_password_confirm: "" })
      setSuccess(data.detail || "Contraseña blanqueada correctamente.")
    } catch (cause) {
      setPasswordError(cause instanceof Error ? cause.message : "No se pudo blanquear la contraseña.")
    } finally {
      setPasswordSaving(false)
    }
  }

  async function toggleActive(user: Account) {
    if (!directory || togglingId !== null) return
    const action = user.is_active ? "Desactivar" : "Reactivar"
    if (!window.confirm(`¿${action} la cuenta de ${user.full_name || user.username}?`)) return
    setTogglingId(user.id)
    setError("")
    setSuccess("")
    try {
      const response = await authFetch(`/admin/school-users/${user.id}/toggle-active/`, {
        method: "PATCH",
        headers: selectedSchoolHeaders(),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || "No se pudo cambiar el estado.")
      setSuccess(data.detail || "Estado actualizado correctamente.")
      setReload((value) => value + 1)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo cambiar el estado.")
    } finally {
      setTogglingId(null)
    }
  }

  function accountActions(user: Account, student?: DirectoryStudent) {
    return <div className="flex flex-wrap justify-end gap-2">
      {student && <Button type="button" size="sm" variant="outline" onClick={() => setEditingStudent(student.id)}>Editar datos</Button>}
      {!student && <Button type="button" size="sm" variant="outline" onClick={() => openEdit(user as DirectoryUser)}>Editar datos</Button>}
      <Button type="button" size="sm" variant="outline" onClick={() => openPassword(user)}>Blanquear contraseña</Button>
      <Button type="button" size="sm" variant="outline" disabled={togglingId !== null} onClick={() => toggleActive(user)}
        className={user.is_active ? "border-red-300 text-red-700 hover:bg-red-50" : "border-emerald-300 text-emerald-700 hover:bg-emerald-50"}>
        {user.is_active ? "Desactivar" : "Reactivar"}
      </Button>
    </div>
  }

  if (!session) return <p className="p-6 text-slate-600">Cargando sesión...</p>
  if (!allowed) return <Card><CardHeader><CardTitle>Acceso restringido</CardTitle><CardDescription>Esta herramienta es exclusiva de Admin Plataforma.</CardDescription></CardHeader></Card>

  return (
    <div className="space-y-6">
      <Link href="/admin/plataforma" className="inline-flex items-center gap-2 text-sm text-slate-700 hover:underline"><ArrowLeft className="h-4 w-4" /> Volver a admin plataforma</Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-3xl font-semibold text-slate-900">Usuarios por colegio</h1><p className="mt-1 text-slate-600">Consultá y administrá los usuarios del colegio seleccionado.</p></div>
        <Button variant="outline" onClick={() => setReload((value) => value + 1)} disabled={loadingSchools || loadingDirectory}><RefreshCw className="mr-2 h-4 w-4" /> Actualizar</Button>
      </div>

      <Card><CardContent className="pt-6"><label htmlFor="platform-school" className="mb-2 block text-sm font-medium">Colegio</label><select id="platform-school" className="h-11 w-full max-w-lg rounded-md border border-slate-300 bg-white px-3 text-slate-900" value={schoolId} onChange={(event) => { setSchoolId(event.target.value); setDirectory(null); setEditingUser(null); setPasswordUser(null); setEditingStudent(null); setQuery(""); setSuccess("") }} disabled={loadingSchools}>{schools.length === 0 && <option value="">{loadingSchools ? "Cargando colegios..." : error ? "No se pudieron cargar los colegios" : "No hay colegios"}</option>}{schools.map((school) => <option key={school.id} value={school.id}>{school.name}</option>)}</select></CardContent></Card>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
      {success && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-800">{success}</p>}
      {loadingDirectory && <p className="text-slate-600">Cargando usuarios...</p>}
      {directory && <>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">{sections.map(([key, label]) => <button key={key} type="button" onClick={() => { setSection(key); setQuery("") }} className={`rounded-xl border p-4 text-left transition ${section === key ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-900 hover:border-slate-400"}`}><span className="block text-sm">{label}</span><span className="mt-1 block text-2xl font-semibold">{directory.totals[key] || 0}</span></button>)}</div>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Users className="h-5 w-5" />{sections.find(([key]) => key === section)?.[1]}</CardTitle><CardDescription>{directory.school.name}</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-3">
              {section === "alumnos" && <select aria-label="Curso" className="h-10 min-w-44 rounded-md border border-slate-300 bg-white px-3" value={courseId} onChange={(event) => setCourseId(event.target.value)}>{directory.alumnos_por_curso.map((group) => <option key={courseKey(group)} value={courseKey(group)}>{group.course.code || group.course.name || "Sin curso"}</option>)}</select>}
              <div className="relative w-full max-w-md"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" /><Input aria-label="Buscar usuarios" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar por nombre, usuario o legajo" className="pl-9" /></div>
            </div>
            <div className="overflow-x-auto rounded-lg border"><Table><TableHeader><TableRow>{section === "alumnos" ? <><TableHead>Legajo</TableHead><TableHead>Alumno</TableHead><TableHead>Usuario vinculado</TableHead><TableHead>Padre vinculado</TableHead><TableHead>Estado</TableHead><TableHead className="text-right">Acción</TableHead></> : <><TableHead>Nombre</TableHead><TableHead>Usuario</TableHead><TableHead>Email</TableHead><TableHead>{section === "padres" ? "Hijos" : "Cursos"}</TableHead><TableHead>Estado</TableHead><TableHead className="text-right">Acción</TableHead></>}</TableRow></TableHeader><TableBody>
              {section === "alumnos" ? students.map((student) => <TableRow key={student.id}><TableCell>{student.id_alumno || "—"}</TableCell><TableCell>{student.full_name}</TableCell><TableCell>{student.linked_user?.username || "Sin usuario"}</TableCell><TableCell>{student.parent_user?.full_name || "Sin padre vinculado"}</TableCell><TableCell>{student.linked_user ? student.linked_user.is_active ? "Activo" : "Inactivo" : "—"}</TableCell><TableCell>{student.linked_user ? accountActions(student.linked_user, student) : <Button type="button" size="sm" variant="outline" onClick={() => setEditingStudent(student.id)}>Editar datos</Button>}</TableCell></TableRow>) : users.map((user) => <TableRow key={user.id}><TableCell className="font-medium">{user.full_name}</TableCell><TableCell>{user.username}</TableCell><TableCell>{user.email || "—"}</TableCell><TableCell>{section === "padres" ? (user.children || []).map((child) => child.full_name).join(", ") || "—" : (user.assigned_school_courses || []).map((course) => course.code || course.name).join(", ") || "—"}</TableCell><TableCell>{user.is_active ? "Activo" : "Inactivo"}</TableCell><TableCell>{accountActions(user)}</TableCell></TableRow>)}
              {(section === "alumnos" ? students.length === 0 : users.length === 0) && <TableRow><TableCell colSpan={6} className="py-8 text-center text-slate-500">No hay usuarios con este filtro.</TableCell></TableRow>}
            </TableBody></Table></div>
          </CardContent>
        </Card>
      </>}
      {editingStudent && directory && <StudentEditor key={`${directory.school.id}:${editingStudent}`} schoolId={String(directory.school.id)} studentId={editingStudent} onClose={() => setEditingStudent(null)} onSaved={() => { setEditingStudent(null); setSuccess("Alumno actualizado correctamente."); setReload((value) => value + 1) }} />}

      <Dialog open={!!editingUser} onOpenChange={(open) => { if (!open && !editSaving) setEditingUser(null) }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Editar datos de {editingUser?.username}</DialogTitle><DialogDescription>Actualizá el nombre, apellido y correo del usuario.</DialogDescription></DialogHeader>
          <form onSubmit={saveEdit} className="space-y-4">
            <div className="space-y-2"><Label htmlFor="platform-user-first-name">Nombre</Label><Input id="platform-user-first-name" required value={editForm.first_name} onChange={(event) => setEditForm((current) => ({ ...current, first_name: event.target.value }))} /></div>
            <div className="space-y-2"><Label htmlFor="platform-user-last-name">Apellido</Label><Input id="platform-user-last-name" required value={editForm.last_name} onChange={(event) => setEditForm((current) => ({ ...current, last_name: event.target.value }))} /></div>
            <div className="space-y-2"><Label htmlFor="platform-user-email">Email</Label><Input id="platform-user-email" type="email" value={editForm.email} onChange={(event) => setEditForm((current) => ({ ...current, email: event.target.value }))} /></div>
            {editError && <p role="alert" className="text-sm text-red-700">{editError}</p>}
            <DialogFooter><Button type="button" variant="outline" disabled={editSaving} onClick={() => setEditingUser(null)}>Cancelar</Button><Button type="submit" disabled={editSaving}>{editSaving ? "Guardando..." : "Guardar cambios"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!passwordUser} onOpenChange={(open) => { if (!open && !passwordSaving) setPasswordUser(null) }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Blanquear contraseña de {passwordUser?.username}</DialogTitle><DialogDescription>Ingresá una nueva contraseña para esta cuenta.</DialogDescription></DialogHeader>
          <form onSubmit={resetPassword} className="space-y-4">
            <div className="space-y-2"><Label htmlFor="platform-new-password">Nueva contraseña</Label><Input id="platform-new-password" type="password" autoComplete="new-password" required value={passwordForm.new_password} onChange={(event) => setPasswordForm((current) => ({ ...current, new_password: event.target.value }))} /></div>
            <div className="space-y-2"><Label htmlFor="platform-confirm-password">Confirmar nueva contraseña</Label><Input id="platform-confirm-password" type="password" autoComplete="new-password" required value={passwordForm.new_password_confirm} onChange={(event) => setPasswordForm((current) => ({ ...current, new_password_confirm: event.target.value }))} /></div>
            {passwordError && <p role="alert" className="text-sm text-red-700">{passwordError}</p>}
            <DialogFooter><Button type="button" variant="outline" disabled={passwordSaving} onClick={() => setPasswordUser(null)}>Cancelar</Button><Button type="submit" disabled={passwordSaving}>{passwordSaving ? "Guardando..." : "Blanquear contraseña"}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
