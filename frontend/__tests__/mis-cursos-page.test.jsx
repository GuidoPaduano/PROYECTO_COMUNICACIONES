import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import MisCursosPage from "@/app/mis-cursos/page"
import { authFetch } from "@/app/_lib/auth"
import { invalidateCourseCatalogCache } from "@/app/_lib/courses"

const mockSession = {
  username: "qa_profesor_resilience",
  groups: ["Profesores"],
  isSuperuser: false,
  school: { id: 1 },
}

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
  getSessionProfile: jest.fn(),
  useAuthGuard: jest.fn(),
  useSessionContext: jest.fn(() => mockSession),
}))

function jsonResponse(data, ok = true, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    json: async () => data,
  }
}

describe("MisCursosPage", () => {
  beforeEach(() => {
    authFetch.mockReset()
    invalidateCourseCatalogCache()
  })

  it("muestra el error si todos los catálogos fallan y recupera al reintentar", async () => {
    const user = userEvent.setup()
    authFetch
      .mockResolvedValueOnce(jsonResponse({ detail: "Servicio de cursos no disponible." }, false, 503))
      .mockResolvedValueOnce(jsonResponse({ detail: "Servicio de cursos no disponible." }, false, 503))
      .mockResolvedValueOnce(jsonResponse({ detail: "Servicio de cursos no disponible." }, false, 503))
      .mockResolvedValueOnce(jsonResponse({ detail: "Servicio de cursos no disponible." }, false, 503))
      .mockResolvedValueOnce(
        jsonResponse({
          cursos: [{ id: "1A", code: "1A", nombre: "Primer año A", school_course_id: 17 }],
        })
      )

    render(<MisCursosPage />)

    expect(await screen.findByText("Servicio de cursos no disponible.")).toBeInTheDocument()
    expect(screen.queryByText(/no tenés cursos asignados/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /reintentar/i }))

    expect(await screen.findByText("Primer año A")).toBeInTheDocument()
    expect(authFetch).toHaveBeenCalledTimes(5)
  })
})
