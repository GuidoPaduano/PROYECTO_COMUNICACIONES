import { expect, test } from "@playwright/test"

import {
  apiJson,
  apiResponse,
  loginAs,
  uniqueQaText,
  watchRuntimeFailures,
} from "./helpers"

function asList(payload: any) {
  if (Array.isArray(payload)) {
    return payload
  }
  return payload?.results || payload?.mensajes || payload?.data || []
}

async function getParentChildren(page: any) {
  await loginAs(page, "qa_padre")
  await expect(page).toHaveURL(/\/dashboard/)
  const payload = await apiJson<any>(page, "/api/padres/mis-hijos/")
  return asList(payload)
}

async function sendMessageToQa002Parent(page: any, subject: string, content: string) {
  const children = await getParentChildren(page)
  const qa002 = children.find((child: any) => child?.id_alumno === "QA002")
  expect(qa002?.school_course_id).toBeTruthy()

  await loginAs(page, "qa_preceptor")
  await expect(page).toHaveURL(/\/dashboard/)

  const response = await apiResponse<any>(page, "/api/mensajes/enviar/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      alumno_id: "QA002",
      asunto: subject,
      contenido: content,
      tipo: "mensaje",
    }),
  })

  expect(response.status).toBe(201)
  expect(response.data?.id || response.data?.ids?.length).toBeTruthy()
  return response.data?.id || response.data?.ids?.[0]
}

test.describe("QA local session security and advanced messaging", () => {
  test("usuarios anonimos no acceden a rutas ni APIs privadas", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await page.goto("/dashboard")
    await expect(page).toHaveURL(/\/login/)

    const inbox = await apiResponse(page, "/api/mensajes/recibidos/")
    expect([401, 403]).toContain(inbox.status)

    const report = await apiResponse(page, "/api/reportes/mis-estadisticas/")
    expect([401, 403]).toContain(report.status)
    expect(failures).toEqual([])
  })

  test("logout invalida la sesion para APIs privadas", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)

    const beforeLogout = await apiResponse(page, "/api/mensajes/recibidos/?limit=1")
    expect(beforeLogout.status).toBe(200)

    const logout = await apiResponse(page, "/api/auth/logout/", { method: "POST" })
    expect([204, 205]).toContain(logout.status)

    const afterLogout = await apiResponse(page, "/api/mensajes/recibidos/?limit=1")
    expect([401, 403]).toContain(afterLogout.status)

    await page.goto("/mensajes")
    await expect(page).toHaveURL(/\/login/)
    expect(failures).toEqual([])
  })

  test("mensaje grupal queda limitado al curso destinatario", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const children = await getParentChildren(page)
    const qa001 = children.find((child: any) => child?.id_alumno === "QA001")
    const qa002 = children.find((child: any) => child?.id_alumno === "QA002")
    expect(qa001?.school_course_id).toBeTruthy()
    expect(qa002?.school_course_id).toBeTruthy()

    const subject = uniqueQaText("Curso 1A QA")
    const content = uniqueQaText("Comunicado curso QA")

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    const sendOwnCourse = await apiResponse<any>(page, "/api/mensajes/enviar_grupal/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        school_course_id: qa001.school_course_id,
        asunto: subject,
        contenido: content,
        tipo: "comunicado",
      }),
    })
    expect(sendOwnCourse.status).toBe(201)
    expect(Number(sendOwnCourse.data?.mensajes_creados || 0)).toBeGreaterThan(0)

    const sendOtherCourse = await apiResponse(page, "/api/mensajes/enviar_grupal/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        school_course_id: qa002.school_course_id,
        asunto: uniqueQaText("Curso 2A bloqueado QA"),
        contenido: content,
        tipo: "comunicado",
      }),
    })
    expect(sendOtherCourse.status).toBe(403)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const qa001Inbox = asList(await apiJson<any>(page, "/api/mensajes/recibidos/?alumno_id=QA001&limit=50"))
    const qa002Inbox = asList(await apiJson<any>(page, "/api/mensajes/recibidos/?alumno_id=QA002&limit=50"))

    expect(qa001Inbox.some((message: any) => String(message?.asunto || "").includes(subject))).toBeTruthy()
    expect(qa002Inbox.some((message: any) => String(message?.asunto || "").includes(subject))).toBeFalsy()
    expect(failures).toEqual([])
  })

  test("solo el destinatario puede leer, marcar y responder un mensaje", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const subject = uniqueQaText("Privado QA002")
    const content = uniqueQaText("Contenido privado QA")
    const reply = uniqueQaText("Respuesta privada QA")

    const messageId = await sendMessageToQa002Parent(page, subject, content)
    expect(messageId).toBeTruthy()

    await loginAs(page, "qa_alumno")
    await expect(page).toHaveURL(/\/dashboard/)

    const outsiderThread = await apiResponse(page, `/api/mensajes/conversacion/${messageId}/`)
    expect(outsiderThread.status).toBe(403)

    const outsiderMarkRead = await apiResponse(page, `/api/mensajes/${messageId}/marcar_leido/`, {
      method: "POST",
    })
    expect(outsiderMarkRead.status).toBe(403)

    const outsiderReply = await apiResponse(page, "/api/mensajes/responder/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje_id: messageId, contenido: uniqueQaText("Respuesta ajena QA") }),
    })
    expect(outsiderReply.status).toBe(403)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const unreadBefore = asList(await apiJson<any>(page, "/api/mensajes/recibidos/?solo_no_leidos=1&limit=100"))
    expect(unreadBefore.some((message: any) => message?.id === messageId)).toBeTruthy()

    const parentThread = await apiResponse<any>(page, `/api/mensajes/conversacion/${messageId}/`)
    expect(parentThread.status).toBe(200)
    expect(asList(parentThread.data?.mensajes).some((message: any) => message?.id === messageId)).toBeTruthy()

    const parentReply = await apiResponse<any>(page, "/api/mensajes/responder/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje_id: messageId, contenido: reply }),
    })
    expect(parentReply.status).toBe(201)
    expect(parentReply.data?.id).toBeTruthy()
    expect(parentReply.data?.thread_id).toBeTruthy()

    const markRead = await apiResponse(page, `/api/mensajes/${messageId}/marcar_leido/`, { method: "POST" })
    expect(markRead.status).toBe(204)

    const unreadAfter = asList(await apiJson<any>(page, "/api/mensajes/recibidos/?solo_no_leidos=1&limit=100"))
    expect(unreadAfter.some((message: any) => message?.id === messageId)).toBeFalsy()

    await loginAs(page, "qa_preceptor")
    await expect(page).toHaveURL(/\/dashboard/)
    const preceptorThread = await apiJson<any>(page, `/api/mensajes/conversacion/${parentReply.data.id}/`)
    expect(asList(preceptorThread?.mensajes).some((message: any) => String(message?.contenido || "").includes(reply))).toBeTruthy()
    expect(failures).toEqual([])
  })
})
