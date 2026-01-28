"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useAuthGuard, authFetch } from "../_lib/auth"
import { useUnreadCount } from "../_lib/useUnreadCount"

import {
  Mail,
  User as UserIcon,
  ChevronDown,
  Plus,
  BookOpen,
  Save,
  ArrowLeft,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import SuccessMessage from "@/components/ui/success-message"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { NotificationBell } from "@/components/notification-bell"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"
const LAST_CURSO_KEY = "ultimo_curso_seleccionado"

/** ⬅️ Acepta también “NO ENTREGADO” (con espacios múltiples) */
const CALIF_REGEX = /^(?:[1-9]|10|TEA|TEP|TED|NO\s+ENTREGADO)$/i

/** ⬅️ Default local por si el backend no envía el catálogo de calificaciones */
const DEFAULT_CALIFS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "TEA", "TEP", "TED", "NO ENTREGADO"]

function califLabel(v) {
  return String(v).toUpperCase() === "NO ENTREGADO" ? "No entregado" : String(v)
}

function hoyISO() {
  const d = new Date()
  const z = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`
}

function pickId(a) {
  // ⚠️ Preferimos el PK (id) para evitar confundir legajo numérico con PK.
  // El backend acepta ambos, pero esto reduce 400 en /notas/masivo/.
  return a?.id ?? a?.pk ?? a?.id_alumno ?? a?.idAlumno ?? null
}
function pickNombre(a) {
  return (
    a?.nombre ??
    a?.full_name ??
    a?.fullName ??
    a?.apellido_nombre ??
    a?.username ??
    "Alumno"
  )
}
function pickCurso(a) {
  return a?.curso ?? a?.division ?? a?.grado ?? ""
}

export default function CargarNotasRapidas() {
  useAuthGuard()

  // contador de no leídos para la campanita / mail
  const unreadCount = useUnreadCount()

  // Perfil/rol
  const [me, setMe] = useState(null)
  const userLabel = useMemo(
    () => (me?.full_name?.trim?.() ? me.full_name : me?.username || ""),
    [me]
  )

  // Estado general
  const [error, setError] = useState("")
  const [okMsg, setOkMsg] = useState("")
  const [loadingInit, setLoadingInit] = useState(true)
  const [saving, setSaving] = useState(false)

  // Catálogos
  const [materias, setMaterias] = useState([])
  const [tipos, setTipos] = useState([])
  const [cuatris, setCuatris] = useState([1, 2])
  /** ⬅️ NUEVO: catálogo de calificaciones (viene del backend o fallback) */
  const [califs, setCalifs] = useState(DEFAULT_CALIFS)

  // Cursos y selección
  const [cursos, setCursos] = useState([]) // strings tipo "1A", "2B", etc.
  const [cursoSel, setCursoSel] = useState("")

  // Filas (una por alumno visible)
  const [rows, setRows] = useState([]) // {id, nombre, materia, tipo, calificacion, cuatrimestre, fecha, incluir}
  const [masterCheck, setMasterCheck] = useState(true)

  // Completar para todos
  const [fill, setFill] = useState({
    materia: "",
    tipo: "",
    calificacion: "",
    cuatrimestre: "",
    fecha: "",
    reemplazarTodo: false,
  })

  // ---- whoami + guard de rol (profesor o superuser) ----
  useEffect(() => {
    ;(async () => {
      try {
        const r = await authFetch("/auth/whoami/")
        if (!r.ok) {
          if (typeof window !== "undefined") window.location.href = "/login"
          return
        }
        const meJson = await r.json()
        setMe(meJson)
        const groups = Array.isArray(meJson.groups) ? meJson.groups : []
        const isProfesor = groups.includes("Profesores")
        const isSuper = !!meJson.is_superuser
        if (!(isProfesor || isSuper)) {
          if (typeof window !== "undefined") window.location.href = "/dashboard"
          return
        }
      } catch {
        setError("No se pudo obtener el perfil")
      }
    })()
  }, [])

  // ---- carga inicial catálogos + cursos (derivados de alumnos) ----
  useEffect(() => {
    ;(async () => {
      setLoadingInit(true)
      setError("")
      try {
        const res = await authFetch("/calificaciones/nueva-nota/datos/")
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()

        setMaterias(Array.isArray(data?.materias) ? data.materias : [])
        setTipos(Array.isArray(data?.tipos) ? data.tipos : [])
        setCuatris(
          Array.isArray(data?.cuatrimestres) ? data.cuatrimestres : [1, 2]
        )

        // ⬅️ NUEVO: tomar catálogo de calificaciones si el backend lo expone
        const fromApi = Array.isArray(data?.calificaciones)
          ? data.calificaciones
          : null
        if (fromApi && fromApi.length) {
          setCalifs(fromApi)
        } else {
          setCalifs(DEFAULT_CALIFS)
        }

        const alumnos = Array.isArray(data?.alumnos) ? data.alumnos : []
        const setC = new Set()
        for (const a of alumnos) {
          const c = String(pickCurso(a) || "").trim()
          if (c) setC.add(c)
        }
        setCursos(Array.from(setC).sort())
        setRows([])
      } catch {
        // si falla, seguimos con defaults locales
        setCalifs(DEFAULT_CALIFS)
        setError("No se pudieron cargar los catálogos iniciales")
      } finally {
        setLoadingInit(false)
      }
    })()
  }, [])

  // ---- al elegir curso, traer solo sus alumnos ----
  useEffect(() => {
    ;(async () => {
      if (!cursoSel) return
      setError("")
      try {
        const res = await authFetch(
          `/calificaciones/nueva-nota/datos/?curso=${encodeURIComponent(
            cursoSel
          )}`
        )
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const alumnos = Array.isArray(data?.alumnos) ? data.alumnos : []
        const nuevas = alumnos
          .map((a) => ({
            id: pickId(a),
            nombre: pickNombre(a),
            materia: "",
            tipo: "",
            calificacion: "",
            cuatrimestre: cuatris?.[0] ?? 1,
            fecha: hoyISO(),
            incluir: true,
          }))
          .filter((r) => r.id != null)

        setRows(nuevas)
        setMasterCheck(true)
      } catch {
        setError("No se pudieron cargar los alumnos del curso seleccionado")
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoSel])

  const filasIncluidas = useMemo(
    () => rows.filter((r) => r.incluir),
    [rows]
  )

  function onApplyFill() {
    setRows((prev) =>
      prev.map((r) => {
        const next = { ...r }
        const canSet = (val, curr) =>
          fill.reemplazarTodo || !curr ? val : curr
        if (fill.materia) next.materia = canSet(fill.materia, r.materia)
        if (fill.tipo) next.tipo = canSet(fill.tipo, r.tipo)
        if (fill.calificacion)
          next.calificacion = canSet(fill.calificacion, r.calificacion)
        if (fill.cuatrimestre)
          next.cuatrimestre = Number(
            canSet(fill.cuatrimestre, r.cuatrimestre)
          )
        if (fill.fecha) next.fecha = canSet(fill.fecha, r.fecha)
        return next
      })
    )
  }

  function toggleMaster(check) {
    setMasterCheck(check)
    setRows((prev) => prev.map((r) => ({ ...r, incluir: check })))
  }

  async function guardarSeleccionadas(e) {
    e?.preventDefault?.()
    setOkMsg("")
    setError("")

    const scrollToTop = () => {
      try {
        window.scrollTo({ top: 0, behavior: "smooth" })
      } catch {
        try {
          window.scrollTo(0, 0)
        } catch {}
      }
    }

    // Validación
    const invalid = filasIncluidas.filter(
      (r) =>
        !r.id ||
        !r.materia ||
        !r.tipo ||
        !CALIF_REGEX.test(String(r.calificacion).toUpperCase()) ||
        !r.cuatrimestre
    )
    if (invalid.length) {
      setError(
        "Completá todos los campos en las filas seleccionadas. Calificación válida: 1–10, TEA/TEP/TED o No entregado."
      )
      return
    }

    setSaving(true)
    try {
      const notas = filasIncluidas.map((r) => ({
        alumno_id: r.id,
        materia: String(r.materia).trim(),
        tipo: String(r.tipo).trim(),
        calificacion: String(r.calificacion).toUpperCase().trim(),
        cuatrimestre: Number(r.cuatrimestre),
        fecha: r.fecha || hoyISO(),
      }))

      // 1) intento masivo “oficial”
      let res = await authFetch("/calificaciones/notas/masivo/", {
        method: "POST",
        body: JSON.stringify({ notas }),
      })

      if (res.status === 404 || res.status === 405) {
        // 2) intento legacy (tu vista /agregar-nota/)
        res = await authFetch("/agregar-nota/", {
          method: "POST",
          body: JSON.stringify({ notas }),
        })
      }

      if (res.status === 404 || res.status === 405) {
        // 3) fallback: una por una
        let ok = 0
        for (const n of notas) {
          const r1 = await authFetch("/calificaciones/notas/", {
            method: "POST",
            body: JSON.stringify(n),
          })
          if (r1.ok) ok += 1
        }
        if (ok === 0) throw new Error("No se pudo guardar ninguna nota.")
        setOkMsg(`✅ Guardadas ${ok} de ${notas.length} notas`)
        scrollToTop()
      } else if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        // Si el backend devuelve errores detallados por fila (masivo), los mostramos.
        if (Array.isArray(err?.errors) && err.errors.length) {
          const first = err.errors[0]
          const msg =
            typeof first === "string"
              ? first
              : `Fila ${Number(first.index ?? 0) + 1}: ${JSON.stringify(first.errors || first)}`
          throw new Error(msg)
        }
        throw new Error(
          err?.detail || err?.error || `Error al guardar (HTTP ${res.status})`
        )
      } else {
        setOkMsg(`✅ Guardadas ${notas.length} notas`)
        scrollToTop()
      }
    } catch (e) {
      setError(e?.message || "Fallo al guardar")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header (misma estética que dashboard) */}
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
            <h1 className="text-xl font-semibold">Cargar notas (rápido)</h1>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            <Link href="/dashboard">
              <Button variant="ghost" className="text-white hover:bg-blue-700">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Volver al panel
              </Button>
            </Link>

            {/* Campanita con menú de notificaciones */}
            <NotificationBell unreadCount={unreadCount} />

            {/* Mail con badge y link a mensajes */}
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

      {/* Contenido principal (mismo estilo de cards que el dashboard) */}
      <div className="space-y-6">
        {/* Flashes */}
        {okMsg && (
          <div className="mb-3">
            <SuccessMessage>{okMsg}</SuccessMessage>
          </div>
        )}
        {error && (
          <Card className="shadow-sm border-0 bg-red-50/90 backdrop-blur-sm">
            <CardContent className="p-4 text-red-800">{error}</CardContent>
          </Card>
        )}

        {/* 1) Selector de curso */}
        <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
          <CardContent className="p-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                <BookOpen className="h-6 w-6 text-blue-600" />
              </div>
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-3 flex-wrap">
                  <label className="font-semibold text-gray-900">
                    Curso:
                  </label>
                  <select
                    className="border rounded-lg px-3 py-2 bg-white"
                    value={cursoSel}
                    onChange={(e) => {
                      const value = e.target.value
                      setCursoSel(value)
                      try {
                        if (value) localStorage.setItem(LAST_CURSO_KEY, value)
                      } catch {}
                    }}
                    disabled={loadingInit}
                  >
                    <option value="">-- Seleccionar Curso --</option>
                    {cursos.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                  <span className="text-sm text-gray-600">
                    Elegí un curso para listar sus alumnos.
                  </span>
                </div>
                {loadingInit && (
                  <p className="text-sm text-gray-500">Cargando datos…</p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Solo mostramos resto si hay curso seleccionado */}
        {cursoSel && (
          <>
            {/* 2) Completar para todos */}
            <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
              <CardContent className="p-6 space-y-4">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    <Plus className="h-6 w-6 text-blue-600" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between flex-wrap gap-3">
                      <strong className="text-gray-900">
                        Completar para todos
                      </strong>
                      <div className="flex items-center gap-2">
                        <label className="text-sm text-gray-700">
                          <input
                            type="checkbox"
                            className="mr-2 align-middle"
                            checked={fill.reemplazarTodo}
                            onChange={(e) =>
                              setFill((f) => ({
                                ...f,
                                reemplazarTodo: e.target.checked,
                              }))
                            }
                          />
                          Reemplazar también campos ya llenos
                        </label>
                        <Button onClick={onApplyFill}>
                          Aplicar
                        </Button>
                      </div>
                    </div>

                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
                      <div className="space-y-1">
                        <label className="block text-sm font-medium text-gray-700">
                          Materia
                        </label>
                        <select
                          className="w-full border rounded-lg px-3 py-2 bg-white"
                          value={fill.materia}
                          onChange={(e) =>
                            setFill((f) => ({ ...f, materia: e.target.value }))
                          }
                        >
                          <option value="">—</option>
                          {materias.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="space-y-1">
                        <label className="block text-sm font-medium text-gray-700">
                          Tipo
                        </label>
                        <select
                          className="w-full border rounded-lg px-3 py-2 bg-white"
                          value={fill.tipo}
                          onChange={(e) =>
                            setFill((f) => ({ ...f, tipo: e.target.value }))
                          }
                        >
                          <option value="">—</option>
                          {(tipos.length
                            ? tipos
                            : ["evaluacion", "tp", "oral", "recuperatorio"]
                          ).map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="space-y-1">
                        <label className="block text-sm font-medium text-gray-700">
                          Calificación
                        </label>
                        <select
                          className="w-full border rounded-lg px-3 py-2 bg-white"
                          value={fill.calificacion}
                          onChange={(e) =>
                            setFill((f) => ({
                              ...f,
                              calificacion: e.target.value,
                            }))
                          }
                        >
                          <option value="">—</option>
                          {(califs?.length ? califs : DEFAULT_CALIFS).map(
                            (v) => (
                              <option
                                key={String(v)}
                                value={String(v)}
                              >
                                {califLabel(v)}
                              </option>
                            )
                          )}
                        </select>
                      </div>

                      <div className="space-y-1">
                        <label className="block text-sm font-medium text-gray-700">
                          Cuatr.
                        </label>
                        <select
                          className="w-full border rounded-lg px-3 py-2 bg-white"
                          value={fill.cuatrimestre}
                          onChange={(e) =>
                            setFill((f) => ({
                              ...f,
                              cuatrimestre: e.target.value,
                            }))
                          }
                        >
                          <option value="">—</option>
                          {cuatris.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="space-y-1">
                        <label className="block text-sm font-medium text-gray-700">
                          Fecha
                        </label>
                        <input
                          type="date"
                          className="w-full border rounded-lg px-3 py-2 bg-white"
                          value={fill.fecha}
                          onChange={(e) =>
                            setFill((f) => ({ ...f, fecha: e.target.value }))
                          }
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* 3) Tabla de carga */}
            <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
              <CardContent className="p-0 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 text-left">
                      <th className="px-4 py-3 border-b">
                        <label className="inline-flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={masterCheck}
                            onChange={(e) => toggleMaster(e.target.checked)}
                          />
                          Incluir
                        </label>
                      </th>
                      <th className="px-4 py-3 border-b">Alumno</th>
                      <th className="px-4 py-3 border-b">Materia</th>
                      <th className="px-4 py-3 border-b">Tipo</th>
                      <th className="px-4 py-3 border-b">Calificación</th>
                      <th className="px-4 py-3 border-b">Cuatr.</th>
                      <th className="px-4 py-3 border-b">Fecha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, idx) => (
                      <tr key={r.id} className="border-b last:border-b-0">
                        <td className="px-4 py-2">
                          <input
                            type="checkbox"
                            className="chk-incluir"
                            checked={r.incluir}
                            onChange={(e) =>
                              setRows((prev) => {
                                const copy = [...prev]
                                copy[idx] = {
                                  ...copy[idx],
                                  incluir: e.target.checked,
                                }
                                if (!e.target.checked) setMasterCheck(false)
                                return copy
                              })
                            }
                          />
                        </td>
                        <td className="px-4 py-2">{r.nombre}</td>
                        <td className="px-4 py-2">
                          <select
                            className="w-full border rounded-md px-2 py-1 bg-white"
                            value={r.materia}
                            onChange={(e) =>
                              setRows((prev) => {
                                const copy = [...prev]
                                copy[idx] = {
                                  ...copy[idx],
                                  materia: e.target.value,
                                }
                                return copy
                              })
                            }
                          >
                            <option value="">—</option>
                            {materias.map((m) => (
                              <option key={m} value={m}>
                                {m}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="px-4 py-2">
                          <select
                            className="w-full border rounded-md px-2 py-1 bg-white"
                            value={r.tipo}
                            onChange={(e) =>
                              setRows((prev) => {
                                const copy = [...prev]
                                copy[idx] = {
                                  ...copy[idx],
                                  tipo: e.target.value,
                                }
                                return copy
                              })
                            }
                          >
                            <option value="">—</option>
                            {(tipos.length
                              ? tipos
                              : ["evaluacion", "tp", "oral", "recuperatorio"]
                            ).map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="px-4 py-2">
                          <select
                            className="w-full border rounded-md px-2 py-1 bg-white"
                            value={r.calificacion}
                            onChange={(e) =>
                              setRows((prev) => {
                                const copy = [...prev]
                                copy[idx] = {
                                  ...copy[idx],
                                  calificacion: e.target.value,
                                }
                                return copy
                              })
                            }
                          >
                            <option value="">—</option>
                            {(califs?.length ? califs : DEFAULT_CALIFS).map(
                              (v) => (
                                <option
                                  key={String(v)}
                                  value={String(v)}
                                >
                                  {califLabel(v)}
                                </option>
                              )
                            )}
                          </select>
                        </td>
                        <td className="px-4 py-2">
                          <select
                            className="w-full border rounded-md px-2 py-1 bg-white"
                            value={r.cuatrimestre}
                            onChange={(e) =>
                              setRows((prev) => {
                                const copy = [...prev]
                                copy[idx] = {
                                  ...copy[idx],
                                  cuatrimestre: Number(e.target.value),
                                }
                                return copy
                              })
                            }
                          >
                            <option value="">—</option>
                            {cuatris.map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="px-4 py-2">
                          <input
                            type="date"
                            className="w-full border rounded-md px-2 py-1 bg-white"
                            value={r.fecha || ""}
                            onChange={(e) =>
                              setRows((prev) => {
                                const copy = [...prev]
                                copy[idx] = {
                                  ...copy[idx],
                                  fecha: e.target.value,
                                }
                                return copy
                              })
                            }
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Acciones */}
                <div className="flex items-center gap-3 px-4 py-4">
                  <Button
                    onClick={guardarSeleccionadas}
                    disabled={saving}
                    className="inline-flex items-center"
                  >
                    {saving ? (
                      "Guardando…"
                    ) : (
                      <>
                        <Save className="h-4 w-4 mr-2" /> Guardar seleccionadas
                      </>
                    )}
                  </Button>
                  <Link href="/dashboard">
                    <Button
                      className="inline-flex items-center"
                    >
                      <ArrowLeft className="h-4 w-4 mr-2" /> Volver
                    </Button>
                  </Link>
                  <span className="text-sm text-gray-600">
                    Solo se guardan las filas tildadas en “Incluir”.
                  </span>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}

