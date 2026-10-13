"use client"

import Link from "next/link"
import { ReactNode, useEffect, useState } from "react"
import { authFetch, useAuthGuard, useSessionContext } from "../../_lib/auth"
import { Button } from "@/components/ui/button"

type Member = { id: number; full_name: string; username: string; email: string; staff_role: string; is_active: boolean }

export default function EoeSchoolTeam({ navigation }: { navigation: ReactNode }) {
  useAuthGuard()
  const session = useSessionContext()
  const allowed = !!session?.isSuperuser || !!session?.groups?.some((group) => ['administradores', 'administrador'].includes(group.toLowerCase()))
  const [members, setMembers] = useState<Member[]>([])
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (!allowed) return
    let active = true
    setLoading(true); setError(""); setMembers([])
    ;(async () => {
      try {
        const response = await authFetch('/admin/staff/')
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'No se pudo cargar el equipo EOE.')
        if (active) setMembers((data.users || []).filter((user: Member) => user.staff_role === 'EOE'))
      } catch (err) { if (active) setError(err instanceof Error ? err.message : 'No se pudo cargar el equipo EOE.') }
      finally { if (active) setLoading(false) }
    })()
    return () => { active = false }
  }, [allowed, session?.school?.id, retry])
  if (!session) return <p>Cargando equipo…</p>
  if (!allowed) return <p>Solo los administradores del colegio pueden consultar esta herramienta.</p>
  return <div className="mx-auto max-w-6xl space-y-6">
    <header><Link href="/admin/colegio" className="text-sm text-slate-600">← Volver a admin colegio</Link><h2 className="mt-3 text-3xl font-semibold">EOE e Integración</h2><p className="mt-2 text-sm text-slate-600">{session.school?.short_name || session.school?.name} · Equipo de acompañamiento</p></header>
    {navigation}
    <section className="surface-card space-y-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-xl font-semibold">Gabinete EOE</h3><Link href="/admin/colegio/nuevo-usuario" className="text-sm font-medium underline">Crear integrante</Link></div>
      <p className="text-sm text-slate-600">Los integrantes del EOE pertenecen al colegio y acceden a todos sus alumnos PPI. No necesitan asignaciones a cursos ni a estudiantes.</p>
      {loading ? <p role="status">Cargando equipo…</p> : error ? <div role="alert">{error} <Button variant="outline" onClick={() => setRetry((n) => n + 1)}>Reintentar</Button></div> : members.length ? <ul className="divide-y divide-slate-200">{members.map((member) => <li key={member.id} className="flex items-center justify-between gap-3 py-3"><div><p className="font-medium">{member.full_name || member.username}</p><p className="text-sm text-slate-500">{member.email || member.username}</p></div><span className="text-sm text-slate-500">{member.is_active ? 'Activo' : 'Inactivo'}</span></li>)}</ul> : <p className="text-sm text-slate-500">Todavía no hay integrantes EOE en este colegio. Podés crearlos desde Nuevo usuario, eligiendo el rol EOE.</p>}
      <Link href="/admin/colegio/usuarios" className="inline-block text-sm font-medium underline">Administrar usuarios del colegio</Link>
    </section>
  </div>
}
