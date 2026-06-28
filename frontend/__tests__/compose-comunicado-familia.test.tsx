// @ts-nocheck
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import ComposeComunicadoFamilia from "@/app/mensajes/_compose-comunicado-familia"
import { authFetch } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({
  authFetch: jest.fn(),
  useSessionContext: jest.fn(() => ({
    username: "qa_profesor",
    school: { id: 1 },
  })),
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

describe("ComposeComunicadoFamilia", () => {
  beforeEach(() => {
    authFetch.mockReset()
  })

  it("habilita Enviar cuando el tutor viene como id numerico", async () => {
    const user = userEvent.setup()

    authFetch.mockImplementation((url, options = {}) => {
      if (url === "/preceptor/cursos/") {
        return Promise.resolve(
          jsonResponse([{ id: 101, nombre: "1A", school_course_id: 101, code: "1A" }])
        )
      }
      if (String(url).startsWith("/alumnos/")) {
        return Promise.resolve(
          jsonResponse({
            alumnos: [
              {
                id: 10,
                id_alumno: "QA001",
                nombre: "Ana",
                apellido: "QA",
                padre: 55,
              },
            ],
          })
        )
      }
      if (url === "/api/mensajes/enviar/" && options.method === "POST") {
        return Promise.resolve(jsonResponse({ id: 900 }))
      }
      return Promise.resolve(jsonResponse({ detail: "unexpected request" }, false, 404))
    })

    render(<ComposeComunicadoFamilia open={true} onOpenChange={() => {}} />)

    await screen.findByRole("heading", { name: /comunicado a familias/i })
    await screen.findByText(/Hijo\/a: QA, Ana/)

    const sendButton = screen.getByRole("button", { name: /^Enviar$/ })
    expect(sendButton).toBeDisabled()

    await user.type(screen.getByLabelText(/asunto/i), "Aviso de prueba")
    await user.type(screen.getByLabelText(/^mensaje$/i), "Contenido de prueba")

    await waitFor(() => expect(sendButton).toBeEnabled())
    await user.click(sendButton)

    await waitFor(() => {
      const sendCall = authFetch.mock.calls.find(
        ([url, options]) => url === "/api/mensajes/enviar/" && options?.method === "POST"
      )
      expect(sendCall).toBeTruthy()
      expect(JSON.parse(sendCall[1].body)).toEqual(
        expect.objectContaining({
          receptor_id: 55,
          alumno_id: 10,
          asunto: "Aviso de prueba",
          contenido: "Contenido de prueba",
          tipo: "comunicado",
        })
      )
    })
  })
})