"use client"

import { useEffect, useMemo, useState } from "react"
import { useAuthGuard, authFetch, useSessionContext } from "../_lib/auth"
import {
  getCourseLabel,
  getCourseSchoolCourseId,
  loadCourseCatalog,
  normalizeCourseList,
} from "../_lib/courses"
import { Save } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import SuccessMessage from "@/components/ui/success-message"

const ASISTENCIA_RESOURCE_MAX_AGE_MS = 10000
const asistenciaResourceCache = new Map()
const asistenciaResourcePromises = new Map()

async function fetchApi(url, opts = {}, timeoutMs = 60000) {
  const controller = new AbortController()
  const t = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await authFetch(url, { ...(opts || {}), signal: controller.signal })

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
          ? "Tiempo de espera agotado. Reintenta."
          : "Error de red.",
      },
    }
  } finally {
    clearTimeout(t)
  }
}

function invalidateAsistenciaResource(cacheKeyPrefix = "") {
  const prefix = String(cacheKeyPrefix || "").trim()
  if (!prefix) return

  for (const key of Array.from(asistenciaResourceCache.keys())) {
    if (key.startsWith(prefix)) {
      asistenciaResourceCache.delete(key)
    }
  }

  for (const key of Array.from(asistenciaResourcePromises.keys())) {
    if (key.startsWith(prefix)) {
      asistenciaResourcePromises.delete(key)
    }
  }
}

async function loadAsistenciaResource(
  cacheKey,
  loader,
  { force = false, maxAgeMs = ASISTENCIA_RESOURCE_MAX_AGE_MS } = {}
) {
  const key = String(cacheKey || "").trim()
  if (!key || typeof loader !== "function") {
    return await loader()
  }

  if (force) {
    invalidateAsistenciaResource(key)
  }

  const cached = asistenciaResourceCache.get(key)
  if (cached && cached.expiresAt > Date.now()) {
    return cached.data
  }

  if (asistenciaResourcePromises.has(key)) {
    return await asistenciaResourcePromises.get(key)
  }

  const promise = (async () => {
    const data = await loader()
    asistenciaResourceCache.set(key, {
      data,
      expiresAt: Date.now() + maxAgeMs,
    })
    return data
  })()

  asistenciaResourcePromises.set(key, promise)

  try {
    return await promise
  } finally {
    if (asistenciaResourcePromises.get(key) === promise) {
      asistenciaResourcePromises.delete(key)
    }
  }
}

function todayISO() {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

function normalizeCursoItem(c) {
  const [course] = normalizeCourseList([c])
  if (!course) return { value: "", text: "" }
  const code = String(course.courseCode || "").trim()
  const label = String(course.label || "").trim()
  return {
    value: course.value,
    text: code && label && code !== label ? `${code} - ${label}` : (label || code || course.value),
  }
}

export default function PasarAsistenciaPage() {
  useAuthGuard()
  const session = useSessionContext()

  const [loadingCursos, setLoadingCursos] = useState(true)
  const [cursos, setCursos] = useState([])
  const [cursoSel, setCursoSel] = useState("")

  const [fecha, setFecha] = useState(todayISO())
  const [tipoAsistencia, setTipoAsistencia] = useState("clases")

  const [loadingAlumnos, setLoadingAlumnos] = useState(false)
  const [alumnos, setAlumnos] = useState([])

  const [marcas, setMarcas] = useState({})

  const [saving, setSaving] = useState(false)
  const [okMsg, setOkMsg] = useState("")
  const [errMsg, setErrMsg] = useState("")
  const asistenciaScopeKey = useMemo(
    () => `${session?.username || "anon"}:${session?.school?.id || session?.school?.slug || "default"}`,
    [session?.school?.id, session?.school?.slug, session?.username]
  )
  const schoolCourseIdSel = useMemo(
    () => getCourseSchoolCourseId(cursoSel, cursos),
    [cursoSel, cursos]
  )

  useEffect(() => {
    let alive = true
    setLoadingCursos(true)

    ;(async () => {
      try {
        const list = await loadCourseCatalog({
          fetcher: (url) => authFetch(url),
          urls: [
            "/api/notas/catalogos/",
            "/api/preceptor/asistencias/cursos/",
            "/api/preceptor/cursos/",
            "/api/cursos/mis-cursos/",
          ],
          cacheKey: `pasar-asistencia:${session?.username || "anon"}:${session?.school?.id || session?.school?.slug || "default"}`,
        })
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
  }, [session?.school?.id, session?.school?.slug, session?.username])

  useEffect(() => {
    if (!cursoSel) return
    if (schoolCourseIdSel == null) {
      setErrMsg("No se pudo resolver el curso seleccionado.")
      setOkMsg("")
      setAlumnos([])
      setMarcas({})
      return
    }
    let alive = true
    setLoadingAlumnos(true)
    setErrMsg("")
    setOkMsg("")

    ;(async () => {
      try {
        const list = await loadAsistenciaResource(
          `pasar-asistencia-alumnos:${asistenciaScopeKey}:${schoolCourseIdSel}`,
          async () => {
            const r = await fetchApi(
              `/api/alumnos/?school_course_id=${encodeURIComponent(String(schoolCourseIdSel))}`
            )
            if (!r.ok) throw new Error(r.data?.detail || "No se pudieron cargar los alumnos.")
            return Array.isArray(r.data?.alumnos) ? r.data.alumnos : []
          }
        )
        if (!alive) return

        setAlumnos(list)

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
  }, [asistenciaScopeKey, cursoSel, schoolCourseIdSel])

  useEffect(() => {
    if (!cursoSel || !fecha) return
    if (schoolCourseIdSel == null) return
    if (!alumnos.length) return

    let alive = true
    setErrMsg("")
    setOkMsg("")

    ;(async () => {
      try {
        const params = new URLSearchParams({
          school_course_id: String(schoolCourseIdSel),
          fecha,
          tipo: tipoAsistencia,
        })
        const d2 = await loadAsistenciaResource(
          `pasar-asistencia-registro:${asistenciaScopeKey}:${params.toString()}`,
          async () => {
            const r2 = await fetchApi(
              `/api/asistencias/curso/?${params.toString()}`
            )
            if (!r2.ok) throw new Error(r2.data?.detail || "No se pudieron cargar las asistencias.")
            return r2.data || {}
          }
        )

        if (!alive) return
        const items = Array.isArray(d2?.asistencias)
          ? d2.asistencias
          : Array.isArray(d2?.items)
            ? d2.items
            : []

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
      } catch {}
    })()

    return () => {
      alive = false
    }
  }, [asistenciaScopeKey, cursoSel, schoolCourseIdSel, fecha, tipoAsistencia, alumnos])

  function marcarTodos(estado) {
    setMarcas((prev) => {
      const next = { ...prev }
      for (const k of Object.keys(next)) next[k] = estado
      return next
    })
  }

  async function guardar() {
    if (!cursoSel) return
    if (schoolCourseIdSel == null) {
      setErrMsg("No se pudo resolver el curso seleccionado.")
      return
    }
    if (!fecha) return
    if (!tipoAsistencia) return
    if (!alumnos.length) return

    setSaving(true)
    setErrMsg("")
    setOkMsg("")

    try {
      const presentes = []
      const tardes = []
      const asistenciasPayload = {}
      let needsMap = false

      for (const a of alumnos) {
        const pk = a?.id ?? a?.pk
        const code = a?.id_alumno ?? a?.codigo
        const key = pk != null ? String(pk) : String(code)
        const estado = marcas[key] || "presente"
        const isPresente = estado !== "ausente"

        if (pk != null) {
          if (isPresente) presentes.push(Number(pk))
          if (estado === "tarde") tardes.push(Number(pk))
        } else if (code != null) {
          // sin PK no podemos usar formato A
          needsMap = true
        }

        asistenciasPayload[String(key)] = estado
      }

      const r = await fetchApi(
        "/api/asistencias/registrar/",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            school_course_id: schoolCourseIdSel,
            fecha,
            tipo_asistencia: tipoAsistencia,
            tipo: tipoAsistencia,
            ...(needsMap
              ? { asistencias: asistenciasPayload }
              : { presentes, tardes }),
          }),
        },
        60000
      )

      if (!r.ok) {
        const msg = r.data?.detail || "No se pudo guardar la asistencia."
        setErrMsg(msg)
        return
      }

      invalidateAsistenciaResource(`pasar-asistencia-registro:${asistenciaScopeKey}:school_course_id=${schoolCourseIdSel}&`)
      invalidateAsistenciaResource(`pasar-asistencia-registro:${asistenciaScopeKey}:`)
      setOkMsg("Asistencia guardada.")
    } catch (e) {
      setErrMsg("Error de red al guardar la asistencia.")
    } finally {
      setSaving(false)
    }
  }

  const isToday = fecha === todayISO()

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-6">
          <div className="flex flex-col lg:flex-row gap-4 items-start lg:items-end">
            <div className="flex flex-wrap gap-4 items-end">
              <div className="flex flex-col">
                <label className="block text-sm font-medium text-gray-900">Curso</label>
                <select
                  className="mt-1 h-10 rounded-xl border border-gray-200 px-3 bg-white"
                  value={cursoSel}
                  onChange={(e) => setCursoSel(e.target.value)}
                  disabled={loadingCursos || saving}
                >
                  {loadingCursos ? (
                    <option value="">Cargando...</option>
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

              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <label className="block text-sm font-medium text-gray-900">Fecha</label>
                  {isToday && (
                    <span className="text-xs px-2 py-0.5 rounded school-primary-soft-badge">
                      Hoy
                    </span>
                  )}
                </div>
                <input
                  id="fecha"
                  type="date"
                  className={`mt-1 h-10 rounded-xl border border-gray-200 px-3 ${!isToday ? "bg-gray-50" : "bg-white"}`}
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

              <div className="flex flex-col min-w-[190px]">
                <label className="block text-sm font-medium text-gray-900">Tipo</label>
                <select
                  className="mt-1 h-10 w-full rounded-xl border border-gray-200 px-3 bg-white"
                  value={tipoAsistencia}
                  disabled={saving}
                  onChange={(e) => {
                    setTipoAsistencia(e.target.value)
                    setOkMsg("")
                    setErrMsg("")
                  }}
                >
                  <option value="clases">Clases</option>
                  <option value="informatica">Informatica</option>
                  <option value="catequesis">Catequesis</option>
                </select>
              </div>

              <div className="ml-auto flex gap-2 self-end">
                <Button
                  className="h-10"
                  onClick={() => marcarTodos("presente")}
                  disabled={!alumnos.length || saving}
                >
                  Marcar todos PRESENTES
                </Button>
                <Button
                  className="h-10"
                  onClick={() => marcarTodos("ausente")}
                  disabled={!alumnos.length || saving}
                >
                  Marcar todos AUSENTES
                </Button>
                <Button className="h-10" onClick={guardar} disabled={saving || !alumnos.length}>
                  <Save className="h-4 w-4 mr-2" />
                  {saving ? "Guardando..." : "Guardar asistencia"}
                </Button>
              </div>
            </div>
          </div>

          <div>
            {errMsg && <p className="mb-2 text-sm text-red-600">{errMsg}</p>}
            {okMsg && <SuccessMessage className="mb-3">{okMsg}</SuccessMessage>}
            {!loadingCursos && cursos.length === 0 && (
              <p className="text-gray-600">No tenes cursos asignados.</p>
            )}
          </div>

          <div className="overflow-x-auto">
            {loadingAlumnos ? (
              <p className="text-gray-600">Cargando alumnos...</p>
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
                            {(getCourseLabel(cursoSel, cursos) || cursoSel)} - {fecha} - {tipoAsistencia}
                          </div>
                        </td>
                        <td className="py-3 px-2 text-center">
                          <label className="inline-flex items-center gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name={`asist_${key}`}
                              className="h-5 w-5 school-radio"
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
                              className="h-5 w-5 school-radio"
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
                              className="h-5 w-5 school-radio"
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
  )
}

