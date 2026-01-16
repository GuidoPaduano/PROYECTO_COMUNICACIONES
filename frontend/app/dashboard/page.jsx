"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../_lib/auth"
import { INBOX_EVENT } from "../_lib/inbox"
import { NotificationBell } from "@/components/notification-bell"

import {
  Calendar,
  Plus,
  CheckSquare,
  ChevronDown,
  Mail,
  User,
  BookOpen,
  Users,
  ClipboardList,
  Inbox,
  Gavel,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

import ComposeComunicadoFamilia from "../mensajes/_compose-comunicado-familia"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

const ROLES = ["Profesores", "Alumnos", "Padres", "Preceptores"]
const PREVIEW_KEY = "preview_role"

function hoyISO() {
  const d = new Date()
  const z = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`
}

/* ======================== Helpers “Mis notas / sanciones” ======================== */

function alumnoRouteIdFromMe(me) {
  if (!me || typeof me !== "object") return null

  const legajoPaths = [
    ["alumno", "id_alumno"],
    ["alumno_id"],
    ["id_alumno"],
    ["user", "alumno", "id_alumno"],
    ["user", "alumno_id"],
    ["user", "id_alumno"],
    ["profile", "alumno_id"],
    ["user", "profile", "alumno_id"],
  ]
  for (const path of legajoPaths) {
    let cur = me
    for (const k of path) cur = cur?.[k]
    if (cur != null && cur !== "") return cur
  }

  const pkPaths = [
    ["alumno", "id"],
    ["alumno", "pk"],
    ["user", "alumno", "id"],
    ["user", "alumno", "pk"],
  ]
  for (const path of pkPaths) {
    let cur = me
    for (const k of path) cur = cur?.[k]
    if (cur != null && cur !== "") return cur
  }

  return null
}

async function fetchAlumnoIdSelfFallback(previewRole) {
  const candidates = ["/perfil_api/"]

  for (const url of candidates) {
    try {
      const res = await authFetch(url.endsWith("/") ? url : `${url}/`, {
        headers: previewRole ? { "X-Preview-Role": previewRole } : undefined,
      })
      if (!res.ok) continue
      const data = await res.json().catch(() => ({}))
      const a = data?.alumno || data

      const legajo =
        a?.id_alumno ??
        a?.alumno_id ??
        a?.user?.alumno_id ??
        a?.user?.id_alumno ??
        a?.profile?.alumno_id
      if (legajo) return legajo

      const pk =
        a?.id ??
        a?.pk ??
        a?.alumno?.id ??
        a?.alumno?.pk ??
        a?.user?.alumno?.id ??
        a?.user?.alumno?.pk
      if (pk != null) return pk
    } catch {}
  }
  return null
}

async function resolveAlumnoRouteId(me, previewRole) {
  const direct = alumnoRouteIdFromMe(me)
  if (direct != null) return direct
  return await fetchAlumnoIdSelfFallback(previewRole)
}

export default function DashboardPage() {
  useAuthGuard()

  const [me, setMe] = useState(null)
  const [error, setError] = useState("")
  const [previewRole, setPreviewRole] = useState("")
  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || ""),
    [me]
  )

  const pfetch = (url, options = {}) => {
    const headers = { ...(options?.headers || {}) }
    if (previewRole) headers["X-Preview-Role"] = previewRole
    return authFetch(url, { ...options, headers })
  }

  const [unreadCount, setUnreadCount] = useState(0)

  useEffect(() => {
    let alive = true
    let timer = null

    const loadUnread = async () => {
      try {
        let res = await pfetch("/mensajes/unread_count/")
        if (!res.ok) res = await pfetch("/api/mensajes/unread_count/")
        if (!res.ok) return
        const j = await res.json().catch(() => ({}))
        if (alive && typeof j?.count === "number") setUnreadCount(j.count)
      } catch {}
    }

    loadUnread()
    timer = setInterval(loadUnread, 60000)

    const handler = () => loadUnread()
    if (typeof window !== "undefined") window.addEventListener(INBOX_EVENT, handler)

    return () => {
      alive = false
      if (timer) clearInterval(timer)
      if (typeof window !== "undefined") window.removeEventListener(INBOX_EVENT, handler)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewRole])

  const [openInd, setOpenInd] = useState(false)
  const [openGrp, setOpenGrp] = useState(false)
  const [openSan, setOpenSan] = useState(false)
  const [openComFam, setOpenComFam] = useState(false)

  // ✅ NUEVO: modal selector “Enviar mensajes” (profesor)
  const [openSendPicker, setOpenSendPicker] = useState(false)

  const [cursos, setCursos] = useState([])

  const [cursoInd, setCursoInd] = useState("")
  const [alumnosInd, setAlumnosInd] = useState([])
  const [alumnoInd, setAlumnoInd] = useState("")
  const [asuntoInd, setAsuntoInd] = useState("")
  const [cuerpoInd, setCuerpoInd] = useState("")
  const [loadingInd, setLoadingInd] = useState(false)
  const [msgIndErr, setMsgIndErr] = useState("")
  const [msgIndOk, setMsgIndOk] = useState("")

  const [cursoGrp, setCursoGrp] = useState("")
  const [asuntoGrp, setAsuntoGrp] = useState("")
  const [cuerpoGrp, setCuerpoGrp] = useState("")
  const [loadingGrp, setLoadingGrp] = useState(false)
  const [msgGrpErr, setMsgGrpErr] = useState("")
  const [msgGrpOk, setMsgGrpOk] = useState("")

  const [cursoSan, setCursoSan] = useState("")
  const [alumnosSan, setAlumnosSan] = useState([])
  const [alumnoSan, setAlumnoSan] = useState("")
  const [fechaSan, setFechaSan] = useState(hoyISO())
const [mensajeSan, setMensajeSan] = useState("")
  const [loadingSan, setLoadingSan] = useState(false)
  const [msgSanErr, setMsgSanErr] = useState("")
  const [msgSanOk, setMsgSanOk] = useState("")

  const [alumnoIdSelf, setAlumnoIdSelf] = useState(null)
  const [loadingAlumnoId, setLoadingAlumnoId] = useState(false)

  const [openAlumnoMsg, setOpenAlumnoMsg] = useState(false)
  const [loadingAlumnoMsg, setLoadingAlumnoMsg] = useState(false)
  const [alumnoMsgErr, setAlumnoMsgErr] = useState("")
  const [alumnoMsgOk, setAlumnoMsgOk] = useState("")
  const [destSel, setDestSel] = useState("")
  const [asuntoAlu, setAsuntoAlu] = useState("")
  const [contenidoAlu, setContenidoAlu] = useState("")
  const [destinatariosProf, setDestinatariosProf] = useState([])
  const [destinatariosPrec, setDestinatariosPrec] = useState([])

  const getCursoId = (c) => (c?.id ?? c?.value ?? c)
  const getCursoNombre = (c) => (c?.nombre ?? c?.label ?? String(getCursoId(c)))

  useEffect(() => {
    try {
      if (typeof window !== "undefined") {
        const saved = localStorage.getItem(PREVIEW_KEY) || ""
        setPreviewRole(saved)
      }
    } catch {}
  }, [])

  useEffect(() => {
    const openIndHandler = () => setOpenInd(true)
    const openGrpHandler = () => setOpenGrp(true)
    const openSanHandler = () => setOpenSan(true)
    window.addEventListener("open-individual", openIndHandler)
    window.addEventListener("open-grupal", openGrpHandler)
    window.addEventListener("open-sancion", openSanHandler)
    return () => {
      window.removeEventListener("open-individual", openIndHandler)
      window.removeEventListener("open-grupal", openGrpHandler)
      window.removeEventListener("open-sancion", openSanHandler)
    }
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        const res = await pfetch("/auth/whoami/")
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          setError(data?.detail || `Error ${res.status}`)
          return
        }
        setMe(data)
      } catch {
        setError("No se pudo obtener el perfil")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewRole])

  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoadingAlumnoId(true)
      try {
        const id = await resolveAlumnoRouteId(me || {}, previewRole)
        if (alive) setAlumnoIdSelf(id)
      } finally {
        if (alive) setLoadingAlumnoId(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [me, previewRole])

  useEffect(() => {
    ;(async () => {
      try {
        const res = await pfetch("/notas/catalogos/")
        const j = await res.json().catch(() => ({}))
        setCursos(j?.cursos || [])
      } catch {}
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewRole])

  useEffect(() => {
    if (!cursoInd) {
      setAlumnosInd([])
      setAlumnoInd("")
      return
    }
    ;(async () => {
      try {
        const res = await pfetch(`/alumnos/?curso=${encodeURIComponent(cursoInd)}`)
        const j = await res.json().catch(() => ({}))
        setAlumnosInd(j?.alumnos || [])
      } catch {
        setMsgIndErr("No se pudieron cargar los alumnos.")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoInd, previewRole])

  useEffect(() => {
    if (!cursoSan) {
      setAlumnosSan([])
      setAlumnoSan("")
      return
    }
    ;(async () => {
      try {
        const res = await pfetch(`/alumnos/?curso=${encodeURIComponent(cursoSan)}`)
        const j = await res.json().catch(() => ({}))
        setAlumnosSan(j?.alumnos || [])
      } catch {
        setMsgSanErr("No se pudieron cargar los alumnos.")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoSan, previewRole])

  useEffect(() => {
    try {
      if (typeof window !== "undefined") {
        if (previewRole) localStorage.setItem(PREVIEW_KEY, previewRole)
        else localStorage.removeItem(PREVIEW_KEY)
      }
    } catch {}
  }, [previewRole])

  async function submitIndividual(ev) {
    ev.preventDefault()
    setMsgIndErr("")
    setMsgIndOk("")
    setLoadingInd(true)
    try {
      const res = await pfetch("/mensajes/enviar/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          alumno_id: Number(alumnoInd),
          asunto: asuntoInd.trim(),
          contenido: cuerpoInd.trim(),
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      setMsgIndOk("✅ Mensaje enviado.")
      setTimeout(() => {
        setOpenInd(false)
        setCursoInd("")
        setAlumnoInd("")
        setAlumnosInd([])
        setAsuntoInd("")
        setCuerpoInd("")
        setMsgIndOk("")
      }, 600)
    } catch (e) {
      setMsgIndErr(e?.message || "No se pudo enviar.")
    } finally {
      setLoadingInd(false)
    }
  }

  async function submitGrupal(ev) {
    ev.preventDefault()
    setMsgGrpErr("")
    setMsgGrpOk("")
    setLoadingGrp(true)
    try {
      const res = await pfetch("/mensajes/enviar_grupal/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          curso: cursoGrp,
          asunto: asuntoGrp.trim(),
          contenido: cuerpoGrp.trim(),
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      setMsgGrpOk(
        `✅ Enviado a ${j?.creados ?? "varios"} destinatarios${
          j?.sin_receptor ? `, ${j.sin_receptor} sin receptor` : ""
        }.`
      )
      setTimeout(() => {
        setOpenGrp(false)
        setCursoGrp("")
        setAsuntoGrp("")
        setCuerpoGrp("")
        setMsgGrpOk("")
      }, 800)
    } catch (e) {
      setMsgGrpErr(e?.message || "No se pudo enviar.")
    } finally {
      setLoadingGrp(false)
    }
  }

  async function submitSancion(ev) {
    ev.preventDefault()
    setMsgSanErr("")
    setMsgSanOk("")
    setLoadingSan(true)
    try {
      const res = await pfetch("/sanciones/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          alumno: Number(alumnoSan),
          fecha: fechaSan,
mensaje: mensajeSan.trim(),
        }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      // ✅ UX: si se registró OK, cerramos el modal automáticamente.
      // De paso limpiamos campos para la próxima vez.
      setMsgSanOk("✅ Sanción registrada.")
      setTimeout(() => {
        setOpenSan(false)
        setCursoSan("")
        setAlumnoSan("")
        setAlumnosSan([])
        setFechaSan(hoyISO())
setMensajeSan("")
        setMsgSanOk("")
        setMsgSanErr("")
      }, 250)
    } catch (e) {
      setMsgSanErr(e?.message || "No se pudo guardar la sanción.")
    } finally {
      setLoadingSan(false)
    }
  }

  const cursoSugeridoAlumno = me?.alumno?.curso || me?.curso || me?.user?.alumno?.curso || ""

  useEffect(() => {
    if (!openAlumnoMsg) return
    let alive = true
    ;(async () => {
      setLoadingAlumnoMsg(true)
      setAlumnoMsgErr("")
      try {
        const base = "/api/mensajes/destinatarios_docentes/"
        const withCurso = cursoSugeridoAlumno
          ? `${base}?curso=${encodeURIComponent(cursoSugeridoAlumno)}`
          : base
        const fallbacks = [withCurso, base, "/mensajes/destinatarios_docentes/"]
        let data = null
        for (const url of fallbacks) {
          try {
            const r = await pfetch(url)
            if (!r.ok) continue
            data = await r.json().catch(() => ({}))
            break
          } catch {}
        }

        let arr = []
        if (Array.isArray(data?.profesores) || Array.isArray(data?.preceptores)) {
          setDestinatariosProf(Array.isArray(data?.profesores) ? data.profesores : [])
          setDestinatariosPrec(Array.isArray(data?.preceptores) ? data.preceptores : [])
        } else {
          if (Array.isArray(data)) arr = data
          else if (Array.isArray(data?.results)) arr = data.results
          else arr = []
          const norm = (v) => String(v ?? "").toLowerCase()
          setDestinatariosProf((arr || []).filter((d) => norm(d?.grupo || d?.rol || d?.role).includes("prof")))
          setDestinatariosPrec((arr || []).filter((d) => norm(d?.grupo || d?.rol || d?.role).includes("prec")))
        }

        if (!alive) return
      } catch (e) {
        if (!alive) return
        setAlumnoMsgErr(e?.message || "No se pudieron cargar los destinatarios.")
      } finally {
        if (alive) setLoadingAlumnoMsg(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [openAlumnoMsg, cursoSugeridoAlumno, previewRole])

  async function enviarMensajeAlumno() {
    if (!destSel) return setAlumnoMsgErr("Elegí un destinatario.")
    if (!asuntoAlu.trim()) return setAlumnoMsgErr("Completá el asunto.")
    if (!contenidoAlu.trim()) return setAlumnoMsgErr("Escribí el mensaje.")
    setAlumnoMsgErr("")
    setAlumnoMsgOk("")

    const payload = {
      receptor_id: Number(destSel),
      asunto: asuntoAlu.trim(),
      contenido: contenidoAlu.trim(),
      ...(cursoSugeridoAlumno ? { curso: cursoSugeridoAlumno } : {}),
    }

    const tries = [
      "/api/mensajes/alumno/enviar/",
      "/mensajes/alumno/enviar/",
      "/api/mensajes/enviar/",
      "/mensajes/enviar/",
    ]

    let sent = false
    let lastErr = ""
    for (const url of tries) {
      try {
        const r = await pfetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        })
        if (r.ok) {
          sent = true
          break
        }
        lastErr = `HTTP ${r.status}`
      } catch (e) {
        lastErr = e?.message || "Error de red"
      }
    }

    if (sent) {
      setAlumnoMsgOk("✅ Mensaje enviado.")
      try {
        window.dispatchEvent(new Event(INBOX_EVENT))
      } catch {}
      setTimeout(() => {
        setOpenAlumnoMsg(false)
        setDestSel("")
        setAsuntoAlu("")
        setContenidoAlu("")
        setAlumnoMsgOk("")
      }, 700)
    } else {
      setAlumnoMsgErr(`No se pudo enviar el mensaje. ${lastErr}`)
    }
  }

  // ✅ helpers: abrir modales desde el selector sin conflictos
  const abrirIndividualDesdePicker = () => {
    setOpenSendPicker(false)
    setTimeout(() => setOpenInd(true), 0)
  }
  const abrirGrupalDesdePicker = () => {
    setOpenSendPicker(false)
    setTimeout(() => setOpenGrp(true), 0)
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
        <Topbar userLabel={userLabel} unreadCount={unreadCount} />
        <div className="max-w-6xl mx-auto px-6 py-8">
          <Card>
            <CardContent className="pt-6 text-red-600">{error}</CardContent>
          </Card>
        </div>
      </div>
    )
  }

  if (!me) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
        <Topbar userLabel={userLabel} unreadCount={unreadCount} />
        <div className="max-w-6xl mx-auto px-6 py-8">
          <Card>
            <CardContent className="pt-6">Cargando…</CardContent>
          </Card>
        </div>
      </div>
    )
  }

  const baseGroups = Array.isArray(me.groups) ? me.groups : []
  const isSuper = !!me.is_superuser

  const effectiveGroups = isSuper && previewRole ? [previewRole] : baseGroups
  const showAll = isSuper && !previewRole

  const showProfesor = showAll || effectiveGroups.includes("Profesores")
  const showAlumno = showAll || effectiveGroups.includes("Alumnos")
  const showPadre = showAll || effectiveGroups.includes("Padres")
  const showPreceptor = showAll || effectiveGroups.includes("Preceptores")

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      <Topbar userLabel={userLabel} unreadCount={unreadCount} />

      <div className="max-w-6xl mx-auto px-6 py-8">
        {isSuper && (
          <div className="mb-6 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-600">Vista como:</span>
              <select
                className="border rounded-md px-3 py-2 text-sm bg-white"
                value={previewRole}
                onChange={(e) => setPreviewRole(e.target.value)}
              >
                <option value="">— Ver todo (superusuario) —</option>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <div className="text-xs text-gray-500">
              Grupos reales: {baseGroups?.length ? baseGroups.join(", ") : "—"}
              {isSuper ? " · superusuario" : ""}
            </div>
          </div>
        )}

        {showProfesor && <ProfesorGrid onAbrirComFam={() => setOpenComFam(true)} />}

        {showAlumno && (
          <AlumnoGrid
            alumnoIdSelf={alumnoIdSelf}
            loadingAlumnoId={loadingAlumnoId}
            onAbrirNuevoMensaje={() => setOpenAlumnoMsg(true)}
          />
        )}

        {showPadre && (
          <PadreGrid
            onAbrirNuevoMensaje={() => setOpenAlumnoMsg(true)}
            unreadCount={unreadCount}
          />
        )}

        {showPreceptor && <PreceptorGrid onAbrirComFam={() => setOpenComFam(true)} />}
      </div>

      {/* ✅ NUEVO: Selector “Enviar mensajes” (profesor) */}
      <Dialog open={openSendPicker} onOpenChange={setOpenSendPicker}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Enviar mensajes</DialogTitle>
            <DialogDescription>
              Elegí si querés enviar a un alumno en particular o a un curso entero.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <TileButton
              title="A un alumno"
              desc="Mensaje individual a un alumno"
              icon={<User className="h-4 w-4 text-blue-600" />}
              onClick={abrirIndividualDesdePicker}
              emphasis
            />
            <TileButton
              title="A un curso"
              desc="Mensaje grupal a un curso"
              icon={<Users className="h-4 w-4 text-blue-600" />}
              onClick={abrirGrupalDesdePicker}
            />
          </div>

          <div className="flex items-center justify-between pt-2">
            <Link href="/mensajes" className="text-sm text-blue-600 hover:underline">
              Abrir bandeja de entrada
            </Link>
            <Button variant="outline" onClick={() => setOpenSendPicker(false)}>
              Cerrar
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* === Modales (profesor) === */}
      <Dialog open={openInd} onOpenChange={setOpenInd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enviar mensaje individual</DialogTitle>
            <DialogDescription>
              Elegí curso y alumno; escribí el asunto y el cuerpo.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={submitIndividual} className="space-y-4">
            {msgIndErr && <div className="text-red-600 text-sm">{msgIndErr}</div>}
            {msgIndOk && <div className="text-green-700 text-sm">{msgIndOk}</div>}

            <div>
              <Label htmlFor="cursoInd">Curso</Label>
              <select
                id="cursoInd"
                className="w-full border p-2 rounded-md"
                value={cursoInd}
                onChange={(e) => setCursoInd(e.target.value)}
                required
              >
                <option value="">Seleccioná un curso…</option>
                {cursos.map((c) => (
                  <option key={getCursoId(c)} value={getCursoId(c)}>
                    {getCursoNombre(c)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="alumnoInd">Alumno</Label>
              <select
                id="alumnoInd"
                className="w-full border p-2 rounded-md"
                value={alumnoInd}
                onChange={(e) => setAlumnoInd(e.target.value)}
                required
                disabled={!cursoInd}
              >
                <option value="">
                  {cursoInd ? "Seleccioná un alumno…" : "Elegí curso primero"}
                </option>
                {alumnosInd.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nombre} ({a.id_alumno})
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="asuntoInd">Asunto</Label>
                <Input
                  id="asuntoInd"
                  value={asuntoInd}
                  onChange={(e) => setAsuntoInd(e.target.value)}
                  required
                />
              </div>
              <div className="sm:pt-6 text-xs text-gray-500">
                El mensaje se enviará al buzón del alumno/padre.
              </div>
            </div>

            <div>
              <Label htmlFor="cuerpoInd">Mensaje</Label>
              <Textarea
                id="cuerpoInd"
                value={cuerpoInd}
                onChange={(e) => setCuerpoInd(e.target.value)}
                rows={5}
                required
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpenInd(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={loadingInd || !alumnoInd}>
                {loadingInd ? "Enviando…" : "Enviar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={openGrp} onOpenChange={setOpenGrp}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enviar mensaje grupal</DialogTitle>
            <DialogDescription>Elegí un curso y escribí el mensaje.</DialogDescription>
          </DialogHeader>

          <form onSubmit={submitGrupal} className="space-y-4">
            {msgGrpErr && <div className="text-red-600 text-sm">{msgGrpErr}</div>}
            {msgGrpOk && <div className="text-green-700 text-sm">{msgGrpOk}</div>}

            <div>
              <Label htmlFor="cursoGrp">Curso</Label>
              <select
                id="cursoGrp"
                className="w-full border p-2 rounded-md"
                value={cursoGrp}
                onChange={(e) => setCursoGrp(e.target.value)}
                required
              >
                <option value="">Seleccioná un curso…</option>
                {cursos.map((c) => (
                  <option key={getCursoId(c)} value={getCursoId(c)}>
                    {getCursoNombre(c)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="asuntoGrp">Asunto</Label>
              <Input
                id="asuntoGrp"
                value={asuntoGrp}
                onChange={(e) => setAsuntoGrp(e.target.value)}
                required
              />
            </div>

            <div>
              <Label htmlFor="cuerpoGrp">Mensaje</Label>
              <Textarea
                id="cuerpoGrp"
                value={cuerpoGrp}
                onChange={(e) => setCuerpoGrp(e.target.value)}
                rows={5}
                required
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpenGrp(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={loadingGrp || !cursoGrp}>
                {loadingGrp ? "Enviando…" : "Enviar a curso"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={openSan} onOpenChange={setOpenSan}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nueva sancion disciplinaria</DialogTitle>
            <DialogDescription>
              Seleccioná curso y alumno, y escribí el motivo.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={submitSancion} className="space-y-4">
            {msgSanErr && <div className="text-red-600 text-sm">{msgSanErr}</div>}
            {msgSanOk && <div className="text-green-700 text-sm">{msgSanOk}</div>}

            <div>
              <Label htmlFor="cursoSan">Curso</Label>
              <select
                id="cursoSan"
                className="w-full border p-2 rounded-md"
                value={cursoSan}
                onChange={(e) => setCursoSan(e.target.value)}
                required
              >
                <option value="">Seleccioná un curso…</option>
                {cursos.map((c) => (
                  <option key={getCursoId(c)} value={getCursoId(c)}>
                    {getCursoNombre(c)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="alumnoSan">Alumno</Label>
              <select
                id="alumnoSan"
                className="w-full border p-2 rounded-md"
                value={alumnoSan}
                onChange={(e) => setAlumnoSan(e.target.value)}
                required
                disabled={!cursoSan}
              >
                <option value="">
                  {cursoSan ? "Seleccioná un alumno…" : "Elegí curso primero"}
                </option>
                {alumnosSan.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nombre}
                    {a.apellido ? ` ${a.apellido}` : ""} — {a.id_alumno}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label htmlFor="fechaSan">Fecha</Label>
              <Input
                id="fechaSan"
                type="date"
                value={fechaSan}
                onChange={(e) => setFechaSan(e.target.value)}
                required
              />
            </div>
<div>
              <Label htmlFor="mensajeSan">Motivo</Label>
              <Textarea
                id="mensajeSan"
                value={mensajeSan}
                onChange={(e) => setMensajeSan(e.target.value)}
                rows={5}
                required
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpenSan(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={loadingSan || !alumnoSan}>
                {loadingSan ? "Guardando…" : "Guardar sanción"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={openAlumnoMsg} onOpenChange={setOpenAlumnoMsg}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Escribir a mis docentes</DialogTitle>
            <DialogDescription>Elegí un profesor o preceptor, redactá y enviá.</DialogDescription>
          </DialogHeader>

          {alumnoMsgErr && <div className="text-sm text-red-600">{alumnoMsgErr}</div>}
          {alumnoMsgOk && <div className="text-sm text-green-700">{alumnoMsgOk}</div>}

          <div className="space-y-3">
            <div>
              <Label>Profesor</Label>
              <select
                className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                value={destSel}
                onChange={(e) => setDestSel(e.target.value)}
              >
                <option value="">Elegí un profesor…</option>
                {destinatariosProf.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.nombre || d.username || `ID ${d.id}`} {d.grupo ? `(${d.grupo})` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <Label>Preceptor</Label>
              <select
                className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                value={destSel}
                onChange={(e) => setDestSel(e.target.value)}
              >
                <option value="">Elegí un preceptor…</option>
                {destinatariosPrec.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.nombre || d.username || `ID ${d.id}`} {d.grupo ? `(${d.grupo})` : ""}
                  </option>
                ))}
              </select>
              {loadingAlumnoMsg && (
                <div className="text-xs text-gray-500 mt-1">Cargando destinatarios…</div>
              )}
            </div>

            <div>
              <Label>Asunto</Label>
              <Input
                value={asuntoAlu}
                onChange={(e) => setAsuntoAlu(e.target.value)}
                placeholder="Ej: Consulta sobre la tarea"
              />
            </div>

            <div>
              <Label>Mensaje</Label>
              <Textarea
                rows={6}
                value={contenidoAlu}
                onChange={(e) => setContenidoAlu(e.target.value)}
              />
            </div>

            <div className="flex justify-end">
              <Button onClick={enviarMensajeAlumno} disabled={loadingAlumnoMsg}>
                {loadingAlumnoMsg ? "Enviando…" : "Enviar"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <ComposeComunicadoFamilia
        open={openComFam}
        onOpenChange={setOpenComFam}
        // ✅ Preceptor: cursos restringidos a su curso. Profesor: lista completa de cursos.
        cursosEndpoint={effectiveGroups.includes("Preceptores") ? "/preceptor/cursos/" : "/notas/catalogos/"}
      />
    </div>
  )
}

/* ======================== Subcomponentes ======================== */

function Topbar({ userLabel, unreadCount }) {
  return (
    <div className="bg-blue-600 text-white px-6 py-4">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="inline-flex">
            <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center overflow-hidden">
              <img
                src={LOGO_SRC}
                alt="Escuela Santa Teresa"
                className="h-full w-full object-contain"
              />
            </div>
          </Link>
          <h1 className="text-xl font-semibold">Escuela Santa Teresa</h1>
        </div>

        <div className="flex items-center gap-4">
          <NotificationBell unreadCount={unreadCount} />

          <div className="relative">
            <Link href="/mensajes">
              <Button variant="ghost" size="icon" className="text-white hover:bg-blue-700">
                <Mail className="h-5 w-5" />
              </Button>
            </Link>
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 text-[10px] leading-none px-1.5 py-0.5 rounded-full bg-red-600 text-white border border-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <User className="h-4 w-4" />
                {userLabel}
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuItem asChild className="text-sm">
                <Link href="/perfil">
                  <div className="flex items-center">
                    <User className="h-4 w-4 mr-2" />
                    Perfil
                  </div>
                </Link>
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => {
                  try {
                    localStorage.clear()
                  } catch {}
                  window.location.href = "/login"
                }}
              >
                <span className="h-4 w-4 mr-2">🚪</span>
                Cerrar sesión
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  )
}

function ProfesorGrid({ onAbrirComFam }) {
  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold text-gray-800 mb-3">Panel del profesor</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-6">
          <Link href="/calendario" className="block">
            <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
              <CardContent className="p-6">
                <Tile
                  icon={<Calendar className="h-6 w-6 text-blue-600" />}
                  title="Ver calendario escolar"
                  desc="Consultá próximos eventos y horarios"
                />
              </CardContent>
            </Card>
          </Link>

          <Link href="/agregar_nota" className="block">
            <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
              <CardContent className="p-6">
                <Tile
                  icon={<Plus className="h-6 w-6 text-blue-600" />}
                  title="Nueva nota"
                  desc="Agregar una calificación u observación"
                />
              </CardContent>
            </Card>
          </Link>

          {/* ✅ CAMBIO: Sanciones sin botón, tarjeta clickeable */}
          <Card
            className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => {
              const ev = new Event("open-sancion", { bubbles: true })
              window.dispatchEvent(ev)
            }}
          >
            <CardContent className="p-6">
              <Tile
                icon={<Gavel className="h-6 w-6 text-blue-600" />}
                title="Nueva sancion disciplinaria"
                desc="Registrar una sanción para un alumno"
              />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          {/* ✅ MISMO COMPORTAMIENTO QUE PRECEPTORES: abre el modal unificado */}
          <Card
            className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onAbrirComFam?.()
            }}
          >
            <CardContent className="p-6">
              <Tile
                icon={<Users className="h-6 w-6 text-blue-600" />}
                title="Enviar mensajes"
                desc="Enviá mensajes a alumnos, padres o cursos"
              />
            </CardContent>
          </Card>

          <Link href="/mis-cursos" className="block">
            <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
              <CardContent className="p-6">
                <Tile
                  icon={<BookOpen className="h-6 w-6 text-blue-600" />}
                  title="Mis cursos"
                  desc="Ver la lista de cursos asignados"
                />
              </CardContent>
            </Card>
          </Link>
        </div>
      </div>
    </section>
  )
}

function AlumnoGrid({ alumnoIdSelf, loadingAlumnoId, onAbrirNuevoMensaje }) {
  const notasCard = (
    <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow">
      <CardContent className="p-6">
        <Tile
          icon={<ClipboardList className="h-6 w-6 text-blue-600" />}
          title="Mis notas"
          desc="Tus calificaciones por materia"
        />
      </CardContent>
    </Card>
  )

  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold text-gray-800 mb-3">Panel del alumno</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Link href="/calendario" className="block">
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
            <CardContent className="p-6">
              <Tile
                icon={<Calendar className="h-6 w-6 text-blue-600" />}
                title="Calendario"
                desc="Exámenes y eventos del curso"
              />
            </CardContent>
          </Card>
        </Link>

        {alumnoIdSelf ? (
          <Link
            href={`/alumnos/${encodeURIComponent(alumnoIdSelf)}?from=mis-notas&tab=notas`}
            className="block"
          >
            <div className="cursor-pointer">{notasCard}</div>
          </Link>
        ) : loadingAlumnoId ? (
          <div className="block opacity-70">
            <div className="cursor-wait">{notasCard}</div>
            <div className="px-6 pb-4 text-xs text-gray-500">Cargando vínculo…</div>
          </div>
        ) : (
          <div className="block opacity-70">
            <div className="cursor-not-allowed">{notasCard}</div>
            <div className="px-6 pb-1 text-xs text-red-600">
              No pudimos determinar tu alumno automáticamente.
            </div>
            <div className="px-6 pb-4 text-xs text-gray-600">
              Ingresá primero a tu perfil para que podamos asociar tu legajo.
            </div>
          </div>
        )}

        <Card
          className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onAbrirNuevoMensaje?.()
          }}
        >
          <CardContent className="p-6">
            <Tile
              icon={<Inbox className="h-6 w-6 text-blue-600" />}
              title="Enviar mensaje"
              desc="Enviá mensajes a Profesores y preceptores"
            />
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function PadreGrid({ onAbrirNuevoMensaje, unreadCount }) {
  return (
    <section className="mb-10">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Link href="/mis-hijos" className="block">
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
            <CardContent className="p-6">
              <Tile
                icon={<ClipboardList className="h-6 w-6 text-blue-600" />}
                title="Notas / Asistencias / Sanciones"
                desc="Seguimiento por materia y cuatrimestre"
              />
            </CardContent>
          </Card>
        </Link>

        <Link href="/calendario" className="block">
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
            <CardContent className="p-6">
              <Tile
                icon={<Calendar className="h-6 w-6 text-blue-600" />}
                title="Calendario"
                desc="Reuniones, actos y eventos"
              />
            </CardContent>
          </Card>
        </Link>

        <Card
          className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onAbrirNuevoMensaje?.()
          }}
        >
          <CardContent className="p-6">
            <Tile
              icon={<Inbox className="h-6 w-6 text-blue-600" />}
              title="Enviar mensajes"
              desc="Enviá mensajes a Profesores y preceptores"
            />
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function PreceptorGrid({ onAbrirComFam }) {
  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold text-gray-800 mb-3">Panel del preceptor</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Link href="/pasar_asistencia" className="block">
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
            <CardContent className="p-6">
              <Tile
                icon={<CheckSquare className="h-6 w-6 text-blue-600" />}
                title="Pasar asistencia"
                desc="Marcar presentes y ausentes"
              />
            </CardContent>
          </Card>
        </Link>

        <Link href="/calendario" className="block">
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
            <CardContent className="p-6">
              <Tile
                icon={<Calendar className="h-6 w-6 text-blue-600" />}
                title="Calendario del curso"
                desc="Eventos del curso a cargo"
              />
            </CardContent>
          </Card>
        </Link>

        <Link href="/gestion_alumnos" className="block">
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer">
            <CardContent className="p-6">
              <Tile
                icon={<Users className="h-6 w-6 text-blue-600" />}
                title="Gestión de Alumnos"
                desc="Ver cursos y perfiles de alumnos"
              />
            </CardContent>
          </Card>
        </Link>

        <Card
          className="shadow-sm border-0 bg-white/80 backdrop-blur-sm hover:shadow-md transition-shadow cursor-pointer"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onAbrirComFam?.()
          }}
        >
          <CardContent className="p-6">
            <Tile
              icon={<Users className="h-6 w-6 text-blue-600" />}
              title="Enviar mensajes"
              desc="Envia mensajes a alumnos, padres o cursos"
            />
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function Tile({ icon, title, desc }) {
  return (
    <div className="flex items-start gap-4">
      <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
        {icon}
      </div>
      <div className="flex-1">
        <h3 className="tile-title">{title}</h3>
        <p className="tile-subtitle">{desc}</p>
      </div>
    </div>
  )
}

function TileButton({ title, desc, icon, onClick, emphasis = false }) {
  const keyActivate = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      onClick()
    }
  }

  const base =
    "p-4 border rounded-lg transition-colors cursor-pointer select-none outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2"

  const normal = "border-gray-200 hover:border-blue-300 hover:bg-blue-50/50"

  const emph =
    "border-blue-200 bg-blue-100 text-blue-700 shadow-sm hover:bg-blue-100/80 hover:border-blue-300"

  return (
    <div
      className={`${base} ${emphasis ? emph : normal}`}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={keyActivate}
      aria-label={title}
    >
      <div className="flex items-center gap-3 mb-2">
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center ${
            emphasis ? "bg-white" : "bg-blue-100"
          }`}
        >
          <span className={emphasis ? "text-blue-600" : ""}>{icon}</span>
        </div>
        <h4 className={`font-medium ${emphasis ? "text-blue-800" : "text-gray-900"}`}>
          {title}
        </h4>
      </div>
      <p className={`text-sm ${emphasis ? "text-blue-700/80" : "text-gray-600"}`}>
        {desc}
      </p>
    </div>
  )
}
