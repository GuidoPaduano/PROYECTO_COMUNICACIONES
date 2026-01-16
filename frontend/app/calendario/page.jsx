"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import Head from "next/head"
import Script from "next/script"
import Link from "next/link"
import { authFetch, useAuthGuard } from "../_lib/auth"
import { useUnreadCount } from "../_lib/useUnreadCount"
import {
  Mail,
  User as UserIcon,
  ChevronDown,
  Calendar as CalIcon,
  Plus,
  Save,
  Trash2,
  Pencil,
  ArrowLeft,
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
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { NotificationBell } from "@/components/notification-bell"

// selector shadcn para elegir hijo (si es padre) y curso (si es preceptor)
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

// ⛔️ Sin imports NPM de FullCalendar (usamos CDN)

function hoyISO() {
  const d = new Date()
  const z = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`
}

function capitalizeFirstLetter(text) {
  const s = String(text || "")
  if (!s) return s
  return s[0].toUpperCase() + s.slice(1)
}

export default function CalendarioEscolarPage() {
  useAuthGuard()

  // contador de no leídos para campanita y mail
  const unreadCount = useUnreadCount()

  // Perfil / permisos
  const [me, setMe] = useState(null)
  const [meLoaded, setMeLoaded] = useState(false) // ✅ CLAVE: evitar que FC se cree antes del whoami

  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || "Usuario"),
    [me]
  )
  const [puedeEditar, setPuedeEditar] = useState(false)

  // curso detectado del alumno (para filtrar)
  const [alumnoCurso, setAlumnoCurso] = useState("")
  const [alumnoCursoChecked, setAlumnoCursoChecked] = useState(false)

  const grupos = useMemo(() => (Array.isArray(me?.groups) ? me.groups : []), [me])

  const isAlumno = useMemo(() => grupos.includes("Alumnos"), [grupos])
  const isPadre = useMemo(() => grupos.includes("Padres"), [grupos])
  const isPreceptor = useMemo(() => grupos.includes("Preceptores"), [grupos])
  const isProfesor = useMemo(() => grupos.includes("Profesores"), [grupos])
  const isDirectivo = useMemo(() => grupos.includes("Directivos"), [grupos])

  // UI
  const [error, setError] = useState("")
  const [okMsg, setOkMsg] = useState("")
  const [fcReady, setFcReady] = useState(false)

  // Catálogos
  const [cursos, setCursos] = useState([])
  const [tiposEvento, setTiposEvento] = useState([
    "examen",
    "acto",
    "reunión",
    "feriado",
  ])

  // hijos del padre y seleccionado
  const [hijos, setHijos] = useState([])
  const [selectedKid, setSelectedKid] = useState("")

  // cursos del preceptor y seleccionado
  const [preceptorCursos, setPreceptorCursos] = useState([]) // [{id,nombre}]
  const [selectedCurso, setSelectedCurso] = useState("")
  const [preceptorCursosLoaded, setPreceptorCursosLoaded] = useState(false)

  // FullCalendar refs
  const calRef = useRef(null)
  const calElRef = useRef(null)

  // Modales
  const [openCrear, setOpenCrear] = useState(false)
  const [openEditar, setOpenEditar] = useState(false)
  const [openEliminar, setOpenEliminar] = useState(false)

  // Formularios
  const [crear, setCrear] = useState({
    titulo: "",
    fecha: hoyISO(),
    descripcion: "",
    curso: "",
    tipo_evento: "",
  })
  const [editar, setEditar] = useState({
    id: "",
    titulo: "",
    fecha: hoyISO(),
    descripcion: "",
    curso: "",
    tipo_evento: "",
  })
  const [eliminar, setEliminar] = useState({ id: "", titulo: "" })

  // --- Si el script ya está en la página (por navegación), marcamos ready
  useEffect(() => {
    if (typeof window !== "undefined" && window.FullCalendar && !fcReady) {
      setFcReady(true)
    }
  }, [fcReady])

  // Fallback por si tarda en adjuntarse FullCalendar al window
  useEffect(() => {
    if (fcReady) return
    let t = setInterval(() => {
      if (window?.FullCalendar) {
        setFcReady(true)
        clearInterval(t)
      }
    }, 60)
    return () => clearInterval(t)
  }, [fcReady])

  // whoami + detectar permisos y cargar hijos si es padre
  useEffect(() => {
    ;(async () => {
      setMeLoaded(false)
      try {
        const r = await authFetch("/auth/whoami/")
        if (!r.ok) {
          if (typeof window !== "undefined") window.location.href = "/login"
          return
        }
        const meJson = await r.json()
        setMe(meJson)

        const groups = Array.isArray(meJson.groups) ? meJson.groups : []
        const isProfesorLocal = groups.includes("Profesores")
        const isPreceptorLocal = groups.includes("Preceptores")
        const isDirectivoLocal = groups.includes("Directivos")
        const isSuper = !!meJson.is_superuser
        const isStaff = !!meJson.is_staff

        // ✅ Debe matchear el backend (api_eventos.py): Profesores, Preceptores, Directivos, staff/superuser
        setPuedeEditar(isProfesorLocal || isPreceptorLocal || isDirectivoLocal || isSuper || isStaff)

        // Alumno: obtener curso
        try {
          if (groups.includes("Alumnos")) {
            setAlumnoCursoChecked(false)
            const pr = await authFetch("/mi-curso/")
            if (pr.ok) {
              const pj = await pr.json()
              const c = String(pj?.curso ?? "").trim()
              if (c) setAlumnoCurso(c)
            }
          }
        } catch {
        } finally {
          if (groups.includes("Alumnos")) setAlumnoCursoChecked(true)
        }

        // Preceptor: obtener cursos
        try {
          if (groups.includes("Preceptores")) {
            setPreceptorCursosLoaded(false)
            const cr = await authFetch("/preceptor/cursos/")
            if (cr.ok) {
              const cj = await cr.json().catch(() => ({}))
              const arr = Array.isArray(cj?.cursos) ? cj.cursos : []
              setPreceptorCursos(arr)

              if (!selectedCurso && arr.length > 0) {
                const firstId = String(arr[0]?.id ?? "").trim()
                if (firstId) setSelectedCurso(firstId)
              }
            } else {
              setPreceptorCursos([])
            }
          }
        } catch {
          setPreceptorCursos([])
        } finally {
          if (groups.includes("Preceptores")) setPreceptorCursosLoaded(true)
        }
      } catch {
        setError("No se pudo obtener tu perfil.")
      } finally {
        setMeLoaded(true)
      }

      // Intentar cargar hijos (si es padre)
      try {
        const hijosRes = await authFetch("/padres/mis-hijos/")
        if (hijosRes.ok) {
          const j = await hijosRes.json()
          const arr = Array.isArray(j?.results) ? j.results : []
          setHijos(arr)
          if (arr[0]?.id_alumno) setSelectedKid(String(arr[0].id_alumno))
        }
      } catch {}
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // catálogos (cursos / tipos)
  useEffect(() => {
    ;(async () => {
      try {
        const r = await authFetch("/calificaciones/nueva-nota/datos/")
        if (r.ok) {
          const data = await r.json()
          const alumnos = Array.isArray(data?.alumnos) ? data.alumnos : []
          const setC = new Set()
          for (const a of alumnos) {
            const c = String(a?.curso ?? a?.division ?? a?.grado ?? "").trim()
            if (c) setC.add(c)
          }
          setCursos(Array.from(setC).sort())
        }
      } catch {}
      try {
        const r2 = await authFetch("/eventos/tipos/")
        if (r2.ok) {
          const data = await r2.json()
          if (Array.isArray(data) && data.length) setTiposEvento(data)
        }
      } catch {}
    })()
  }, [])

  // helpers
  function refetchEvents() {
    try {
      calRef.current?.refetchEvents?.()
    } catch {}
  }

  function openEditFromEvent(ev) {
    setEditar({
      id: String(ev.id),
      titulo: ev.title || "",
      fecha: (ev.startStr || "").slice(0, 10) || hoyISO(),
      descripcion: ev.extendedProps?.description || "",
      curso: ev.extendedProps?.curso || "",
      tipo_evento: ev.extendedProps?.tipo_evento || "",
    })
    setOpenEditar(true)
  }

  // Abrir modal de creación: para preceptor, preseleccionamos el curso elegido en el calendario
  function openCrearModal() {
    setError("")
    setOkMsg("")
    setCrear((v) => ({
      ...v,
      curso: isPreceptor ? String(selectedCurso || v.curso || "") : v.curso,
    }))
    setOpenCrear(true)
  }

  // si cambia alumnoCurso, refetch automático
  useEffect(() => {
    if (!isAlumno) return
    if (!alumnoCurso) return
    refetchEvents()
  }, [isAlumno, alumnoCurso])

  // si cambia curso del preceptor, refetch automático
  useEffect(() => {
    if (!isPreceptor) return
    if (!selectedCurso) return
    refetchEvents()
  }, [isPreceptor, selectedCurso])

  // si cambia el rol, también refetch
  useEffect(() => {
    refetchEvents()
  }, [isAlumno, isPadre, isPreceptor, isProfesor, isDirectivo])

  // ✅ GATING: no crear FullCalendar hasta que el perfil esté cargado (y checks listos)
  const readyToInitCalendar = useMemo(() => {
    if (!fcReady) return false
    if (!meLoaded) return false
    if (!calElRef.current) return false

    // si es alumno, esperar a que termine el check de curso (aunque sea vacío)
    if (isAlumno && !alumnoCursoChecked) return false

    // si es preceptor, esperar a que termine de cargar cursos
    if (isPreceptor && !preceptorCursosLoaded) return false

    return true
  }, [fcReady, meLoaded, isAlumno, alumnoCursoChecked, isPreceptor, preceptorCursosLoaded])

  // ✅ FIX: limpiar tooltips colgados (evita que “aparezcan fantasmas” en otras páginas)
  function cleanupTooltips() {
    try {
      document.querySelectorAll(".fc-tooltip").forEach((n) => n.remove())
    } catch {}
  }

  // Inicializar FullCalendar (CDN global)
  useEffect(() => {
    if (!readyToInitCalendar) return
    if (calRef.current) return
    if (!window?.FullCalendar) return

    const { Calendar } = window.FullCalendar
    calRef.current = new Calendar(calElRef.current, {
      initialView: "dayGridMonth",
      locale: "es",
      height: "auto",
      buttonText: { today: "Hoy" },
      datesSet: (info) => {
        try {
          const rawTitle = info?.view?.title || ""
          const withoutDe = rawTitle.replace(/\s+de\s+/i, " ")
          const title = capitalizeFirstLetter(withoutDe)
          const titleEl = calElRef.current?.querySelector(".fc-toolbar-title")
          if (titleEl && title) titleEl.textContent = title
        } catch {}
      },

      events: async (info, success, failure) => {
        try {
          setError("")

          const desde = (info.startStr || "").slice(0, 10)
          const hasta = (info.endStr || "").slice(0, 10)

          let url = ""

          if (selectedKid) {
            url = `/padres/hijos/${encodeURIComponent(
              selectedKid
            )}/eventos/?desde=${desde}&hasta=${hasta}`
          } else if (isAlumno) {
            if (!alumnoCurso) {
              const msg =
                "No se pudo cargar tu calendario porque falta el curso del alumno. Revisá que /api/mi-curso/ devuelva {curso: '...'} para tu usuario."
              setError(msg)
              failure(new Error(msg))
              return
            }
            url = `/eventos/?curso=${encodeURIComponent(alumnoCurso)}&desde=${desde}&hasta=${hasta}`
          } else if (isPreceptor) {
            if (!selectedCurso) {
              const msg =
                "Seleccioná un curso para ver el calendario. Si no te aparece ninguno, revisá las asignaciones del preceptor."
              setError(msg)
              failure(new Error(msg))
              return
            }
            url = `/eventos/?curso=${encodeURIComponent(selectedCurso)}&desde=${desde}&hasta=${hasta}`
          } else {
            url = `/eventos/?desde=${desde}&hasta=${hasta}`
          }

          const res = await authFetch(url)
          if (!res.ok) {
            const err = await res.json().catch(() => ({}))
            throw new Error(err?.detail || `HTTP ${res.status}`)
          }
          const raw = await res.json()

          const list = Array.isArray(raw)
            ? raw
            : Array.isArray(raw?.results)
            ? raw.results
            : []

          const data = list.map((e) => ({
            id: String(e.id ?? ""),
            title: e.title ?? e.titulo ?? "",
            start: e.start ?? e.fecha ?? "",
            extendedProps: {
              description: e.extendedProps?.description ?? e.descripcion ?? "",
              curso: e.extendedProps?.curso ?? e.curso ?? "",
              tipo_evento: e.extendedProps?.tipo_evento ?? e.tipo_evento ?? "",
            },
          }))

          success(data)
        } catch (e) {
          const msg = String(e?.message || "")
          setError(msg || "No se pudieron cargar los eventos.")
          failure(e)
        }
      },

      eventDidMount: (info) => {
        const desc = info.event.extendedProps?.description
        if (!desc) return

        const el = info.el

        const tooltip = document.createElement("div")
        tooltip.className = "fc-tooltip"

        const descripcion = document.createElement("div")
        descripcion.innerText = desc
        tooltip.appendChild(descripcion)
        tooltip.appendChild(document.createElement("br"))

        if (puedeEditar) {
          const editarBtn = document.createElement("a")
          editarBtn.innerText = "✏️ Editar"
          editarBtn.href = "#"
          editarBtn.onclick = (e) => {
            e.preventDefault()
            openEditFromEvent(info.event)
          }
          tooltip.appendChild(editarBtn)

          const eliminarBtn = document.createElement("a")
          eliminarBtn.innerText = "🗑️ Eliminar"
          eliminarBtn.href = "#"
          eliminarBtn.onclick = (e) => {
            e.preventDefault()
            setEliminar({ id: String(info.event.id), titulo: info.event.title })
            setOpenEliminar(true)
          }
          tooltip.appendChild(eliminarBtn)
        }

        document.body.appendChild(tooltip)
        let hideTimeout = null

        const onEnter = (e) => {
          tooltip.style.left = e.pageX + 10 + "px"
          tooltip.style.top = e.pageY + 10 + "px"
          tooltip.style.display = "block"
        }

        const onMove = (e) => {
          tooltip.style.left = e.pageX + 10 + "px"
          tooltip.style.top = e.pageY + 10 + "px"
        }

        const onLeave = () => {
          hideTimeout = setTimeout(() => (tooltip.style.display = "none"), 200)
        }

        const onTooltipEnter = () => {
          if (hideTimeout) clearTimeout(hideTimeout)
        }

        const onTooltipLeave = () => {
          tooltip.style.display = "none"
        }

        el.addEventListener("mouseenter", onEnter)
        el.addEventListener("mousemove", onMove)
        el.addEventListener("mouseleave", onLeave)
        tooltip.addEventListener("mouseenter", onTooltipEnter)
        tooltip.addEventListener("mouseleave", onTooltipLeave)

        // ✅ Guardar refs para limpiar después (evita tooltip “fantasma”)
        el.__fcTooltip = tooltip
        el.__fcTooltipHandlers = { onEnter, onMove, onLeave, onTooltipEnter, onTooltipLeave }
        el.__fcTooltipClear = () => {
          try {
            if (hideTimeout) clearTimeout(hideTimeout)
          } catch {}
        }
      },

      // ✅ CLAVE: cuando FullCalendar desmonta el evento, limpiamos tooltip + listeners
      eventWillUnmount: (info) => {
        const el = info.el
        try {
          if (el.__fcTooltipClear) el.__fcTooltipClear()

          const t = el.__fcTooltip
          const h = el.__fcTooltipHandlers

          if (h) {
            el.removeEventListener("mouseenter", h.onEnter)
            el.removeEventListener("mousemove", h.onMove)
            el.removeEventListener("mouseleave", h.onLeave)
            if (t) {
              t.removeEventListener("mouseenter", h.onTooltipEnter)
              t.removeEventListener("mouseleave", h.onTooltipLeave)
            }
          }

          if (t && t.parentNode) t.parentNode.removeChild(t)
        } catch {}

        try {
          delete el.__fcTooltip
          delete el.__fcTooltipHandlers
          delete el.__fcTooltipClear
        } catch {}
      },
    })

    calRef.current.render()

    return () => {
      try {
        calRef.current?.destroy?.()
      } catch {}
      calRef.current = null

      // ✅ doble seguro: borrar tooltips que hayan quedado en el body
      cleanupTooltips()
    }
  }, [
    readyToInitCalendar,
    puedeEditar,
    selectedKid,
    isAlumno,
    alumnoCurso,
    isPreceptor,
    selectedCurso,
  ])

  // Refetch al cambiar de hijo
  useEffect(() => {
    if (!selectedKid) return
    refetchEvents()
  }, [selectedKid])

  // Refetch al volver con back/forward cache (por si aplica)
  useEffect(() => {
    const onShow = (e) => {
      if (e.persisted) refetchEvents()
    }
    window.addEventListener("pageshow", onShow)
    return () => window.removeEventListener("pageshow", onShow)
  }, [])

  // CRUD (AJUSTADO A TUS URLS)
  async function crearEvento() {
    setError("")
    setOkMsg("")
    try {
      const cursoToSend = (crear.curso || "").trim() || (isPreceptor ? String(selectedCurso || "") : "")
      if (isPreceptor && !cursoToSend) {
        throw new Error(
          "Seleccioná un curso asignado para crear el evento (arriba, en el selector de curso del preceptor)."
        )
      }

      const res = await authFetch("/eventos/crear/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          titulo: crear.titulo,
          fecha: crear.fecha,
          descripcion: crear.descripcion,
          curso: cursoToSend,
          tipo_evento: crear.tipo_evento,
        }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      }
      setOpenCrear(false)
      setCrear({
        titulo: "",
        fecha: hoyISO(),
        descripcion: "",
        curso: "",
        tipo_evento: "",
      })
      setOkMsg("✅ Evento creado.")
      refetchEvents()
    } catch (e) {
      setError(e.message || "No se pudo crear el evento.")
    }
  }

  async function editarEvento() {
    setError("")
    setOkMsg("")
    try {
      const cursoToSend = (editar.curso || "").trim() || (isPreceptor ? String(selectedCurso || "") : "")
      if (isPreceptor && !cursoToSend) {
        throw new Error(
          "El evento necesita un curso. Seleccioná un curso asignado al preceptor."
        )
      }

      const res = await authFetch(`/eventos/editar/${editar.id}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          titulo: editar.titulo,
          fecha: editar.fecha,
          descripcion: editar.descripcion,
          curso: cursoToSend,
          tipo_evento: editar.tipo_evento,
        }),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      }
      setOpenEditar(false)
      setOkMsg("✅ Evento actualizado.")
      refetchEvents()
    } catch (e) {
      setError(e.message || "No se pudo actualizar el evento.")
    }
  }

  async function eliminarEvento() {
    setError("")
    setOkMsg("")
    try {
      const res = await authFetch(`/eventos/eliminar/${eliminar.id}/`, {
        method: "DELETE",
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        throw new Error(j?.detail || j?.error || `Error (HTTP ${res.status})`)
      }
      setOpenEliminar(false)
      setOkMsg("🗑️ Evento eliminado.")
      refetchEvents()
    } catch (e) {
      setError(e.message || "No se pudo eliminar el evento.")
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-white">
      <Head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.css"
        />
      </Head>

      <Script
        src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js"
        strategy="afterInteractive"
        onLoad={() => setFcReady(true)}
      />

      {/* Header */}
      <div className="bg-blue-600 text-white px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center overflow-hidden">
              <img
                src={LOGO_SRC}
                alt="Escuela Santa Teresa"
                className="h-full w-full object-contain"
              />
            </div>
            <h1 className="text-xl font-semibold">Calendario escolar</h1>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            <Link href="/dashboard">
              <Button variant="ghost" className="text-white hover:bg-blue-700">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Volver al panel
              </Button>
            </Link>

            <NotificationBell unreadCount={unreadCount} />

            <div className="relative">
              <Link href="/mensajes">
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-white hover:bg-blue-700"
                >
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
                <Button
                  variant="ghost"
                  className="text-white hover:bg-blue-700 gap-2"
                >
                  <UserIcon className="h-4 w-4" />
                  {userLabel}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem asChild>
                  <Link href="/perfil">
                    <div className="flex items-center">
                      <UserIcon className="h-4 w-4 mr-2" />
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

      {/* Contenido */}
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        {okMsg && (
          <Card className="shadow-sm border-0 bg-green-50/90 backdrop-blur-sm">
            <CardContent className="p-4 text-green-800">{okMsg}</CardContent>
          </Card>
        )}
        {error && (
          <Card className="shadow-sm border-0 bg-red-50/90 backdrop-blur-sm">
            <CardContent className="p-4 text-red-800">{error}</CardContent>
          </Card>
        )}

        {/*
          Nota: para alumnos seguimos detectando el curso (alumnoCurso) para filtrar eventos,
          pero NO lo mostramos en pantalla.
        */}

        {hijos.length > 0 && (
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
            <CardContent className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                <div>
                  <Label className="block text-sm mb-1">
                    Elegí el hijo/a (calendario)
                  </Label>
                  <Select value={selectedKid} onValueChange={(v) => setSelectedKid(v)}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Seleccionar" />
                    </SelectTrigger>
                    <SelectContent>
                      {hijos.map((h) => (
                        <SelectItem key={h.id_alumno} value={String(h.id_alumno)}>
                          {[h.apellido, h.nombre].filter(Boolean).join(", ")}
                          {h.curso ? ` — ${h.curso}` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="text-sm text-gray-600 md:col-span-2">
                  El calendario mostrará únicamente eventos del curso de{" "}
                  {selectedKid ? "ese hijo/a seleccionado" : "tu hijo/a"}.
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {isPreceptor && (
          <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
            <CardContent className="p-6">
              {!preceptorCursosLoaded ? (
                <div className="text-sm text-gray-700">Cargando cursos asignados…</div>
              ) : preceptorCursos.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                  <div>
                    <Label className="block text-sm mb-1">
                      Elegí el curso (calendario)
                    </Label>
                    <Select
                      value={selectedCurso}
                      onValueChange={(v) => {
                        setSelectedCurso(v)
                        setError("")
                      }}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Seleccionar curso" />
                      </SelectTrigger>
                      <SelectContent>
                        {preceptorCursos.map((c) => (
                          <SelectItem key={String(c.id)} value={String(c.id)}>
                            {c.nombre ? String(c.nombre) : String(c.id)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="text-sm text-gray-600 md:col-span-2">
                    El calendario mostrará únicamente eventos del curso seleccionado.
                  </div>
                </div>
              ) : (
                <div className="text-sm text-gray-700">
                  <span className="font-semibold">Preceptor:</span> no tenés cursos asignados.
                  <span className="block text-gray-600 mt-1">
                    Pedile al administrador que te asigne al menos un curso (PreceptorCurso).
                  </span>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
          <CardContent className="p-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                <CalIcon className="h-6 w-6 text-blue-600" />
              </div>
              <div>
                <h3 className="font-semibold text-gray-900">
                  Eventos de la institución
                </h3>
                <p className="text-sm text-gray-600">
                  Consultá fechas importantes, exámenes, actos y reuniones.
                </p>
              </div>
            </div>
            {puedeEditar && (
              <Button onClick={openCrearModal} className="inline-flex items-center">
                <Plus className="h-4 w-4 mr-2" /> Agregar nuevo evento
              </Button>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
          <CardContent className="p-2">
            <div id="calendar" ref={calElRef} className="fc-wrapper" />
          </CardContent>
        </Card>
      </div>

      {/* --------- Modal CREAR --------- */}
      <Dialog open={openCrear} onOpenChange={setOpenCrear}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Agregar evento</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="titulo">Título</Label>
              <Input
                id="titulo"
                value={crear.titulo}
                onChange={(e) => setCrear((v) => ({ ...v, titulo: e.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="fecha">Fecha</Label>
              <Input
                type="date"
                id="fecha"
                value={crear.fecha}
                onChange={(e) => setCrear((v) => ({ ...v, fecha: e.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="descripcion">Descripción</Label>
              <Textarea
                id="descripcion"
                value={crear.descripcion}
                onChange={(e) => setCrear((v) => ({ ...v, descripcion: e.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="curso">Curso</Label>
              <select
                id="curso"
                className="border rounded-md px-3 py-2 bg-white"
                value={crear.curso}
                onChange={(e) => setCrear((v) => ({ ...v, curso: e.target.value }))}
              >
                <option value="">—</option>
                {isPreceptor
                  ? preceptorCursos.map((c) => {
                      const id = String(c?.id ?? "").trim()
                      if (!id) return null
                      const label = String(c?.nombre ?? id)
                      return (
                        <option key={id} value={id}>
                          {label}
                        </option>
                      )
                    })
                  : cursos.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
              </select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="tipo">Tipo de evento</Label>
              <select
                id="tipo"
                className="border rounded-md px-3 py-2 bg-white"
                value={crear.tipo_evento}
                onChange={(e) => setCrear((v) => ({ ...v, tipo_evento: e.target.value }))}
              >
                <option value="">—</option>
                {tiposEvento.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpenCrear(false)}>
              Cancelar
            </Button>
            <Button onClick={crearEvento}>
              <Save className="h-4 w-4 mr-2" /> Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* --------- Modal EDITAR --------- */}
      <Dialog open={openEditar} onOpenChange={setOpenEditar}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Editar evento</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="e-titulo">Título</Label>
              <Input
                id="e-titulo"
                value={editar.titulo}
                onChange={(e) => setEditar((v) => ({ ...v, titulo: e.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="e-fecha">Fecha</Label>
              <Input
                type="date"
                id="e-fecha"
                value={editar.fecha}
                onChange={(e) => setEditar((v) => ({ ...v, fecha: e.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="e-descripcion">Descripción</Label>
              <Textarea
                id="e-descripcion"
                value={editar.descripcion}
                onChange={(e) => setEditar((v) => ({ ...v, descripcion: e.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="e-curso">Curso</Label>
              <select
                id="e-curso"
                className="border rounded-md px-3 py-2 bg-white"
                value={editar.curso}
                onChange={(e) => setEditar((v) => ({ ...v, curso: e.target.value }))}
              >
                <option value="">—</option>
                {isPreceptor
                  ? preceptorCursos.map((c) => {
                      const id = String(c?.id ?? "").trim()
                      if (!id) return null
                      const label = String(c?.nombre ?? id)
                      return (
                        <option key={id} value={id}>
                          {label}
                        </option>
                      )
                    })
                  : cursos.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
              </select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="e-tipo">Tipo de evento</Label>
              <select
                id="e-tipo"
                className="border rounded-md px-3 py-2 bg-white"
                value={editar.tipo_evento}
                onChange={(e) => setEditar((v) => ({ ...v, tipo_evento: e.target.value }))}
              >
                <option value="">—</option>
                {tiposEvento.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpenEditar(false)}>
              Cancelar
            </Button>
            <Button onClick={editarEvento}>
              <Pencil className="h-4 w-4 mr-2" /> Guardar cambios
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* --------- Modal ELIMINAR --------- */}
      <Dialog open={openEliminar} onOpenChange={setOpenEliminar}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Eliminar evento</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-gray-700">
            ¿Estás seguro de que querés eliminar <strong>{eliminar.titulo}</strong>?
          </p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpenEliminar(false)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={eliminarEvento}>
              <Trash2 className="h-4 w-4 mr-2" /> Eliminar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Estilos del tooltip */}
      <style jsx global>{`
        .fc-tooltip {
          position: absolute;
          z-index: 10001;
          background: rgba(0, 0, 0, 0.85);
          color: white;
          padding: 8px 12px;
          border-radius: 4px;
          font-size: 0.85em;
          pointer-events: auto;
          max-width: 320px;
          white-space: normal;
          word-wrap: break-word;
          line-height: 1.5em;
          display: none;
        }
        .fc-tooltip a {
          display: inline-block;
          margin-right: 10px;
          color: #93c5fd;
          text-decoration: none;
          cursor: pointer;
        }
        .fc .fc-toolbar.fc-header-toolbar {
          padding: 8px;
        }
        .fc .fc-button-primary {
          background: #2563eb;
          border-color: #2563eb;
        }
        .fc .fc-button-primary:hover {
          background: #1d4ed8;
          border-color: #1d4ed8;
        }
      `}</style>
    </div>
  )
}
