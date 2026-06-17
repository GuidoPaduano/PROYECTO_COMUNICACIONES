export function createClientRequestId() {
  return (
    globalThis.crypto?.randomUUID?.() ||
    "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
      const value = Math.floor(Math.random() * 16)
      return (char === "x" ? value : (value & 0x3) | 0x8).toString(16)
    })
  )
}

export function buildReplyRequestAttempts(payload) {
  const requestPayload = {
    ...payload,
    client_request_id: payload.client_request_id || createClientRequestId(),
  }
  const formPayload = new FormData()
  formPayload.append("mensaje_id", String(requestPayload.mensaje_id))
  formPayload.append("asunto", requestPayload.asunto)
  formPayload.append("contenido", requestPayload.contenido)
  formPayload.append("client_request_id", requestPayload.client_request_id)

  return [
    {
      body: JSON.stringify(requestPayload),
      headers: { "Content-Type": "application/json", Accept: "application/json" },
    },
    {
      body: formPayload,
      headers: { Accept: "application/json" },
    },
  ]
}
