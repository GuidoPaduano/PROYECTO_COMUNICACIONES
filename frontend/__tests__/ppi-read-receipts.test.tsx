import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import PpiDocumentCard, { PpiDocument } from "@/components/ppi-document-card"
import PpiDocuments from "@/app/alumnos/[alumnoId]/_ppi-documents"
import { authFetch } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({ authFetch: jest.fn() }))
const request = authFetch as jest.Mock
const doc: PpiDocument = { id: 1, alumno_id: 7, titulo: "Recomendaciones", nombre_archivo: "guia.pdf", tamano: 40, creado_en: "2026-10-08", subido_por: "EOE", version: 1, requiere_firma: true, puede_firmar: true }
beforeEach(() => {
  request.mockReset()
  URL.createObjectURL = jest.fn(() => 'blob:document')
  URL.revokeObjectURL = jest.fn()
})

it("consulting the PDF does not sign it; explicit confirmation is required", async () => {
  request.mockImplementation(async (_url, options) => options?.method === 'POST'
    ? { ok: true, json: async () => ({ firmado_en: '2026-10-08T12:00:00Z' }) }
    : { ok: true, blob: async () => new Blob(['%PDF']) })
  render(<PpiDocumentCard document={doc} />)
  expect(screen.getByRole('button', { name: 'Firmar lectura' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Ver PDF' }))
  const viewer = await screen.findByRole('dialog')
  expect(within(viewer).getByTitle('PDF: Recomendaciones')).toBeInTheDocument()
  expect(request).toHaveBeenCalledTimes(1)
  fireEvent.click(within(viewer).getByRole('button', { name: 'Firmar lectura' }))
  const confirm = screen.getByRole('button', { name: 'Confirmar lectura' })
  expect(confirm).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Confirmo que leí las recomendaciones de este documento.' }))
  fireEvent.click(confirm)
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(request).toHaveBeenLastCalledWith('/alumnos/7/ppi-documentos/1/firmar', expect.objectContaining({method:'POST',body:JSON.stringify({confirmo_lectura:true})}))
  expect(screen.queryByRole('button', { name:'Firmar lectura' })).not.toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Lectura confirmada')
})

it("keeps the confirmation open if the signature cannot be saved", async () => {
  request.mockResolvedValue({ok:false,json:async()=>({detail:'Hay una nueva versión de este documento.'})})
  render(<PpiDocumentCard document={{...doc,consultado_en:'2026-10-08'}} />)
  fireEvent.click(screen.getByRole('button',{name:'Firmar lectura'}))
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button',{name:'Confirmar lectura'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('nueva versión')
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.queryByText(/Lectura confirmada/)).not.toBeInTheDocument()
})

it("lets EOE remind a pending teacher with an icon and applies cooldown", async () => {
  request.mockResolvedValue({ok:true,json:async()=>({ultimo_recordatorio_en:new Date().toISOString()})})
  render(<PpiDocumentCard document={{...doc,puede_firmar:false,puede_gestionar:true,destinatarios:[{id:9,nombre:'Docente A'},{id:10,nombre:'Docente B',firmado_en:'2026-10-08'}]}} />)
  fireEvent.click(screen.getByText('Lecturas confirmadas: 1 de 2'))
  const bell=screen.getByRole('button',{name:'Recordar a Docente A'})
  expect(bell.textContent).toBe('')
  expect(screen.queryByRole('button',{name:'Recordar a Docente B'})).not.toBeInTheDocument()
  fireEvent.click(bell)
  expect(await screen.findByRole('status')).toHaveTextContent('Recordatorio enviado a Docente A')
  expect(bell).toBeDisabled()
})

it("requires recipients before publishing a recommendation", async () => {
  request.mockResolvedValue({ok:true,json:async()=>({documents:[],can_upload:true,docentes:[{id:9,nombre:'Docente A'}]})})
  render(<PpiDocuments alumnoId={7} />)
  fireEvent.change(await screen.findByLabelText('Título'),{target:{value:'Recomendaciones'}})
  fireEvent.change(screen.getByLabelText('Archivo PDF'),{target:{files:[new File(['%PDF'],'guia.pdf',{type:'application/pdf'})]}})
  fireEvent.click(screen.getByLabelText('Requiere constancia de lectura'))
  fireEvent.submit(screen.getByRole('button',{name:'Subir PDF'}).closest('form')!)
  expect(await screen.findByRole('alert')).toHaveTextContent('Seleccioná al menos un docente')
  expect(request).toHaveBeenCalledTimes(1)
  request.mockResolvedValue({ok:true,json:async()=>({document:{...doc,puede_firmar:false,puede_gestionar:true}})})
  fireEvent.click(screen.getByLabelText('Docente A'))
  fireEvent.submit(screen.getByRole('button',{name:'Subir PDF'}).closest('form')!)
  await screen.findByText('PDF guardado correctamente.')
  const body=request.mock.calls[1][1].body
  expect(body.get('requiere_firma')).toBe('true')
  expect(body.get('docentes')).toBe('[9]')
})
