"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, FileSpreadsheet, Upload } from "lucide-react"

import { API_BASE, authFetch, useAuthGuard, useSessionContext } from "../../../../_lib/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
  return `${summary.valid || 0} validos, ${summary.errors || 0} con error, ${summary.skipped || 0} omitidos`
}

export default function ImportarAlumnosPage() {
  useAuthGuard()
  const sessionContext = useSessionContext()
  const loading = !sessionContext
  const allowed = !!sessionContext?.isSuperuser
  const [schools, setSchools] = useState([])
  const [school, setSchool] = useState("")
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const selectedSchool = useMemo(
    () => schools.find((item) => String(item.slug || item.id) === school) || null,
    [schools, school]
  )

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const res = await fetch(`${API_BASE}/public/schools/`, {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
        })
        const data = await res.json().catch(() => ({}))
        if (!alive) return
        const items = Array.isArray(data?.schools) ? data.schools : []
        setSchools(items)
        if (!school && items.length) setSchool(String(items[0].slug || items[0].id))
      } catch {}
    })()
    return () => {
      alive = false
    }
  }, [school])

  const runImport = async ({ commit }) => {
    setError("")
    setSubmitting(true)
    try {
      if (!school) {
        setError("Selecciona un colegio.")
        return
      }
      if (!file) {
        setError("Selecciona un archivo Excel o CSV.")
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

  if (loading || !allowed) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center rounded-3xl border border-slate-200 bg-white">
        <div className="text-sm font-medium text-slate-600">Cargando herramienta de importacion...</div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <Link
          href="/admin/plataforma"
          className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver a admin plataforma
        </Link>
        <h1 className="mt-3 text-3xl font-semibold text-slate-900">Importar alumnos</h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card>
          <CardHeader>
            <CardTitle>Archivo de alumnos</CardTitle>
            <CardDescription>
              Primero previsualiza. La importacion solo crea alumnos validos y no crea usuarios ni tutores.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Colegio</Label>
                <Select value={school} onValueChange={setSchool}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecciona colegio" />
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
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            ) : null}

            <div className="flex flex-wrap gap-3">
              <Button type="button" variant="outline" disabled={submitting} onClick={() => runImport({ commit: false })}>
                <FileSpreadsheet className="mr-2 h-4 w-4" />
                {submitting ? "Procesando..." : "Previsualizar"}
              </Button>
              <Button
                type="button"
                disabled={submitting || !result?.summary || result?.summary?.errors > 0 || result?.summary?.valid < 1}
                onClick={() => runImport({ commit: true })}
              >
                <Upload className="mr-2 h-4 w-4" />
                Confirmar importacion
              </Button>
            </div>

            {result?.summary ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                {selectedSchool ? `${selectedSchool.name}: ` : ""}
                {formatSummary(result.summary)}
                {result.summary.created ? `, ${result.summary.created} creados` : ""}
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

        <Card>
          <CardHeader>
            <CardTitle>Columnas esperadas</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
            <p>Usa encabezados simples. La herramienta reconoce:</p>
            <p><span className="font-medium text-slate-900">nombre</span>, <span className="font-medium text-slate-900">apellido</span>, <span className="font-medium text-slate-900">legajo</span> o <span className="font-medium text-slate-900">id_alumno</span>, y <span className="font-medium text-slate-900">curso</span>.</p>
            <p>El curso debe existir en el colegio elegido: 1A, 1B, 2A, 2B, 3A, 3B, 4ECO, 4NAT, 5ECO, 5NAT, 6ECO o 6NAT.</p>
            <p>Si el legajo viene vacio, se genera automaticamente por curso.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
