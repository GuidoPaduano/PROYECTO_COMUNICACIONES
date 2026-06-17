import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import MensajesPage from "@/app/mensajes/page"
import { authFetch } from "@/app/_lib/auth"

jest.mock("next/dynamic", () => () => function DynamicComponent() {
  return null
})

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
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

jest.mock("@/components/notification-bell", () => ({
  NotificationBell: () => null,
}))

jest.mock("@/app/_lib/useUnreadCount", () => ({
  useUnreadCount: () => 0,
}))

jest.mock("@/app/_lib/inbox", () => ({
  notifyInboxChanged: jest.fn(),
}))

jest.mock("@/app/_lib/auth", () => ({
  authFetch: jest.fn(),
  getCachedSessionProfileData: jest.fn(() => ({
    id: 7,
    username: "qa_profesor",
    groups: ["Profesores"],
  })),
  getSessionProfile: jest.fn(),
  useAuthGuard: jest.fn(),
  useSessionContext: jest.fn(() => ({
    username: "qa_profesor",
    school: { id: 1 },
    groups: ["Profesores"],
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

describe("MensajesPage resilience", () => {
  beforeEach(() => {
    authFetch.mockReset()
  })

  it("muestra el error HTTP y recupera la bandeja al reintentar", async () => {
    const user = userEvent.setup()
    authFetch
      .mockResolvedValueOnce(
        jsonResponse({ detail: "Bandeja temporalmente no disponible." }, false, 503)
      )
      .mockResolvedValueOnce(jsonResponse([]))

    render(<MensajesPage />)

    expect(await screen.findByText("Bandeja temporalmente no disponible.")).toBeInTheDocument()
    expect(screen.queryByText("No hay mensajes recibidos.")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /reintentar/i }))

    expect(await screen.findByText("No hay mensajes recibidos.")).toBeInTheDocument()
    expect(authFetch).toHaveBeenCalledTimes(2)
  })
})
