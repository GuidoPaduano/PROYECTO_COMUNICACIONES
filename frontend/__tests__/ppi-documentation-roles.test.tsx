import { render, screen, waitFor } from "@testing-library/react"
import IntegrationPpiDocumentation from "@/components/integration-ppi-documentation"
import DocumentacionPage from "@/app/documentacion/page"
import { authFetch, useSessionContext } from "@/app/_lib/auth"

jest.mock("@/app/_lib/auth", () => ({ authFetch: jest.fn(), useSessionContext: jest.fn(), useAuthGuard: jest.fn() }))
jest.mock("@/app/alumnos/[alumnoId]/_ppi-documents", () => ({
  __esModule: true,
  default: ({ alumnoId, sendToAllCourseTeachers }: { alumnoId: number; sendToAllCourseTeachers: boolean }) => (
    <div data-testid="ppi-documents">{alumnoId} · {sendToAllCourseTeachers ? "integracion" : "eoe"}</div>
  ),
}))

const request = authFetch as jest.Mock
const session = useSessionContext as jest.Mock

beforeEach(() => {
  request.mockReset()
  session.mockReset()
  localStorage.clear()
  request.mockResolvedValue({
    ok: true,
    json: async () => ({ alumnos: [{ id: 7, nombre: "Ana", apellido: "Acosta", curso: "1A", legajo: "PPI1" }] }),
  })
})

it.each([
  { role: "EOE", endpoint: "/eoe/alumnos/", card: "7 · eoe" },
  { role: "Integracion", endpoint: "/integracion/alumnos/", card: "7 · integracion" },
])("loads the PPI documents for $role", async ({ role, endpoint, card }) => {
  session.mockReturnValue({ groups: [role], role, username: role, school: { id: 1 } })
  render(<IntegrationPpiDocumentation />)
  expect(await screen.findByTestId("ppi-documents")).toHaveTextContent(card)
  await waitFor(() => expect(request).toHaveBeenCalledWith(endpoint))
})

it("shows the PPI document list in EOE's Documentation page", async () => {
  session.mockReturnValue({ groups: ["EOE"], role: "EOE", username: "eoe", school: { id: 1 } })
  render(<DocumentacionPage />)
  expect(await screen.findByTestId("ppi-documents")).toHaveTextContent("7 · eoe")
  expect(request).toHaveBeenCalledWith("/eoe/alumnos/")
  expect(request).not.toHaveBeenCalledWith("/api/documentos/")
})
