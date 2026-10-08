import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import StudentEditor from "@/app/admin/_components/student-editor"
import { authFetch } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({ authFetch: jest.fn() }))
const request = authFetch as jest.Mock
const student = { id: 5, nombre: "Ana", apellido: "Perez", id_alumno: "A001", es_ppi: false, school_course_id: 1, school_course_name: "1A", nivel: "secundaria" }
const payload = { student, courses: [{ id: 1, name: "1A", nivel: "secundaria", is_active: true }, { id: 2, name: "Primero", nivel: "primaria", is_active: true }] }

beforeEach(() => {
  request.mockReset()
  request.mockResolvedValue({ ok: true, json: async () => payload })
})

it("loads the selected student from the active school", async () => {
  render(<StudentEditor schoolId="9" studentId={5} onClose={jest.fn()} onSaved={jest.fn()} />)
  expect(await screen.findByLabelText("Nombre")).toHaveValue("Ana")
  expect(request).toHaveBeenCalledWith("/admin/students/5", { headers: { "X-School": "9" } })
  expect(screen.getByText("Sin cuenta vinculada")).toBeInTheDocument()
})

it("saves PPI and course, showing the course level", async () => {
  request.mockImplementation(async (_url: string, options: RequestInit) => options?.method === "PATCH"
    ? { ok: true, json: async () => ({ student }) }
    : { ok: true, json: async () => payload })
  const onClose = jest.fn()
  const onSaved = jest.fn()
  render(<StudentEditor schoolId="9" studentId={5} onClose={onClose} onSaved={onSaved} />)
  await screen.findByLabelText("Nombre")
  fireEvent.click(screen.getByRole("checkbox", { name: /PPI/ }))
  fireEvent.change(screen.getByLabelText("Curso"), { target: { value: "2" } })
  expect(screen.getByText("Primaria", { selector: "strong" })).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }))
  await waitFor(() => expect(request).toHaveBeenCalledWith("/admin/students/5", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ nombre: "Ana", apellido: "Perez", id_alumno: "A001", es_ppi: true, school_course_id: 2 }) })))
  await waitFor(() => expect(onSaved).toHaveBeenCalled())
})

it("keeps entered data on validation failure", async () => {
  request.mockImplementation(async (_url: string, options: RequestInit) => options?.method === "PATCH"
    ? { ok: false, json: async () => ({ detail: "Legajo duplicado" }) }
    : { ok: true, json: async () => payload })
  const onClose = jest.fn()
  const onSaved = jest.fn()
  render(<StudentEditor schoolId="9" studentId={5} onClose={onClose} onSaved={onSaved} />)
  await screen.findByLabelText("Nombre")
  fireEvent.change(screen.getByLabelText("Legajo"), { target: { value: "DUP" } })
  fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Legajo duplicado")
  expect(screen.getByLabelText("Legajo")).toHaveValue("DUP")
})

it("cancels without saving", async () => {
  const onClose = jest.fn()
  const onSaved = jest.fn()
  render(<StudentEditor schoolId="9" studentId={5} onClose={onClose} onSaved={onSaved} />)
  await screen.findByLabelText("Nombre")
  fireEvent.click(screen.getByRole("checkbox", { name: /PPI/ }))
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }))
  expect(onClose).toHaveBeenCalled()
  expect(request.mock.calls.some(([, options]) => options?.method === "PATCH")).toBe(false)
})
