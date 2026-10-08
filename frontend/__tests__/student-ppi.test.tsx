import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import StudentPpi from "@/app/alumnos/[alumnoId]/_student-ppi"
import { authFetch } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({ authFetch: jest.fn() }))
const request = authFetch as jest.Mock

beforeEach(() => request.mockReset())

it.each([false, true])("saves the checkbox change from %s", async (value) => {
  const onSaved = jest.fn()
  request.mockResolvedValue({ ok: true, json: async () => ({ es_ppi: !value, can_edit_ppi: true }) })
  render(<StudentPpi alumnoId={7} value={value} canEdit onSaved={onSaved} />)
  fireEvent.click(screen.getByRole("checkbox", { name: /PPI/ }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith({ es_ppi: !value, can_edit_ppi: true }))
  expect(request).toHaveBeenCalledWith("/alumnos/7/", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ es_ppi: !value }) }))
  expect(screen.getByRole("status")).toHaveTextContent("Cambio guardado")
})

it("keeps the saved value when the request fails", async () => {
  const onSaved = jest.fn()
  request.mockResolvedValue({ ok: false, json: async () => ({ detail: "No autorizado" }) })
  render(<StudentPpi alumnoId={7} value={false} canEdit onSaved={onSaved} />)
  fireEvent.click(screen.getByRole("checkbox"))
  expect(await screen.findByRole("alert")).toHaveTextContent("No autorizado")
  expect(screen.getByRole("checkbox")).not.toBeChecked()
  expect(onSaved).not.toHaveBeenCalled()
})

it("disables editing for read-only access", () => {
  render(<StudentPpi alumnoId={7} value canEdit={false} onSaved={jest.fn()} />)
  expect(screen.getByRole("checkbox")).toBeDisabled()
  expect(screen.getByRole("checkbox")).toBeChecked()
  expect(request).not.toHaveBeenCalled()
})
