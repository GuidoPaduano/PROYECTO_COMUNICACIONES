"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch } from "../_lib/auth"
import { ChevronLeft, Save, CheckSquare, User } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

/* ------------------------------------------------------------
   Helpers
------------------------------------------------------------ */
async function fetchApi(url, opts = {}, timeoutMs = 60000) {
  // ✅ NUEVO: timeout más realista (60s) + abort para no quedar clavado
  const controller = new AbortController()
  const t = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await authFetch(url, { ...(opts || {}), signal: controller.signal })

    // Leemos como texto y parseamos JSON si se puede (evita cuelgues con respuestas no-JSON)
    const raw = await res.text().catch(() => "")
    let data = {}
    try {
      data = raw ? JSON.parse(raw) : {}
    } catch {
      data = raw ? { detail: raw } : {}
    }

    return { ok: res.ok, data, status: res.status }
  } catch (e) {
    const isAbort = e?.name === "AbortError"
    return {
      ok: false,
      status: 0,
      data: {
        detail: isAbort
          ? "Tiempo de espera agotado. Reintentá (si vuelve a pasar, el guardado en el backend está lento)."
          : "Error de red.",
      },
    }
  } finally {
    clearTimeout(t)
  }
}

function todayISO() {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

// ✅ evita "1A — 1A" y normaliza estructura
function normalizeCursoItem(c) {
  if (typeof c === "string") {
    const v = c.trim()
    return { value: v, text: v }
  }

  const value = String(c?.curso ?? c?.value ?? c?.id ?? c?.codigo ?? c?.nombre ?? "").trim()
  const nombre = String(c?.nombre ?? c?.label ?? "").trim()

  const text = nombre ? (nombre === value ? value : `${value} — ${nombre}`) : value
  return { value: value || nombre || "", text: text || "" }
}

export default function PasarAsistenciaPage() {
  useAuthGuard()

  const [me, setMe] = useState(null)
  const userLabel = useMemo(() => {
    return me?.full_name?.trim?.() ? me.full_name : me?.username || "Usuario"
  }, [me])

  const [loadingCursos, setLoadingCursos] = useState(true)
  const [cursos, setCursos] = useState([])
  const [cursoSel, setCursoSel] = useState("")

  const [fecha, setFecha] = useState(todayISO())
  const [tipoAsistencia, setTipoAsistencia] = useState("clases")

  const [loadingAlumnos, setLoadingAlumnos] = useState(false)
  const [alumnos, setAlumnos] = useState([])

  // marcas: { alumnoKey: "presente" | "tarde" | "ausente" }
  const [marcas, setMarcas] = useState({})

  const [saving, setSaving] = useState(false)
  const [okMsg, setOkMsg] = useState("")
  const [errMsg, setErrMsg] = useState("")

  // whoami
  useEffect(() => {
    let alive = true
    ;(async () => {
      const who = await fetchApi("/auth/whoami/")
      if (alive && who.ok) setMe(who.data)
    })()
    return () => {
      alive = false
    }
  }, [])

  // cargar cursos del preceptor
  useEffect(() => {
    let alive = true
    setLoadingCursos(true)

    ;(async () => {
      try {
        const tries = [
          "/preceptores/mis-cursos/",
          "/api/preceptores/mis-cursos/",
          "/cursos/mis-cursos/",
          "/api/cursos/mis-cursos/",
          "/preceptor/asistencias/cursos/",
          "/api/preceptor/asistencias/cursos/",
        ]

        let data = null
        for (const url of tries) {
          const r = await fetchApi(url)
          if (r.ok) {
            data = r.data
            break
          }
        }

        const arr = Array.isArray(data) ? data : data?.results || data?.cursos || []
        const list = Array.isArray(arr) ? arr : []
        if (!alive) return

        setCursos(list)

        const first = list?.[0]
        const norm = first ? normalizeCursoItem(first) : { value: "", text: "" }
        setCursoSel((prev) => prev || norm.value)
      } finally {
        if (alive) setLoadingCursos(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [])

  // cargar alumnos por curso
  useEffect(() => {
    if (!cursoSel) return
    let alive = true
    setLoadingAlumnos(true)
    setErrMsg("")
    setOkMsg("")

    ;(async () => {
      try {
        const tries = [
          `/alumnos/curso/${encodeURIComponent(cursoSel)}/`,
          `/api/alumnos/curso/${encodeURIComponent(cursoSel)}/`,
          `/gestion_alumnos/api/curso/${encodeURIComponent(cursoSel)}/`,
          `/alumnos/?curso=${encodeURIComponent(cursoSel)}`,
          `/api/alumnos/?curso=${encodeURIComponent(cursoSel)}`,
        ]

        let data = null
        for (const url of tries) {
          const r = await fetchApi(url)
          if (r.ok) {
            data = r.data
            break
          }
        }

        const arr = Array.isArray(data) ? data : data?.results || data?.alumnos || []
        const list = Array.isArray(arr) ? arr : []
        if (!alive) return

        setAlumnos(list)

        // init: todos presentes
        const init = {}
        for (const a of list) {
          const pk = a?.id ?? a?.pk
          const code = a?.id_alumno ?? a?.codigo
          const key = pk != null ? String(pk) : String(code)
          init[key] = "presente"
        }
        setMarcas(init)
      } catch (e) {
        if (alive) setErrMsg("No se pudieron cargar los alumnos.")
      } finally {
        if (alive) setLoadingAlumnos(false)
      }
    })()

    return () => {
      alive = false
    }
  }, [cursoSel])

  // cargar asistencias ya guardadas para (curso + fecha + tipo)
  useEffect(() => {
    if (!cursoSel || !fecha) return
    if (!alumnos.length) return

    let alive = true
    setErrMsg("")
    setOkMsg("")

    ;(async () => {
      try {
        const r2 = await fetchApi(
          `/asistencias/curso/?curso=${encodeURIComponent(
            cursoSel
          )}&fecha=${encodeURIComponent(fecha)}&tipo=${encodeURIComponent(
            tipoAsistencia
          )}`
        )

        if (!alive) return
        if (!r2.ok) return

        const d2 = r2.data || {}
        const items = Array.isArray(d2?.asistencias)
          ? d2.asistencias
          : Array.isArray(d2?.items)
          ? d2.items
          : []

        // map por alumno_id (PK)
        const map = new Map()
        for (const it of items) {
          const aid = it?.alumno_id ?? it?.alumnoPk ?? it?.alumno_pk ?? null
          if (aid == null) continue
          const pres = !!it?.presente
          const tar = !!it?.tarde
          const estado = pres ? (tar ? "tarde" : "presente") : "ausente"
          map.set(String(aid), estado)
        }

        setMarcas((prev) => {
          const next = { ...prev }
          for (const a of alumnos) {
            const pk = a?.id ?? a?.pk
            const code = a?.id_alumno ?? a?.codigo
            const key = pk != null ? String(pk) : String(code)
            if (pk != null && map.has(String(pk))) {
              next[key] = map.get(String(pk))
            }
          }
          return next
        })
      } catch {
        // silencioso
      }
    })()

    return () => {
      alive = false
    }
  }, [cursoSel, fecha, tipoAsistencia, alumnos])

  function marcarTodos(estado) {
    setMarcas((prev) => {
      const next = { ...prev }
      for (const k of Object.keys(next)) next[k] = estado
      return next
    })
  }

  async function guardar() {
    if (!cursoSel) return
    if (!fecha) return
    if (!tipoAsistencia) return
    if (!alumnos.length) return

    setSaving(true)
    setErrMsg("")
    setOkMsg("")

    try {
      // ✅ NUEVO: armamos payload 100% basado en PK cuando existe (lo más seguro)
      // Mantenemos "presentes" como compat, pero el backend ideal usa el mapping.
      const asistenciasPayload = {}
      const presentes = []

      for (const a of alumnos) {
        const pk = a?.id ?? a?.pk
        const code = a?.id_alumno ?? a?.codigo
        const key = pk != null ? String(pk) : String(code)
        const estado = marcas[key] || "presente"
        const isPresente = estado !== "ausente"

        // Preferimos PK: si hay pk, la clave es el pk.
        if (pk != null) {
          asistenciasPayload[String(pk)] = estado
          if (isPresente) presentes.push(Number(pk))
        } else if (code != null) {
          // fallback por si algún listado viene sin id
          asistenciasPayload[String(code)] = estado
        }
      }

      const r = await fetchApi("/asistencias/registrar/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          curso: cursoSel,
          fecha,
          tipo_asistencia: tipoAsistencia,
          // ✅ dejamos compat por si backend viejo lo usa
          tipo: tipoAsistencia,
          presentes,
          asistencias: asistenciasPayload,
        }),
      }, 60000) // ✅ NUEVO: timeout explícito 60s para el POST

      if (!r.ok) {
        const msg =
          r.data?.error ||
          r.data?.detail ||
          "No se pudo guardar la asistencia."
        setErrMsg(msg)
        return
      }

      if (r.data && (r.data.ok === false || r.data.success === false)) {
        const msg = r.data?.detail || "No se pudo guardar la asistencia."
        setErrMsg(msg)
        return
      }

      setOkMsg("Asistencia guardada ✅")
    } catch (e) {
      setErrMsg("Error de red al guardar la asistencia.")
    } finally {
      setSaving(false)
    }
  }

  const isToday = fecha === todayISO()

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      {/* Topbar */}
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
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <CheckSquare className="h-5 w-5" />
              Pasar asistencia
            </h1>
          </div>

          <div className="flex items-center gap-2">
            <Link href="/dashboard" prefetch>
              <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
                <ChevronLeft className="h-4 w-4" />
                Volver al panel
              </Button>
            </Link>

            <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
              <User className="h-4 w-4" />
              {userLabel}
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-6">
        <Card className="shadow-sm border-0 bg-white/80 backdrop-blur-sm">
          <CardContent className="p-6">
            {/* Controles */}
            <div className="flex flex-col lg:flex-row gap-4 items-start lg:items-end">
              <div className="flex flex-wrap gap-4 items-end">
                {/* Curso */}
                <div className="flex flex-col">
                  <label className="block text-sm font-medium text-gray-900">Curso</label>
                  <select
                    className="mt-1 h-10 border rounded-md px-3 bg-white"
                    value={cursoSel}
                    onChange={(e) => setCursoSel(e.target.value)}
                    disabled={loadingCursos || saving}
                  >
                    {loadingCursos ? (
                      <option value="">Cargando…</option>
                    ) : cursos.length === 0 ? (
                      <option value="">Sin cursos</option>
                    ) : (
                      cursos.map((c, idx) => {
                        const norm = normalizeCursoItem(c)
                        const v = norm.value || String(idx)
                        return (
                          <option key={v} value={norm.value}>
                            {norm.text}
                          </option>
                        )
                      })
                    )}
                  </select>
                </div>

                {/* Fecha */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2">
                    <label className="block text-sm font-medium text-gray-900">Fecha</label>
                    {isToday && (
                      <span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">
                        Hoy
                      </span>
                    )}
                  </div>
                  <input
                    id="fecha"
                    type="date"
                    className={`mt-1 h-10 border rounded-md px-3 ${!isToday ? "bg-gray-50" : ""}`}
                    value={fecha}
                    max={todayISO()}
                    disabled={saving}
                    onChange={(e) => {
                      const v = e.target.value
                      if (v && v <= todayISO()) {
                        setFecha(v)
                        setOkMsg("")
                        setErrMsg("")
                      }
                    }}
                  />
                </div>

                {/* Tipo */}
                <div className="flex flex-col min-w-[190px]">
                  <label className="block text-sm font-medium text-gray-900">Tipo</label>
                  <select
                    className="mt-1 h-10 w-full border rounded-md px-3 bg-white"
                    value={tipoAsistencia}
                    disabled={saving}
                    onChange={(e) => {
                      setTipoAsistencia(e.target.value)
                      setOkMsg("")
                      setErrMsg("")
                    }}
                  >
                    <option value="clases">Clases</option>
                    <option value="informatica">Informática</option>
                    <option value="catequesis">Catequesis</option>
                  </select>
                </div>

                <div className="ml-auto flex gap-2 self-end">
                  <Button
                    variant="outline"
                    className="h-10"
                    onClick={() => marcarTodos("presente")}
                    disabled={!alumnos.length || saving}
                  >
                    Marcar todos PRESENTES
                  </Button>
                  <Button
                    variant="outline"
                    className="h-10"
                    onClick={() => marcarTodos("ausente")}
                    disabled={!alumnos.length || saving}
                  >
                    Marcar todos AUSENTES
                  </Button>
                  <Button
                    className="h-10"
                    onClick={guardar}
                    disabled={saving || !alumnos.length}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    {saving ? "Guardando..." : "Guardar asistencia"}
                  </Button>
                </div>
              </div>
            </div>

            {/* Mensajes de estado */}
            <div className="mt-4">
              {errMsg && <p className="mb-2 text-sm text-red-600">{errMsg}</p>}
              {okMsg && <p className="mb-2 text-sm text-green-700">{okMsg}</p>}
              {!loadingCursos && cursos.length === 0 && (
                <p className="text-gray-600">No tenés cursos asignados.</p>
              )}
            </div>

            {/* Tabla de alumnos */}
            <div className="mt-6 overflow-x-auto">
              {loadingAlumnos ? (
                <p className="text-gray-600">Cargando alumnos…</p>
              ) : !alumnos.length ? (
                <p className="text-gray-600">No hay alumnos para este curso.</p>
              ) : (
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="text-gray-600">
                      <th className="text-left py-2 px-2">Alumno</th>
                      <th className="text-center py-2 px-2">PRESENTE</th>
                      <th className="text-center py-2 px-2">AUSENTE</th>
                      <th className="text-center py-2 px-2">TARDE</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {alumnos.map((a) => {
                      const pk = a?.id ?? a?.pk
                      const code = a?.id_alumno ?? a?.codigo
                      const key = pk != null ? String(pk) : String(code)
                      const nombre =
                        [a?.apellido, a?.nombre].filter(Boolean).join(", ") ||
                        a?.nombre ||
                        `Alumno ${key}`

                      const estado = marcas[key] || "presente"
                      const checkedP = estado === "presente"
                      const checkedT = estado === "tarde"
                      const checkedA = estado === "ausente"

                      return (
                        <tr key={key} className="hover:bg-gray-50">
                          <td className="py-3 px-2">
                            <div className="text-gray-900">{nombre}</div>
                            <div className="text-xs text-gray-500">
                              {cursoSel} — {fecha} — {tipoAsistencia}
                            </div>
                          </td>
                          <td className="py-3 px-2 text-center">
                            <label className="inline-flex items-center gap-2 cursor-pointer">
                              <input
                                type="radio"
                                name={`asist_${key}`}
                                className="h-5 w-5 accent-blue-600"
                                checked={checkedP}
                                disabled={saving}
                                onChange={() => setMarcas((m) => ({ ...m, [key]: "presente" }))}
                              />
                            </label>
                          </td>
                          <td className="py-3 px-2 text-center">
                            <label className="inline-flex items-center gap-2 cursor-pointer">
                              <input
                                type="radio"
                                name={`asist_${key}`}
                                className="h-5 w-5 accent-blue-600"
                                checked={checkedA}
                                disabled={saving}
                                onChange={() => setMarcas((m) => ({ ...m, [key]: "ausente" }))}
                              />
                            </label>
                          </td>
                          <td className="py-3 px-2 text-center">
                            <label className="inline-flex items-center gap-2 cursor-pointer">
                              <input
                                type="radio"
                                name={`asist_${key}`}
                                className="h-5 w-5 accent-blue-600"
                                checked={checkedT}
                                disabled={saving}
                                onChange={() => setMarcas((m) => ({ ...m, [key]: "tarde" }))}
                              />
                            </label>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
