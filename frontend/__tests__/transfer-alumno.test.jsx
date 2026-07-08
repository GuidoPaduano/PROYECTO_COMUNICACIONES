import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import TransferAlumno from "@/app/alumnos/[alumnoId]/_transfer-alumno"
import { authFetch } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({
  authFetch: jest.fn(),
}))

function jsonResponse(data, ok = true, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
    text: async () => JSON.stringify(data),
  }
}

describe("TransferAlumno", () => {
  beforeEach(() => {
    authFetch.mockReset()
  })

  it("sigue buscando cursos si el primer catalogo solo trae el curso actual", async () => {
    const user = userEvent.setup()

    authFetch.mockImplementation((url, options = {}) => {
      if (url === "/alumnos/cursos/") {
        return Promise.resolve(
          jsonResponse({
            cursos: [{ id: "1B", nombre: "1B", code: "1B", school_course_id: 101 }],
          })
        )
      }
      if (url === "/notas/catalogos/") {
        return Promise.resolve(
          jsonResponse({
            cursos: [
              { id: "1B", nombre: "1B", code: "1B", school_course_id: 101 },
              { id: "2A", nombre: "2A", code: "2A", school_course_id: 202 },
            ],
          })
        )
      }
      if (url === "/api/alumnos/transferir/" || url === "/alumnos/transferir/") {
        return Promise.resolve(jsonResponse({ alumno: { id: 7, school_course_id: 202 } }))
      }
      return Promise.resolve(jsonResponse({ detail: `Unexpected ${url}` }, false, 404))
    })

    render(<TransferAlumno alumnoPk={7} cursoActual="1B" />)

    await user.click(screen.getByRole("button", { name: /transferir alumno/i }))

    const transferButton = await screen.findByRole("button", {
      name: /^transferir$/i,
    })

    await waitFor(() => expect(screen.getByText("2A")).toBeInTheDocument())
    await waitFor(() => expect(transferButton).toBeEnabled())

    await user.click(transferButton)

    await waitFor(() => {
      const transferCall = authFetch.mock.calls.find(
        ([url, options]) => url === "/alumnos/transferir/" && options?.method === "POST"
      )
      expect(transferCall).toBeTruthy()
      expect(JSON.parse(transferCall[1].body)).toEqual({
        alumno_id: 7,
        school_course_id: 202,
      })
    })
  })
})
