import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import MisHijosPage from "@/app/mis-hijos/page"
import { authFetch } from "@/app/_lib/auth"

const mockReplace = jest.fn()
const mockSearchParams = new URLSearchParams()

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  useSearchParams: () => mockSearchParams,
}))

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
    username: "qa_padre_resilience",
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

describe("MisHijosPage", () => {
  beforeEach(() => {
    authFetch.mockReset()
    mockReplace.mockReset()
    window.localStorage.clear()
  })

  it("diferencia un error HTTP de una cuenta sin hijos y permite reintentar", async () => {
    const user = userEvent.setup()
    authFetch
      .mockResolvedValueOnce(
        jsonResponse({ detail: "Vínculos familiares temporalmente no disponibles." }, false, 503)
      )
      .mockResolvedValueOnce(
        jsonResponse({
          results: [{ id: 21, id_alumno: "QA001", nombre: "Alumno QA" }],
        })
      )

    render(<MisHijosPage />)

    expect(
      await screen.findByText("Vínculos familiares temporalmente no disponibles.")
    ).toBeInTheDocument()
    expect(
      screen.queryByText("No se encontraron alumnos asociados a tu cuenta.")
    ).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /reintentar/i }))

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/alumnos/21?from=%2Fmis-hijos")
    })
    expect(authFetch).toHaveBeenCalledTimes(2)
  })
})
