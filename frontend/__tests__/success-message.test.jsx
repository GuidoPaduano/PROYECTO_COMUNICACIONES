import { render, screen } from "@testing-library/react"
import SuccessMessage from "@/components/ui/success-message"

describe("SuccessMessage", () => {
  it("renders provided text without the leading check emoji", () => {
    render(<SuccessMessage>✅ Operacion exitosa</SuccessMessage>)
    expect(screen.getByText("Operacion exitosa")).toBeInTheDocument()
  })
})
