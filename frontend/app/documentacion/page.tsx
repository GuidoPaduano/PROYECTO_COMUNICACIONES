// @ts-nocheck
"use client"

import { useEffect, useState } from "react"
import { FileText, Upload, CheckCircle, Clock, Trash2, Eye, X } from "lucide-react"
import { useAuthGuard, authFetch, useSessionContext } from "../_lib/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"

const TIPO_LABELS = {
  autorizacion: "Autorización",
  normas: "Normas de convivencia",
  circular: "Circular",
  otro: "Otro",
}

const TIPO_COLORS = {
  autorizacion: "#2563eb",
  normas: "#16a34a",
  circular: "#d97706",
  otro: "#6b7280",
}

function TipoBadge({ tipo }) {
  return (
    <span style={{
      display: "inline-block", fontSize: "11px", fontWeight: 600,
      padding: "2px 8px", borderRadius: "9999px",
      background: TIPO_COLORS[tipo] + "18", color: TIPO_COLORS[tipo],
      border: `1px solid ${TIPO_COLORS[tipo]}40`,
    }}>
      {TIPO_LABELS[tipo] || tipo}
    </span>
  )
}

function CursoBadge({ name }) {
  if (!name) return (
    <span style={{
      display: "inline-block", fontSize: "11px", fontWeight: 500,
      padding: "2px 8px", borderRadius: "9999px",
      background: "#f1f5f9", color: "#64748b",
      border: "1px solid #e2e8f0",
    }}>Toda la institución</span>
  )
  return (
    <span style={{
      display: "inline-block", fontSize: "11px", fontWeight: 600,
      padding: "2px 8px", borderRadius: "9999px",
      background: "#ede9fe", color: "#7c3aed",
      border: "1px solid #c4b5fd",
    }}>{name}</span>
  )
}

export default function DocumentacionPage() {
  useAuthGuard()

  const sessionContext = useSessionContext()
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  // Visor PDF
  const [pdfDoc, setPdfDoc] = useState(null)

  // Cursos disponibles (para el selector al subir)
  const [cursos, setCursos] = useState([])

  // Subir documento
  const [openUpload, setOpenUpload] = useState(false)
  const [uploadForm, setUploadForm] = useState({
    titulo: "", descripcion: "", tipo: "otro",
    requiere_firma: true, school_course_id: "",
  })
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadErr, setUploadErr] = useState("")
  const [uploading, setUploading] = useState(false)

  // Firmas
  const [firmasDoc, setFirmasDoc] = useState(null)
  const [firmas, setFirmas] = useState(null)
  const [loadingFirmas, setLoadingFirmas] = useState(false)

  // Signing
  const [signing, setSigning] = useState(null)

  const groups = Array.isArray(sessionContext?.groups) ? sessionContext.groups : []
  const canUpload =
    !!sessionContext?.isSuperuser ||
    groups.some((g) => ["Directivos", "Preceptores", "Administradores"].includes(g))

  async function loadDocs() {
    setLoading(true)
    setError("")
    try {
      const r = await authFetch("/api/documentos/")
      const j = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(j?.detail || "Error al cargar documentos.")
      setDocs(j.documentos || [])
    } catch (e) {
      setError(e?.message || "Error al cargar documentos.")
    } finally {
      setLoading(false)
    }
  }

  async function loadCursos() {
    try {
      const r = await authFetch("/api/alumnos/cursos/")
      const j = await r.json().catch(() => ({}))
      const lista = Array.isArray(j?.cursos) ? j.cursos : Array.isArray(j) ? j : []
      setCursos(lista)
    } catch {}
  }

  useEffect(() => {
    loadDocs()
    if (canUpload) loadCursos()
  }, [canUpload])

  async function handleFirmar(doc) {
    setSigning(doc.id)
    try {
      const r = await authFetch(`/api/documentos/${doc.id}/firmar/`, { method: "POST" })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(j?.detail || "Error al firmar.")
      setDocs((prev) => prev.map((d) => d.id === doc.id ? { ...d, firmado: true } : d))
    } catch (e) {
      alert(e?.message || "Error al firmar.")
    } finally {
      setSigning(null)
    }
  }

  async function handleEliminar(doc) {
    if (!confirm(`¿Eliminar "${doc.titulo}"?`)) return
    try {
      const r = await authFetch(`/api/documentos/${doc.id}/`, { method: "DELETE" })
      if (!r.ok) throw new Error("No se pudo eliminar.")
      setDocs((prev) => prev.filter((d) => d.id !== doc.id))
    } catch (e) {
      alert(e?.message || "Error al eliminar.")
    }
  }

  async function handleVerFirmas(doc) {
    setFirmasDoc(doc)
    setFirmas(null)
    setLoadingFirmas(true)
    try {
      const r = await authFetch(`/api/documentos/${doc.id}/firmas/`)
      const j = await r.json().catch(() => ({}))
      setFirmas(j)
    } catch {
      setFirmas({ firmas: [], total_firmas: 0 })
    } finally {
      setLoadingFirmas(false)
    }
  }

  async function handleUpload(e) {
    e.preventDefault()
    if (!uploadFile) return setUploadErr("Seleccioná un archivo PDF.")
    if (!uploadForm.titulo.trim()) return setUploadErr("El título es requerido.")
    setUploadErr("")
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append("titulo", uploadForm.titulo.trim())
      fd.append("descripcion", uploadForm.descripcion.trim())
      fd.append("tipo", uploadForm.tipo)
      fd.append("requiere_firma", uploadForm.requiere_firma ? "true" : "false")
      if (uploadForm.school_course_id) fd.append("school_course_id", uploadForm.school_course_id)
      fd.append("archivo", uploadFile)

      const r = await authFetch("/api/documentos/", { method: "POST", body: fd })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(j?.detail || "Error al subir el documento.")
      setDocs((prev) => [j, ...prev])
      setOpenUpload(false)
      setUploadForm({ titulo: "", descripcion: "", tipo: "otro", requiere_firma: true, school_course_id: "" })
      setUploadFile(null)
    } catch (e) {
      setUploadErr(e?.message || "Error al subir el documento.")
    } finally {
      setUploading(false)
    }
  }

  // Helper para obtener el nombre del curso de la lista
  function getCursoNombre(c) {
    return c?.name || c?.nombre || c?.code || c?.codigo || String(c?.id || "")
  }
  function getCursoId(c) {
    return c?.school_course_id ?? c?.id ?? ""
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 16px" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "#0f172a", margin: 0 }}>Documentación</h1>
          <p style={{ fontSize: "0.875rem", color: "#64748b", marginTop: 4 }}>
            Autorizaciones, normas de convivencia y circulares del colegio.
          </p>
        </div>
        {canUpload && (
          <Button onClick={() => setOpenUpload(true)} className="gap-2">
            <Upload className="w-4 h-4" />
            Subir documento
          </Button>
        )}
      </div>

      {/* Lista */}
      {loading && (
        <div style={{ textAlign: "center", padding: 40, color: "#64748b" }}>Cargando documentos…</div>
      )}
      {error && (
        <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "12px 16px", color: "#dc2626", marginBottom: 16 }}>
          {error}
        </div>
      )}
      {!loading && !error && docs.length === 0 && (
        <div style={{ textAlign: "center", padding: 60, color: "#94a3b8" }}>
          <FileText style={{ width: 48, height: 48, margin: "0 auto 12px", opacity: 0.3 }} />
          <p style={{ margin: 0 }}>No hay documentos publicados todavía.</p>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {docs.map((doc) => (
          <div
            key={doc.id}
            style={{
              background: "white", border: "1px solid #e2e8f0", borderRadius: 10,
              padding: "16px 20px", display: "flex", alignItems: "flex-start",
              gap: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
            }}
          >
            <div style={{ flexShrink: 0, width: 40, height: 40, background: "#f1f5f9", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <FileText style={{ width: 20, height: 20, color: "#475569" }} />
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span style={{ fontWeight: 600, color: "#0f172a", fontSize: "0.9375rem" }}>{doc.titulo}</span>
                <TipoBadge tipo={doc.tipo} />
                <CursoBadge name={doc.school_course_name} />
                {doc.requiere_firma && (
                  doc.firmado
                    ? <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "#16a34a", fontWeight: 500 }}><CheckCircle style={{ width: 14, height: 14 }} />Firmado</span>
                    : <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "#d97706", fontWeight: 500 }}><Clock style={{ width: 14, height: 14 }} />Pendiente de firma</span>
                )}
              </div>
              {doc.descripcion && (
                <p style={{ fontSize: "0.8125rem", color: "#64748b", margin: "4px 0 0", lineHeight: 1.5 }}>{doc.descripcion}</p>
              )}
              <p style={{ fontSize: "0.75rem", color: "#94a3b8", margin: "6px 0 0" }}>
                Subido por {doc.subido_por || "—"} · {new Date(doc.creado_en).toLocaleDateString("es-AR", { day: "2-digit", month: "short", year: "numeric" })}
                {canUpload && doc.requiere_firma && ` · ${doc.total_firmas} firma${doc.total_firmas !== 1 ? "s" : ""}`}
              </p>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
              <Button size="sm" onClick={() => setPdfDoc({ ...doc, proxy_url: `/api/documentos/${doc.id}/archivo/` })} className="gap-1" style={{ fontSize: 13 }}>
                <Eye className="w-3.5 h-3.5" />Ver
              </Button>
              {doc.requiere_firma && !doc.firmado && (
                <Button size="sm" onClick={() => handleFirmar(doc)} disabled={signing === doc.id}
                  style={{ fontSize: 13, background: "#16a34a", color: "white" }}>
                  {signing === doc.id ? "Firmando…" : "Firmar"}
                </Button>
              )}
              {canUpload && (
                <>
                  <Button size="sm" onClick={() => handleVerFirmas(doc)}
                    style={{ fontSize: 13, background: "transparent", border: "1px solid #cbd5e1", color: "#475569" }}>
                    Firmas
                  </Button>
                  <button onClick={() => handleEliminar(doc)} title="Eliminar"
                    style={{ background: "none", border: "none", cursor: "pointer", color: "#ef4444", padding: 6, borderRadius: 6, display: "flex", alignItems: "center" }}>
                    <Trash2 style={{ width: 16, height: 16 }} />
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ── Visor PDF ── */}
      {pdfDoc && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 50, display: "flex", flexDirection: "column" }}
          onClick={(e) => { if (e.target === e.currentTarget) setPdfDoc(null) }}>
          <div style={{ background: "#1e293b", padding: "10px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexShrink: 0 }}>
            <span style={{ color: "white", fontWeight: 600, fontSize: "0.9375rem", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pdfDoc.titulo}</span>
            <a
              href={pdfDoc.proxy_url || pdfDoc.archivo_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#94a3b8", textDecoration: "none", whiteSpace: "nowrap", padding: "4px 10px", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 6, background: "rgba(255,255,255,0.06)" }}
            >
              <Eye style={{ width: 14, height: 14 }} />
              Abrir en nueva pestaña
            </a>
            <button onClick={() => setPdfDoc(null)} style={{ background: "none", border: "none", cursor: "pointer", color: "white", display: "flex", alignItems: "center", padding: 4 }}>
              <X style={{ width: 20, height: 20 }} />
            </button>
          </div>
          <div style={{ flex: 1, position: "relative", background: "#0f172a" }}>
            <embed
              src={(pdfDoc.proxy_url || pdfDoc.archivo_url) + "#toolbar=1&navpanes=0"}
              type="application/pdf"
              style={{ width: "100%", height: "100%", border: "none" }}
            />
            {/* Fallback visible si embed no carga */}
            <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, color: "#64748b", zIndex: -1 }}>
              <FileText style={{ width: 48, height: 48, opacity: 0.3 }} />
              <p style={{ margin: 0, fontSize: 14 }}>El PDF no se puede mostrar en el navegador.</p>
              <a
                href={pdfDoc.proxy_url || pdfDoc.archivo_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontSize: 14, color: "#3b82f6", textDecoration: "underline" }}
              >
                Hacé clic aquí para abrirlo
              </a>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal subir documento ── */}
      <Dialog open={openUpload} onOpenChange={setOpenUpload}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Subir documento</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleUpload} className="space-y-4">
            {uploadErr && (
              <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "8px 12px", color: "#dc2626", fontSize: 13 }}>
                {uploadErr}
              </div>
            )}

            <div>
              <Label htmlFor="titulo">Título</Label>
              <Input id="titulo" className="mt-1" value={uploadForm.titulo}
                onChange={(e) => setUploadForm((f) => ({ ...f, titulo: e.target.value }))} required />
            </div>

            <div>
              <Label htmlFor="descripcion">Descripción (opcional)</Label>
              <Input id="descripcion" className="mt-1" value={uploadForm.descripcion}
                onChange={(e) => setUploadForm((f) => ({ ...f, descripcion: e.target.value }))} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="tipo">Tipo</Label>
                <select id="tipo" className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                  value={uploadForm.tipo} onChange={(e) => setUploadForm((f) => ({ ...f, tipo: e.target.value }))}>
                  <option value="autorizacion">Autorización</option>
                  <option value="normas">Normas de convivencia</option>
                  <option value="circular">Circular</option>
                  <option value="otro">Otro</option>
                </select>
              </div>

              <div>
                <Label htmlFor="curso">Curso</Label>
                <select id="curso" className="mt-1 w-full border rounded-md px-3 py-2 text-sm bg-white"
                  value={uploadForm.school_course_id}
                  onChange={(e) => setUploadForm((f) => ({ ...f, school_course_id: e.target.value }))}>
                  <option value="">Toda la institución</option>
                  {cursos.map((c) => (
                    <option key={getCursoId(c)} value={getCursoId(c)}>
                      {getCursoNombre(c)}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" id="requiere_firma" checked={uploadForm.requiere_firma}
                onChange={(e) => setUploadForm((f) => ({ ...f, requiere_firma: e.target.checked }))}
                style={{ width: 16, height: 16, cursor: "pointer" }} />
              <Label htmlFor="requiere_firma" style={{ cursor: "pointer", margin: 0 }}>Requiere firma digital</Label>
            </div>

            <div>
              <Label htmlFor="archivo">Archivo PDF</Label>
              <input id="archivo" type="file" accept=".pdf"
                className="mt-1 block w-full text-sm text-gray-600 file:mr-4 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)} required />
            </div>

            <DialogFooter>
              <Button type="button" onClick={() => setOpenUpload(false)} disabled={uploading}>Cancelar</Button>
              <Button type="submit" disabled={uploading}>{uploading ? "Subiendo…" : "Subir"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Modal ver firmas ── */}
      <Dialog open={!!firmasDoc} onOpenChange={(v) => { if (!v) { setFirmasDoc(null); setFirmas(null) } }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Firmas — {firmasDoc?.titulo}</DialogTitle>
          </DialogHeader>
          {loadingFirmas && <div style={{ textAlign: "center", padding: 20, color: "#64748b" }}>Cargando…</div>}
          {firmas && (
            <div>
              <p style={{ fontSize: "0.875rem", color: "#64748b", marginBottom: 12 }}>
                {firmas.total_firmas} firma{firmas.total_firmas !== 1 ? "s" : ""} registrada{firmas.total_firmas !== 1 ? "s" : ""}
              </p>
              {firmas.firmas?.length === 0 ? (
                <p style={{ color: "#94a3b8", textAlign: "center", padding: 20 }}>Nadie ha firmado todavía.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 320, overflowY: "auto" }}>
                  {firmas.firmas.map((f) => (
                    <div key={f.usuario_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
                      <div>
                        <div style={{ fontWeight: 500, fontSize: "0.875rem", color: "#0f172a" }}>{f.nombre}</div>
                        <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{f.email}</div>
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "#94a3b8", textAlign: "right" }}>
                        {new Date(f.fecha_firma).toLocaleDateString("es-AR", { day: "2-digit", month: "short", year: "numeric" })}
                        <br />
                        {new Date(f.fecha_firma).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

    </div>
  )
}
