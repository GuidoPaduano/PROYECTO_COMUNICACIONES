import {
  buildReplyRequestAttempts,
  createClientRequestId,
} from "@/app/_lib/idempotency"


describe("message reply idempotency", () => {
  it("genera identificadores UUID", () => {
    expect(createClientRequestId()).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    )
  })

  it("reutiliza la misma clave en los intentos JSON y FormData", () => {
    const [jsonAttempt, formAttempt] = buildReplyRequestAttempts({
      mensaje_id: 42,
      asunto: "Re: Consulta",
      contenido: "Respuesta",
    })
    const jsonPayload = JSON.parse(jsonAttempt.body)

    expect(formAttempt.body.get("client_request_id")).toBe(jsonPayload.client_request_id)
    expect(formAttempt.body.get("mensaje_id")).toBe("42")
    expect(jsonPayload.client_request_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    )
  })
})
