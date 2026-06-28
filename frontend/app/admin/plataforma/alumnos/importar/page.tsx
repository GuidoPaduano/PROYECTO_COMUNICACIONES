// @ts-nocheck
"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, Download, FileSpreadsheet, Upload } from "lucide-react"

import { authFetch, buildApiUrl, normalizeSchool, useAuthGuard, useSessionContext } from "../../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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

function formatSummary(summary) {
  if (!summary) return "Sin previsualizacion"
  const coursesText = summary.courses_to_create ? `, ${summary.courses_to_create} cursos nuevos` : ""
  return `${summary.valid || 0} válidos, ${summary.errors || 0} con error, ${summary.skipped || 0} omitidos${coursesText}`
}

function schoolValue(item) {
  return String(item?.slug || item?.id || "").trim()
}

function mergeSchools(...groups) {
  const merged = []
  const seen = new Set()
  for (const group of groups) {
    for (const rawItem of Array.isArray(group) ? group : []) {
      const item = normalizeSchool(rawItem)
      const value = schoolValue(item)
      if (!value || seen.has(value)) continue
      seen.add(value)
      merged.push(item)
    }
  }
  return merged
}

export default function ImportarAlumnosPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loadingSession = !sessionContext
  const allowed = !!sessionContext?.isSuperuser
  const [schools, setSchools] = useState([])
  const [school, setSchool] = useState("")
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const sessionSchool = useMemo(() => normalizeSchool(sessionContext?.school), [sessionContext?.school])
  const sessionSchools = useMemo(
    () => mergeSchools(sessionContext?.availableSchools, sessionSchool ? [sessionSchool] : []),
    [sessionContext?.availableSchools, sessionSchool]
  )
  const sessionSchoolValue = schoolValue(sessionSchool)

  const selectedSchool = useMemo(
    () => schools.find((item) => String(item.slug || item.id) === school) || null,
    [schools, school]
  )
  const importCount = Number(result?.summary?.valid || 0)
  const coursesToCreateCount = Number(result?.summary?.courses_to_create || result?.courses_to_create?.length || 0)
  const canImport = !!result?.summary && result.summary.errors <= 0 && importCount > 0

  useEffect(() => {
    if (sessionSchools.length) {
      setSchools((current) => mergeSchools(sessionSchools, current))
    }
    if (!school && sessionSchoolValue) {
      setSchool(sessionSchoolValue)
    }
  }, [school, sessionSchoolValue, sessionSchools])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const res = await fetch(buildApiUrl("/public/schools/"), {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        })
        const data = await res.json().catch(() => ({}))
        if (!alive) return
        const items = Array.isArray(data?.schools) ? data.schools : []
        setSchools((current) => mergeSchools(current, items))
        if (!school && !sessionSchoolValue && items.length) setSchool(schoolValue(items[0]))
      } catch {}
    })()
    return () => {
      alive = false
    }
  }, [school, sessionSchoolValue])

  const runImport = async ({ commit }) => {
    setError("")
    setSubmitting(true)
    try {
      if (!school) {
        setError("Seleccioná un colegio.")
        return
      }
      if (!file) {
        setError("Seleccioná un archivo Excel o CSV.")
        return
      }

      const formData = new FormData()
      formData.append("school", school)
      formData.append("file", file)
      if (commit) formData.append("commit", "true")

      const res = await authFetch("/admin/alumnos/import/", {
        method: "POST",
        body: formData,
        headers: school ? { "X-School": school } : undefined,
      })
      const data = await res.json().catch(() => ({}))
      setResult(data)
      if (!res.ok) {
        setError(data?.detail || "No se pudo procesar el archivo.")
      }
    } catch {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setSubmitting(false)
    }
  }

  const openImportConfirmation = () => {
    if (!canImport) return
    setConfirmOpen(true)
  }

  const confirmImport = async () => {
    setConfirmOpen(false)
    await runImport({ commit: true })
  }

  const downloadTemplate = async () => {
    setError("")
    try {
      const res = await authFetch("/admin/alumnos/import/template/", {
        method: "GET",
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data?.detail || "No se pudo descargar la plantilla.")
        return
      }
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = "plantilla-importacion-alumnos.xlsx"
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch {
      setError("No se pudo conectar con el servidor.")
    }
  }

  if (loadingSession) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de importación...</div>
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
    <div className="mx-auto max-w-6xl space-y-6 min-w-0">
      <div>
        <Link
          href="/admin/plataforma"
          className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver a admin plataforma
        </Link>
        <h2 className="mt-3 text-3xl font-semibold text-slate-900">Importar alumnos</h2>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Archivo de alumnos</CardTitle>
            <CardDescription>
              Primero previsualizá. La importación solo crea alumnos válidos y no crea usuarios ni tutores.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Colegio</Label>
                <Select value={school} onValueChange={setSchool}>
                  <SelectTrigger aria-label="Colegio">
                    <SelectValue placeholder="Seleccioná colegio" />
                  </SelectTrigger>
                  <SelectContent>
                    {schools.map((item) => (
                      <SelectItem key={item.slug || item.id} value={String(item.slug || item.id)}>
                        {item.short_name || item.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="students-file">Excel o CSV</Label>
                <Input
                  id="students-file"
                  type="file"
                  accept=".xlsx,.csv"
                  onChange={(event) => {
                    setFile(event.target.files?.[0] || null)
                    setResult(null)
                    setError("")
                  }}
                />
              </div>
            </div>

            {error ? (
              <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            ) : null}

            <div className="flex flex-wrap gap-3">
              <Button type="button" variant="outline" disabled={submitting} onClick={downloadTemplate}>
                <Download className="mr-2 h-4 w-4" />
                Descargar plantilla
              </Button>
              <Button type="button" variant="outline" disabled={submitting} onClick={() => runImport({ commit: false })}>
                <FileSpreadsheet className="mr-2 h-4 w-4" />
                {submitting ? "Procesando..." : "Previsualizar"}
              </Button>
              <Button
                type="button"
                disabled={submitting || !canImport}
                onClick={openImportConfirmation}
              >
                <Upload className="mr-2 h-4 w-4" />
                Importar
              </Button>
            </div>

            {result?.summary ? (
              <div role="status" aria-live="polite" className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                {selectedSchool ? `${selectedSchool.name}: ` : ""}
                {formatSummary(result.summary)}
                {result.summary.created ? `, ${result.summary.created} creados` : ""}
                {result.summary.created_courses ? `, ${result.summary.created_courses} cursos creados` : ""}
              </div>
            ) : null}

            {Array.isArray(result?.courses_to_create) && result.courses_to_create.length ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                Se crearán estos cursos al importar: {result.courses_to_create.map((item) => item.code).join(", ")}.
              </div>
            ) : null}

            {Array.isArray(result?.errors) && result.errors.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Fila</TableHead>
                    <TableHead>Alumno</TableHead>
                    <TableHead>Curso</TableHead>
                    <TableHead>Error</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.errors.map((item) => (
                    <TableRow key={`error-${item.row}`}>
                      <TableCell>{item.row}</TableCell>
                      <TableCell>{[item.apellido, item.nombre].filter(Boolean).join(", ") || item.legajo}</TableCell>
                      <TableCell>{item.curso}</TableCell>
                      <TableCell className="text-red-700">{(item.errors || []).join(" ")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}

            {Array.isArray(result?.preview) && result.preview.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Fila</TableHead>
                    <TableHead>Legajo</TableHead>
                    <TableHead>Apellido</TableHead>
                    <TableHead>Nombre</TableHead>
                    <TableHead>Curso</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.preview.map((item) => (
                    <TableRow key={`preview-${item.row}-${item.legajo}`}>
                      <TableCell>{item.row}</TableCell>
                      <TableCell>{item.legajo}</TableCell>
                      <TableCell>{item.apellido}</TableCell>
                      <TableCell>{item.nombre}</TableCell>
                      <TableCell>{item.school_course_name || item.curso}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Columnas esperadas</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
            <p>Usa encabezados simples. La herramienta reconoce:</p>
            <p><span className="font-medium text-slate-900">apellido</span> y <span className="font-medium text-slate-900">nombre</span>.</p>
            <p>La plantilla usa una hoja por curso. El nombre de la hoja será el nombre del curso y, si no existe, se crea al importar.</p>
            <p>El legajo se genera automáticamente por curso.</p>
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={confirmOpen}
        onOpenChange={(open) => {
          if (!submitting) setConfirmOpen(open)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirmar importación</DialogTitle>
            <DialogDescription>
              ¿Está seguro que desea importar {importCount} {importCount === 1 ? "alumno" : "alumnos"}?
            </DialogDescription>
          </DialogHeader>
          {coursesToCreateCount ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              También se {coursesToCreateCount === 1 ? "creará" : "crearán"} {coursesToCreateCount}{" "}
              {coursesToCreateCount === 1 ? "curso nuevo" : "cursos nuevos"}.
            </div>
          ) : null}
          {selectedSchool ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              Colegio: <span className="font-medium text-slate-900">{selectedSchool.name}</span>
            </div>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={submitting} onClick={() => setConfirmOpen(false)}>
              Cancelar
            </Button>
            <Button type="button" disabled={submitting} onClick={confirmImport}>
              <Upload className="mr-2 h-4 w-4" />
              {submitting ? "Importando..." : "Importar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}