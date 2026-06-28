// @ts-nocheck
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import PlataformaBackupsPage from "@/app/admin/plataforma/backups/page"
import { authFetch } from "@/app/_lib/auth"

let mockSession = { isSuperuser: true }

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
  useSessionContext: jest.fn(() => mockSession),
}))

function backupResponse({ ok = true, detail = "", filename = "global-backup-test.sqlite3" } = {}) {
  return {
    ok,
    json: async () => ({ detail }),
    blob: async () => new Blob(["backup-test"], { type: "application/octet-stream" }),
    headers: new Headers({
      "Content-Disposition": `attachment; filename="${filename}"`,
    }),
  }
}

describe("PlataformaBackupsPage", () => {
  let clickSpy

  beforeEach(() => {
    mockSession = { isSuperuser: true }
    authFetch.mockReset()
    clickSpy = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    window.URL.createObjectURL = jest.fn(() => "blob:backup-test")
    window.URL.revokeObjectURL = jest.fn()
  })

  afterEach(() => {
    clickSpy.mockRestore()
  })

  it("genera el backup, dispara la descarga y muestra el archivo", async () => {
    const user = userEvent.setup()
    authFetch.mockResolvedValue(backupResponse())

    render(<PlataformaBackupsPage />)
    await user.click(screen.getByRole("button", { name: /generar backup completo/i }))

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith("/admin/backups/manual/", {
        method: "POST",
        body: JSON.stringify({}),
      })
    })
    expect(window.URL.createObjectURL).toHaveBeenCalled()
    expect(clickSpy).toHaveBeenCalled()
    expect(await screen.findByText(/backup generado y descargado/i)).toBeInTheDocument()
    expect(screen.getByText(/global-backup-test\.sqlite3/i)).toBeInTheDocument()
  })

  it("muestra el detalle del servidor y vuelve a habilitar el boton", async () => {
    const user = userEvent.setup()
    authFetch.mockResolvedValue(backupResponse({ ok: false, detail: "pg_dump no esta disponible" }))

    render(<PlataformaBackupsPage />)
    await user.click(screen.getByRole("button", { name: /generar backup completo/i }))

    expect(await screen.findByText("pg_dump no esta disponible")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /generar backup completo/i })).toBeEnabled()
  })

  it("muestra acceso restringido a usuarios no superadmin", () => {
    mockSession = { isSuperuser: false }

    render(<PlataformaBackupsPage />)

    expect(screen.getByText(/acceso restringido/i)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /generar backup/i })).not.toBeInTheDocument()
  })
})