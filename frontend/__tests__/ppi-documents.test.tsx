import userEvent from "@testing-library/user-event"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import PpiDocuments from "@/app/alumnos/[alumnoId]/_ppi-documents"
import { authFetch } from "@/app/_lib/auth"
jest.mock("@/app/_lib/auth", () => ({ authFetch: jest.fn() }))
const request = authFetch as jest.Mock
beforeEach(() => request.mockReset())

it("allows integration staff to upload a PDF and shows the saved document", async () => {
  request.mockImplementation(async (_url: string, options: RequestInit) => ({ ok: true, json: async () => options?.method === "POST" ? { document: { id:1,titulo:"Informe",nombre_archivo:"informe.pdf",tamano:40,creado_en:"2026-10-08",subido_por:"Integración" } } : { documents: [], can_upload: true } }))
  render(<PpiDocuments alumnoId={7} />)
  fireEvent.change(await screen.findByLabelText("Título"), { target: { value: "Informe" } })
  const file = new File(["%PDF-1.4"], "informe.pdf", { type: "application/pdf" })
  await userEvent.upload(screen.getByLabelText("Archivo PDF"), file)
  fireEvent.submit(screen.getByRole("button", { name: "Subir PDF" }).closest("form")!)
  expect(await screen.findByText("PDF guardado correctamente.")).toBeInTheDocument()
  expect(screen.getByRole("button", { name:"Descargar PDF" })).toBeInTheDocument()
  const [, opts] = request.mock.calls.find(([, options]) => options?.method === "POST")
  expect(opts.body.get("archivo")).toBe(file)
  expect(opts.body.get("titulo")).toBe("Informe")
})

it("shows read-only documentation without upload controls", async () => {
  request.mockResolvedValue({ok:true,json:async()=>({documents:[],can_upload:false})})
  render(<PpiDocuments alumnoId={7} />)
  await screen.findByText("Todavía no hay documentos para este alumno.")
  expect(screen.queryByLabelText("Archivo PDF")).not.toBeInTheDocument()
})

it("shows denied access without displaying upload controls", async () => {
  request.mockResolvedValue({ok:false,json:async()=>({detail:"No autorizado para este alumno."})})
  render(<PpiDocuments alumnoId={7} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("No autorizado")
  expect(screen.queryByLabelText("Archivo PDF")).not.toBeInTheDocument()
})
