// @ts-nocheck
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import AlumnosPage from "@/app/alumnos/page"
import { authFetch } from "@/app/_lib/auth"

jest.mock("next/link", () => {
  return function Link({ href, children, ...props }) {
    return (
      <a href={href} {...props}>
        {children}
      </a>
    )
  }
})

jest.mock("@/app/_lib/auth", () => ({
  authFetch: jest.fn(),
  useAuthGuard: jest.fn(),
  useSessionContext: jest.fn(() => ({
    username: "qa_profesor",
    school: { id: 1 },
  })),
}))

function jsonResponse(data, ok = true, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    json: async () => data,
  }
}

describe("AlumnosPage", () => {
  beforeEach(() => {
    authFetch.mockReset()
  })

  it("muestra carga sin anticipar el estado vacío", () => {
    authFetch.mockReturnValue(new Promise(() => {}))

    render(<AlumnosPage />)

    expect(screen.getByText("Cargando cursos...")).toBeInTheDocument()
    expect(screen.queryByText("No hay cursos para mostrar.")).not.toBeInTheDocument()
  })

  it("distingue un catálogo vacío exitoso", async () => {
    authFetch.mockResolvedValue(jsonResponse({ cursos: [] }))

    render(<AlumnosPage />)

    expect(await screen.findByText("No hay cursos para mostrar.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /reintentar/i })).not.toBeInTheDocument()
  })

  it("muestra el error del servidor y recupera los cursos al reintentar", async () => {
    const user = userEvent.setup()
    authFetch
      .mockResolvedValueOnce(
        jsonResponse({ detail: "Cursos temporalmente no disponibles." }, false, 503)
      )
      .mockResolvedValueOnce(
        jsonResponse({
          cursos: [{ id: "1A", nombre: "Primer año A", school_course_id: 17 }],
        })
      )

    render(<AlumnosPage />)

    expect(await screen.findByText("Cursos temporalmente no disponibles.")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /reintentar/i }))

    expect(await screen.findByText("Primer año A")).toBeInTheDocument()
    expect(authFetch).toHaveBeenCalledTimes(2)
  })
})