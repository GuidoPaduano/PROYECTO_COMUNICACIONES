"use client"

import Link from "next/link"
import { useEffect, useMemo, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useAuthGuard, authFetch } from "../_lib/auth"

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import {
  ChevronLeft,
  Mail,
  Users as UsersIcon,
  RefreshCw,
  Loader2,
} from "lucide-react"

import { NotificationBell } from "@/components/notification-bell"
import { useUnreadCount } from "../_lib/useUnreadCount"

const LOGO_SRC = "/imagenes/Santa%20teresa%20logo.png"

/* ===== Constantes ===== */
const ALL = "__ALL__"
const DEFAULT_CUATRI = ["1", "2"]

/* ======================== Helpers ======================== */
async function fetchJSON(url, opts) {
  const res = await authFetch(url, {
    ...opts,
    headers: { Accept: "application/json", ...(opts?.headers || {}) },
  })
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, data, status: res.status }
}

function prettyDate(iso) {
  if (!iso) return ""
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString()
}

function getQueryFromLocation() {
  if (typeof window === "undefined") return {}
  const sp = new URLSearchParams(window.location.search)
  return {
    alumno: sp.get("alumno") || "",
    materia: sp.get("materia") || "",
    cuatrimestre: sp.get("cuatrimestre") || "",
  }
}

function setQueryInLocation(router, { alumno, materia, cuatrimestre }) {
  const sp = new URLSearchParams()
  if (alumno) sp.set("alumno", alumno)
  if (materia) sp.set("materia", materia)
  if (cuatrimestre) sp.set("cuatrimestre", cuatrimestre)
  const qs = sp.toString()
  router.replace(qs ? `/historial_notas?${qs}` : `/historial_notas`)
}

/* ======================== Page ======================== */
export default function HistorialNotasPadrePage() {
  useAuthGuard()
  const router = useRouter()

  // whoami
  const [me, setMe] = useState(null)

  // hijos + selección
  const [hijos, setHijos] = useState([])
  const [loadingHijos, setLoadingHijos] = useState(true)
  const [selectedId, setSelectedId] = useState("")

  // notas + catálogos
  const [alumno, setAlumno] = useState(null)
  const [notas, setNotas] = useState([])
  const [materiasOptions, setMateriasOptions] = useState([])
  const [cuatrimestresOptions, setCuatrimestresOptions] = useState([])

  // loading flags
  const [loadingNotas, setLoadingNotas] = useState(false)
  const [hardLoading, setHardLoading] = useState(true)

  // filtros (desde QS)
  const initQS = getQueryFromLocation()
  const [materiaFilter, setMateriaFilter] = useState(initQS.materia || "")
  const [cuatriFilter, setCuatriFilter] = useState(initQS.cuatrimestre || "")

  // contador centralizado de no leídos
  const unreadCount = useUnreadCount()

  const pushFiltersToUrl = useCallback(
    (kid, materia, cuatri) => {
      setQueryInLocation(router, { alumno: kid, materia, cuatrimestre: cuatri })
    },
    [router]
  )

  const clearFilters = () => {
    setMateriaFilter("")
    setCuatriFilter("")
    pushFiltersToUrl(selectedId, "", "")
    fetchNotas(selectedId, "", "")
  }

  /* -------- Carga inicial -------- */
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [who, hijosRes] = await Promise.all([
          fetchJSON("/auth/whoami/"),
          fetchJSON("/padres/mis-hijos/"),
        ])
        if (!alive) return

        if (who.ok) setMe(who.data || null)

        const arr = hijosRes.ok ? (hijosRes.data?.results || []) : []
        setHijos(arr)

        // Respetar ?alumno= si coincide; si no, tomar primero
        const alumnoQS = initQS.alumno
        const first = arr[0]?.id_alumno ?? ""
        const initialId =
          alumnoQS && arr.some((h) => String(h.id_alumno) === String(alumnoQS))
            ? alumnoQS
            : first

        setSelectedId(initialId)
        if (initialId) await fetchNotas(initialId, materiaFilter, cuatriFilter)

        // mantener el QS sincronizado
        pushFiltersToUrl(initialId, materiaFilter, cuatriFilter)
      } finally {
        if (alive) {
          setLoadingHijos(false)
          setHardLoading(false)
        }
      }
    })()

    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* -------- Fetch de notas (server-side) -------- */
  const fetchNotas = useCallback(async (id, materia, cuatri) => {
    if (!id) {
      setAlumno(null)
      setNotas([])
      setMateriasOptions([])
      setCuatrimestresOptions([])
      return
    }
    setLoadingNotas(true)
    try {
      const qs = new URLSearchParams()
      if (materia) qs.set("materia", materia)
      if (cuatri) qs.set("cuatrimestre", cuatri)

      const url = qs.toString()
        ? `/padres/hijos/${id}/notas/?${qs.toString()}`
        : `/padres/hijos/${id}/notas/`

      const r = await fetchJSON(url)
      if (r.ok) {
        setAlumno(r.data?.alumno || null)
        setNotas(Array.isArray(r.data?.results) ? r.data.results : [])
        setMateriasOptions(Array.isArray(r.data?.materias) ? r.data.materias : [])
        setCuatrimestresOptions(Array.isArray(r.data?.cuatrimestres) ? r.data.cuatrimestres : [])
      } else {
        setAlumno(null)
        setNotas([])
        setMateriasOptions([])
        setCuatrimestresOptions([])
      }
    } finally {
      setLoadingNotas(false)
    }
  }, [])

  // Cambia alumno
  useEffect(() => {
    if (!selectedId) return
    pushFiltersToUrl(selectedId, materiaFilter, cuatriFilter)
    fetchNotas(selectedId, materiaFilter, cuatriFilter)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  /* ====== Opciones saneadas (sin null/empty) ====== */
  const safeMaterias = useMemo(
    () =>
      Array.from(
        new Set((materiasOptions || []).map(String).filter((v) => v && v.trim() !== ""))
      ),
    [materiasOptions]
  )

  // Unimos lo que venga del backend con ["1","2"] y ordenamos natural
  const safeCuatrimestres = useMemo(() => {
    const merged = new Set([
      ...DEFAULT_CUATRI,
      ...((cuatrimestresOptions || []).map(String)),
    ].filter((v) => v && v.trim() !== ""))
    const arr = Array.from(merged)
    return arr.sort((a, b) => {
      const na = Number(a),
        nb = Number(b)
      const aNum = !Number.isNaN(na),
        bNum = !Number.isNaN(nb)
      if (aNum && bNum) return na - nb
      if (aNum) return -1
      if (bNum) return 1
      return a.localeCompare(b)
    })
  }, [cuatrimestresOptions])

  // Cambios de filtros — mapear token ALL -> ""
  const onMateriaChange = (v) => {
    const real = v === ALL ? "" : v
    setMateriaFilter(real)
    pushFiltersToUrl(selectedId, real, cuatriFilter)
    fetchNotas(selectedId, real, cuatriFilter)
  }
  const onCuatriChange = (v) => {
    const real = v === ALL ? "" : v
    setCuatriFilter(real)
    pushFiltersToUrl(selectedId, materiaFilter, real)
    fetchNotas(selectedId, materiaFilter, real)
  }

  const hayHijos = (hijos?.length || 0) > 0
  const hardOrNotesLoading = hardLoading || loadingNotas

  /* -------- Render -------- */
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-25 to-white">
      {/* Topbar unificado con campanita y mail */}
      <Topbar unreadCount={unreadCount} me={me} />

      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Toolbar */}
        <Card className="border-0 shadow-sm bg-white/90 backdrop-blur-sm">
          <CardContent className="p-4 md:p-5">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3 md:gap-4">
              {/* Hijo */}
              <div className="col-span-1">
                <label className="block text-sm mb-1">Elegí el hijo/a</label>
                <Select
                  value={selectedId}
                  onValueChange={(v) => setSelectedId(v)}
                  disabled={loadingHijos || !hayHijos}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue
                      placeholder={
                        loadingHijos
                          ? "Cargando..."
                          : hayHijos
                          ? "Seleccionar"
                          : "Sin hijos vinculados"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {hijos.map((h) => (
                      <SelectItem key={h.id_alumno} value={h.id_alumno}>
                        {[h.apellido, h.nombre].filter(Boolean).join(", ") ||
                          h.nombre ||
                          h.id_alumno}
                        {h.curso ? ` — ${h.curso}` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Materia */}
              <div className="col-span-1">
                <label className="block text-sm mb-1">Materia</label>
                <Select
                  value={materiaFilter || ALL}
                  onValueChange={onMateriaChange}
                  disabled={hardOrNotesLoading}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Todas" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>Todas</SelectItem>
                    {safeMaterias.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Cuatrimestre */}
              <div className="col-span-1">
                <label className="block text-sm mb-1">Cuatrimestre</label>
                <Select
                  value={cuatriFilter || ALL}
                  onValueChange={onCuatriChange}
                  disabled={hardOrNotesLoading}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Todos" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>Todos</SelectItem>
                    {safeCuatrimestres.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Acciones */}
              <div className="col-span-2 flex items-end justify-start md:justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="gap-2"
                  onClick={() => fetchNotas(selectedId, materiaFilter, cuatriFilter)}
                  disabled={!selectedId || loadingNotas}
                >
                  {loadingNotas ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Actualizando…
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-4 w-4" />
                      Refrescar
                    </>
                  )}
                </Button>
                <Button type="button" variant="ghost" onClick={clearFilters}>
                  Limpiar filtros
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tabla */}
        <Card className="border-0 shadow-sm bg-white/90 backdrop-blur-sm">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-32">Fecha</TableHead>
                    <TableHead>Materia</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="w-40">Calificación</TableHead>
                    <TableHead className="w-36">Cuatrimestre</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {hardOrNotesLoading ? (
                    Array.from({ length: 6 }).map((_, i) => (
                      <TableRow key={`sk-${i}`}>
                        <TableCell>
                          <div className="h-4 w-20 bg-muted rounded animate-pulse" />
                        </TableCell>
                        <TableCell>
                          <div className="h-4 w-40 bg-muted rounded animate-pulse" />
                        </TableCell>
                        <TableCell>
                          <div className="h-4 w-24 bg-muted rounded animate-pulse" />
                        </TableCell>
                        <TableCell>
                          <div className="h-4 w-16 bg-muted rounded animate-pulse" />
                        </TableCell>
                        <TableCell>
                          <div className="h-4 w-16 bg-muted rounded animate-pulse" />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (notas?.length ?? 0) > 0 ? (
                    notas.map((n) => (
                      <TableRow key={n.id} className="transition-colors">
                        <TableCell className="whitespace-nowrap">
                          {prettyDate(n.fecha)}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">{n.materia}</TableCell>
                        <TableCell className="capitalize whitespace-nowrap">
                          {n.tipo}
                        </TableCell>
                        <TableCell className="font-medium whitespace-nowrap">
                          {n.calificacion_display || n.calificacion}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          {n.cuatrimestre}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell
                        colSpan={5}
                        className="py-10 text-center text-sm text-muted-foreground"
                      >
                        No hay resultados que coincidan con los filtros.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

/* ======================== Topbar ======================== */
function Topbar({ unreadCount, me }) {
  const userLabel =
    (me?.full_name && String(me.full_name).trim()) ||
    me?.username ||
    [me?.user?.first_name, me?.user?.last_name].filter(Boolean).join(" ") ||
    "Usuario"

  return (
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
          <h1 className="text-xl font-semibold">Notas de mis hijos</h1>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/dashboard">
            <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
              <ChevronLeft className="h-4 w-4" />
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

          <Button variant="ghost" className="text-white hover:bg-blue-700 gap-2">
            <UsersIcon className="h-4 w-4" />
            {userLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
