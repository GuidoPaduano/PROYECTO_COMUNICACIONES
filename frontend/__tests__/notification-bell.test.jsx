import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { NotificationBell } from "@/components/notification-bell"
import { authFetch } from "@/app/_lib/auth"
import { getUnreadSnapshot, requestUnreadRefresh } from "@/app/_lib/unread-store"

const mockPush = jest.fn()
let mockSnapshot = { notifications: 0, messages: 0 }

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}))

jest.mock("next/link", () => {
  return function Link({ href, children, ...props }) {
    return (
      <a href={typeof href === "string" ? href : "#"} {...props}>
        {children}
      </a>
    )
  }
})

jest.mock("@/components/ui/dropdown-menu", () => {
  const React = require("react")
  const DropdownContext = React.createContext(null)

  function DropdownMenu({ open, onOpenChange, children }) {
    return <DropdownContext.Provider value={{ open, onOpenChange }}>{children}</DropdownContext.Provider>
  }

  function DropdownMenuTrigger({ asChild, children }) {
    const ctx = React.useContext(DropdownContext)
    if (asChild && React.isValidElement(children)) {
      return React.cloneElement(children, {
        onClick: () => ctx.onOpenChange(!ctx.open),
      })
    }
    return (
      <button type="button" onClick={() => ctx.onOpenChange(!ctx.open)}>
        {children}
      </button>
    )
  }

  function DropdownMenuContent({ children }) {
    const ctx = React.useContext(DropdownContext)
    return ctx.open ? <div role="menu">{children}</div> : null
  }

  function DropdownMenuItem({ children, onSelect }) {
    return (
      <button
        type="button"
        role="menuitem"
        onClick={(event) => onSelect?.({ ...event, preventDefault: () => {} })}
      >
        {children}
      </button>
    )
  }

  return {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel: ({ children }) => <div>{children}</div>,
    DropdownMenuSeparator: () => <hr />,
    DropdownMenuTrigger,
  }
})

jest.mock("@/app/_lib/auth", () => ({
  authFetch: jest.fn(),
}))

jest.mock("@/app/_lib/inbox", () => ({
  notifyInboxChanged: jest.fn(),
}))

jest.mock("@/app/_lib/unread-store", () => ({
  getUnreadSnapshot: jest.fn(() => mockSnapshot),
  requestUnreadRefresh: jest.fn(async () => {}),
  subscribeUnread: jest.fn(() => () => {}),
}))

function jsonResponse(data, ok = true, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    json: async () => data,
  }
}

describe("NotificationBell", () => {
  beforeEach(() => {
    mockPush.mockClear()
    authFetch.mockReset()
    requestUnreadRefresh.mockClear()
    getUnreadSnapshot.mockClear()
    mockSnapshot = { notifications: 0, messages: 0 }
  })

  it("caps the controlled badge at 99+ and renders controlled items without fetching", async () => {
    const user = userEvent.setup()

    render(
      <NotificationBell
        unreadCount={125}
        items={[{ id: 1, kind: "notificacion", title: "Aviso", description: "Detalle", href: "/mensajes" }]}
      />
    )

    expect(screen.getByText("99+")).toBeInTheDocument()

    await user.click(screen.getByRole("button"))

    expect(screen.getByText("Aviso")).toBeInTheDocument()
    expect(screen.getByText("Detalle")).toBeInTheDocument()
    expect(authFetch).not.toHaveBeenCalled()
  })

  it("loads notification preview, marks an unread item, and navigates to the derived grade URL", async () => {
    const user = userEvent.setup()
    mockSnapshot = { notifications: 1, messages: 0 }
    authFetch.mockImplementation(async (url, options = {}) => {
      if (String(url).startsWith("/api/notificaciones/recientes/")) {
        return jsonResponse([
          {
            id: 7,
            tipo: "nota",
            titulo: "Nueva nota para Ana",
            descripcion: "Calificacion: 8",
            leida: false,
            meta: { alumno_id: "ALU-1" },
          },
        ])
      }
      if (url === "/api/notificaciones/7/marcar_leida/" && options.method === "POST") {
        return jsonResponse({})
      }
      return jsonResponse({}, false, 404)
    })

    render(<NotificationBell />)

    await user.click(screen.getByRole("button"))

    expect(await screen.findByText("Ana recibió una nota")).toBeInTheDocument()

    await user.click(screen.getByText("Ana recibió una nota"))

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith("/api/notificaciones/7/marcar_leida/", { method: "POST" })
    })
    expect(mockPush).toHaveBeenCalledWith("/alumnos/ALU-1/?tab=notas")
  })

  it("marks all notifications read and refreshes unread state", async () => {
    const user = userEvent.setup()
    mockSnapshot = { notifications: 3, messages: 0 }
    authFetch.mockImplementation(async (url, options = {}) => {
      if (String(url).startsWith("/api/notificaciones/recientes/")) {
        return jsonResponse([
          { id: 8, tipo: "sancion", titulo: "Nueva sancion para Ana", descripcion: "Motivo: Conducta", leida: false },
        ])
      }
      if (url === "/api/notificaciones/marcar_todas_leidas/" && options.method === "POST") {
        mockSnapshot = { notifications: 0, messages: 0 }
        return jsonResponse({})
      }
      return jsonResponse({}, false, 404)
    })

    render(<NotificationBell />)

    expect(screen.getByText("3")).toBeInTheDocument()

    await user.click(screen.getByRole("button"))
    await screen.findByText("Marcar todas leídas")
    await user.click(screen.getByText("Marcar todas leídas"))

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith("/api/notificaciones/marcar_todas_leidas/", { method: "POST" })
    })
    expect(requestUnreadRefresh).toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.queryByText("3")).not.toBeInTheDocument()
    })
  })

  it("shows an empty state when the preview endpoint returns no unread notifications", async () => {
    const user = userEvent.setup()
    authFetch.mockResolvedValue(jsonResponse([]))

    render(<NotificationBell />)

    await user.click(screen.getByRole("button"))

    expect(await screen.findByText(/notificaciones por ahora/i)).toBeInTheDocument()
  })
})
