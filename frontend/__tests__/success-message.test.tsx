import { render, screen } from "@testing-library/react"
import SuccessMessage from "@/components/ui/success-message"

describe("SuccessMessage", () => {
  it("renders provided text without the leading check emoji", () => {
    render(<SuccessMessage>✅ Operación exitosa</SuccessMessage>)
    expect(screen.getByText("Operación exitosa")).toBeInTheDocument()
  })
})
