// @ts-nocheck
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import Profile from "@/app/perfil/page"
import { authFetch, getProfileApi, logout } from "@/app/_lib/auth"

let mockProfile = null

jest.mock("next/link", () => {
  return function Link({ href, children, ...props }) {
    return (
      <a href={typeof href === "string" ? href : "#"} {...props}>
        {children}
      </a>
    )
  }
})

jest.mock("@/components/notification-bell", () => ({
  NotificationBell: () => <button type="button">Notificaciones</button>,
}))

jest.mock("@/app/_lib/useUnreadMessages", () => ({
  useUnreadMessages: () => 0,
}))

jest.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
  DropdownMenuTrigger: ({ children }) => children,
}))

jest.mock("@/app/_lib/auth", () => ({
  DEFAULT_SCHOOL_PRIMARY_COLOR: "#0b1b3f",
  authFetch: jest.fn(),
  getCachedProfileApi: jest.fn(() => mockProfile),
  getCachedSessionProfileData: jest.fn(() => null),
  getProfileApi: jest.fn(async () => mockProfile),
  logout: jest.fn(),
  useAuthGuard: jest.fn(),
  useSessionContext: jest.fn(() => null),
}))

function jsonResponse(data, ok = true, status = ok ? 200 : 400) {
  return {
    ok,
    status,
    json: async () => data,
  }
}

function baseProfile(overrides = {}) {
  return {
    user: {
      id: 1,
      username: "qa_profesor",
      first_name: "Profe",
      last_name: "QA",
      email: "profe@example.com",
      groups: ["Profesores"],
      rol: "Profesor",
      is_superuser: false,
    },
    school: {
      id: 1,
      name: "QA Local",
      short_name: "QA",
      primary_color: "#123456",
      logo_url: "/imagenes/Logo%20Color.png",
    },
    assigned_school_courses: [{ id: 10, school_course_id: 10, school_course_name: "1A QA" }],
    children: [],
    alumno: null,
    ...overrides,
  }
}

describe("Profile page", () => {
  beforeEach(() => {
    authFetch.mockReset()
    getProfileApi.mockClear()
    logout.mockClear()
    mockProfile = baseProfile()
  })

  it("lets a non-student edit name and email through perfil_api", async () => {
    const user = userEvent.setup()
    authFetch.mockImplementation(async (url, options = {}) => {
      if (url === "/perfil_api/" && options.method === "PATCH") {
        return jsonResponse({ detail: "ok" })
      }
      return jsonResponse({}, true)
    })

    render(<Profile />)

    await user.click(screen.getByRole("button", { name: /editar/i }))
    await user.clear(screen.getByLabelText(/nombre completo/i))
    await user.type(screen.getByLabelText(/nombre completo/i), "Nuevo Nombre")
    await user.clear(screen.getByLabelText(/correo/i))
    await user.type(screen.getByLabelText(/correo/i), "nuevo@example.com")
    await user.click(screen.getByRole("button", { name: /guardar/i }))

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith(
        "/perfil_api/",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            first_name: "Nuevo",
            last_name: "Nombre",
            email: "nuevo@example.com",
          }),
        })
      )
    })
    expect(await screen.findByText("Perfil actualizado.")).toBeInTheDocument()
  })

  it("lets a non-student change password and schedules logout after success", async () => {
    jest.useFakeTimers()
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
    authFetch.mockResolvedValue(jsonResponse({ detail: "Password ok." }))

    const { container } = render(<Profile />)

    try {
      await user.click(screen.getByRole("button", { name: /cambiar contrase/i }))
      await user.type(container.querySelector("#currentPassword"), "CurrentPassword123!")
      await user.type(container.querySelector("#newPassword"), "NewPassword123!")
      await user.type(container.querySelector("#confirmPassword"), "NewPassword123!")
      await user.click(screen.getByRole("button", { name: /actualizar/i }))

      await waitFor(() => {
        expect(authFetch).toHaveBeenCalledWith(
          "/auth/password-change/",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({
              current_password: "CurrentPassword123!",
              new_password: "NewPassword123!",
            }),
          })
        )
      })

      jest.advanceTimersByTime(1200)
      expect(logout).toHaveBeenCalled()
    } finally {
      jest.useRealTimers()
    }
  })

  it("hides edit/password controls for an unlinked student and lets them link a legajo", async () => {
    const user = userEvent.setup()
    mockProfile = baseProfile({
      user: {
        id: 2,
        username: "alumno_sin_legajo_precargado_para_test",
        first_name: "Alumno",
        last_name: "QA",
        email: "",
        groups: ["Alumnos"],
        rol: "Alumno",
      },
      assigned_school_courses: [],
      children: [],
      alumno: null,
    })
    authFetch.mockImplementation(async (url, options = {}) => {
      if (url === "/alumnos/vincular/" && options.method === "POST") return jsonResponse({ already_linked: false })
      return jsonResponse({})
    })

    render(<Profile />)

    expect(screen.queryByRole("button", { name: /editar/i })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /cambiar contrase/i })).not.toBeInTheDocument()
    expect(screen.getByText("Vincular mi legajo")).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/legajo/i))
    await user.type(screen.getByLabelText(/legajo/i), "ALU-100")
    await user.click(screen.getByRole("button", { name: /^vincular$/i }))

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith(
        "/alumnos/vincular/",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ id_alumno: "ALU-100" }),
        })
      )
    })
    expect(authFetch).toHaveBeenCalledTimes(1)
  })

  it("shows parent children returned by the profile API", async () => {
    mockProfile = baseProfile({
      user: {
        id: 3,
        username: "qa_padre",
        first_name: "Padre",
        last_name: "QA",
        email: "padre@example.com",
        groups: ["Padres"],
        rol: "Padre",
      },
      assigned_school_courses: [],
      children: [{ id: 21, id_alumno: "HIJO-1", nombre: "Hijo QA", school_course_name: "2B QA" }],
    })
    authFetch.mockImplementation(async (url) => {
      if (url === "/padres/mis-hijos/") {
        return jsonResponse({
          results: [{ id: 21, id_alumno: "HIJO-1", nombre: "Hijo QA", school_course_name: "2B QA" }],
        })
      }
      return jsonResponse({})
    })

    render(<Profile />)

    expect(await screen.findByText("Vínculos")).toBeInTheDocument()
    expect(await screen.findByRole("link", { name: "Hijo QA" })).toHaveAttribute(
      "href",
      "/alumnos/21?from=%2Fmis-hijos"
    )
    expect(screen.getByText(/2B QA/)).toBeInTheDocument()
  })
})