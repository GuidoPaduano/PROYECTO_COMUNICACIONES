import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import IntegrationPpiDocumentsDashboardCard from "@/components/integration-ppi-documents-dashboard-card"
import { authFetch } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({
  authFetch: jest.fn(),
  useSessionContext: () => ({ username: "integration", school: { id: 1 } }),
}))

const request = authFetch as jest.Mock

beforeEach(() => {
  request.mockReset()
  localStorage.clear()
  request.mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => url === "/integracion/alumnos/"
      ? { alumnos: [
          { id: 7, nombre: "Ana", apellido: "Acosta", curso: "1A" },
          { id: 8, nombre: "Bruno", apellido: "Báez", curso: "2A" },
        ] }
      : { documents: url.includes("/7/")
          ? [{ id: 31, titulo: "Informe de Ana", creado_en: "2026-10-15", version: 1, requiere_firma: false }]
          : [{ id: 32, titulo: "Informe de Bruno", creado_en: "2026-10-15", version: 1, requiere_firma: true }],
      },
  }))
})

it("shows documents for the selected PPI student and follows changes to the selection", async () => {
  localStorage.setItem("integracion_last_alumno_ppi", "8")
  render(<IntegrationPpiDocumentsDashboardCard />)
  expect(await screen.findByText("Informe de Bruno")).toBeInTheDocument()
  expect(screen.queryByText("Informe de Ana")).not.toBeInTheDocument()
  expect(screen.getByRole("link", { name: "Ver" })).toHaveAttribute("href", "/documentacion?alumno_id=8&ppi_document=32#ppi-document-32")

  fireEvent.change(screen.getByLabelText("Alumno PPI"), { target: { value: "7" } })
  expect(await screen.findByText("Informe de Ana")).toBeInTheDocument()
  await waitFor(() => expect(localStorage.getItem("integracion_last_alumno_ppi")).toBe("7"))
  expect(screen.queryByText("Informe de Bruno")).not.toBeInTheDocument()
})
