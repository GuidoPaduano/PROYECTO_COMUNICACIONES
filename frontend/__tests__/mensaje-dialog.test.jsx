import { render, screen } from "@testing-library/react"

import MensajeDialog from "@/components/ui/mensaje-dialog"

describe("MensajeDialog", () => {
  it("prioritizes school_course_name for the course chip", () => {
    render(
      <MensajeDialog
        open={true}
        onOpenChange={() => {}}
        mensaje={{
          asunto: "Aviso",
          contenido: "Contenido",
          emisor: "Preceptor",
          fecha: "2026-03-28",
          school_course_name: "1A Norte",
        }}
        onVerHistorial={() => {}}
      />
    )

    expect(screen.getByText("1A Norte")).toBeInTheDocument()
    expect(screen.queryByText(/^1A$/)).not.toBeInTheDocument()
  })
})
