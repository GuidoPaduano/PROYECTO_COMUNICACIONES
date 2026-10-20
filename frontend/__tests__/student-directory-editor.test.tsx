import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import Directory from "@/app/admin/_components/school-user-directory-page"
import { authFetch } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({
  authFetch: jest.fn(), useAuthGuard: jest.fn(),
  useSessionContext: () => ({ isSuperuser: true, groups: [], school: { id: 9, name: "Norte" } }),
}))
const request = authFetch as jest.Mock
const student = { id: 5, nombre: "Ana", apellido: "Perez", full_name: "Ana Perez", id_alumno: "A001", es_ppi: false, school_course_id: 1, school_course_name: "1A", nivel: "secundaria" }
const directory = { school: { id: 9, name: "Norte" }, totals: { alumnos: 1 }, alumnos_por_curso: [{ course: { id: 1, code: "1A", name: "1A" }, students: [student] }] }

it("opens student information from names in both directory layouts and refreshes after saving", async () => {
  request.mockImplementation(async (url: string, options: RequestInit) => ({ ok: true, json: async () => {
    if (url === "/admin/school-users/") return directory
    if (options?.method === "PATCH") return { student }
    return { student, courses: [{ id: 1, name: "1A", nivel: "secundaria", is_active: true }] }
  } }))
  render(<Directory />)
  const names = await screen.findAllByRole("button", { name: "Ana Perez" })
  expect(names).toHaveLength(2)
  expect(screen.getAllByRole("button", { name: "Editar datos" })).toHaveLength(2)
  fireEvent.click(names[0])
  expect(await screen.findByLabelText("Nombre")).toHaveValue("Ana")
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }))
  fireEvent.click(screen.getAllByRole("button", { name: "Editar datos" })[1])
  await screen.findByLabelText("Nombre")
  fireEvent.click(screen.getByRole("checkbox", { name: /PPI/ }))
  fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }))
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  expect(await screen.findByText("Alumno actualizado correctamente.")).toBeInTheDocument()
  expect(request.mock.calls.filter(([url]) => url === "/admin/school-users/").length).toBeGreaterThan(1)
})

it("opens the password modal for a school user and sends both passwords", async () => {
  const professor = { id: 12, username: "profesor12", full_name: "María López", is_active: true, assigned_school_courses: [] }
  request.mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => url === "/admin/school-users/"
      ? { ...directory, totals: { profesores: 1 }, profesores: [professor] }
      : { detail: "Contraseña actualizada correctamente." },
  }))
  render(<Directory />)
  fireEvent.click(await screen.findByRole("button", { name: /Profesores 1/ }))
  fireEvent.click(screen.getAllByRole("button", { name: "Cambiar contraseña" })[0])
  expect(await screen.findByText("Cambiar contraseña de profesor12")).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Contraseña actual"), { target: { value: "Anterior123!" } })
  fireEvent.change(screen.getByLabelText("Nueva contraseña"), { target: { value: "NuevaClaveFuerte123!" } })
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cambiar contraseña" }))
  await waitFor(() => expect(request).toHaveBeenCalledWith(
    "/admin/school-users/12/password/",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ current_password: "Anterior123!", new_password: "NuevaClaveFuerte123!" }),
    }),
  ))
  expect(await screen.findByText("Contraseña actualizada correctamente.")).toBeInTheDocument()
})
