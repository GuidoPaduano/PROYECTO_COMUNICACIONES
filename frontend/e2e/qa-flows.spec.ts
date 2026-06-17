import { expect, test } from "@playwright/test"

import {
  apiJson,
  localDateString,
  loginAs,
  selectOptionMatching,
  uniqueQaText,
  watchRuntimeFailures,
} from "./helpers"

test.describe("QA local functional flows", () => {
  test("profesor carga una nota y queda persistida", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const today = localDateString()
    const materia = "Matemática"

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/agregar_nota")
    await expect(page.getByRole("heading", { name: /carga de notas/i })).toBeVisible()

    const selects = page.locator("select")
    await expect(selects.nth(0)).toBeEnabled({ timeout: 15_000 })
    await selectOptionMatching(selects.nth(0), /1A/)
    await expect(page.getByText(/ana.*qa|qa.*ana/i)).toBeVisible()

    await selectOptionMatching(selects.nth(1), /^Matem/)
    await selectOptionMatching(selects.nth(2), /examen/i)
    await selectOptionMatching(selects.nth(3), /^9(?:\.|,)?00$|^9$/)
    await selectOptionMatching(selects.nth(4), /^[12]$/)
    await page.locator('input[type="date"]').first().fill(today)
    await page.getByRole("button", { name: /aplicar a todas/i }).click()

    const saveResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/calificaciones/notas/masivo") && response.status() < 400
    })
    await page.getByRole("button", { name: /guardar seleccionadas/i }).click()
    await saveResponse
    await expect(page.getByText(/guardadas?\s+\d+\s+notas/i)).toBeVisible()

    const notasPayload = await apiJson<any>(page, "/api/notas/?alumno_id=QA001")
    const notas = Array.isArray(notasPayload)
      ? notasPayload
      : notasPayload?.notas || notasPayload?.results || notasPayload?.data || []
    expect(
      notas.some((nota: Record<string, unknown>) => {
        return (
          String(nota?.materia || "").toLowerCase().includes(materia.toLowerCase()) &&
          String(nota?.fecha || "").startsWith(today) &&
          (String(nota?.calificacion || "") === "9" ||
            String(nota?.nota_numerica || "").startsWith("9") ||
            String(nota?.calificacion || "").startsWith("9"))
        )
      })
    ).toBeTruthy()
    expect(failures).toEqual([])
  })

  test("preceptor registra asistencia tarde y queda persistida", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const today = localDateString()

    await loginAs(page, "qa_preceptor")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/pasar_asistencia")
    await expect(page.getByRole("heading", { name: /asistencia/i })).toBeVisible()

    await expect(page.getByText(/cargando alumnos/i)).toBeHidden({ timeout: 15_000 })
    await page.locator("#fecha").fill(today)
    await expect(page.getByText(/ana.*qa|qa.*ana/i)).toBeVisible()

    const anaRow = page.getByRole("row", { name: /ana.*qa|qa.*ana/i })
    await anaRow.locator('input[type="radio"]').nth(2).check()

    const saveResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/asistencias/registrar") && response.status() < 400
    })
    await page.getByRole("button", { name: /guardar asistencia/i }).click()
    await saveResponse
    await expect(page.getByText(/asistencia guardada/i)).toBeVisible()

    const data = await apiJson<any>(page, `/api/asistencias/alumno_codigo/QA001/?tipo=clases`)
    const list = Array.isArray(data) ? data : data?.asistencias || data?.results || []
    expect(
      list.some((item: any) => {
        return (
          String(item?.fecha || "").startsWith(today) &&
          (item?.tarde === true ||
            String(item?.estado || item?.status || item?.asistencia || "").toLowerCase().includes("tarde"))
        )
      })
    ).toBeTruthy()
    expect(failures).toEqual([])
  })

  test("profesor envia mensaje a familia y el padre lo ve en bandeja", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const subject = uniqueQaText("Mensaje E2E familia")
    const body = uniqueQaText("Contenido E2E familia")

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/mensajes")
    await expect(page.getByRole("heading", { name: /mensajes/i })).toBeVisible()

    await page.getByRole("button", { name: /mensaje nuevo/i }).click()
    await page.getByRole("button", { name: /a la familia/i }).click()
    await expect(page.getByRole("heading", { name: /comunicado a familias/i })).toBeVisible()

    await selectOptionMatching(page.locator("#curso"), /1A/)
    await selectOptionMatching(page.locator("#dest"), /ana.*qa|qa.*ana/i)
    await page.locator("#asunto").fill(subject)
    await page.locator("#msg").fill(body)

    const sendResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/mensajes/enviar") && response.status() < 400
    })
    await page.getByRole("button", { name: /^enviar$/i }).click()
    await sendResponse
    await expect(page.getByText(/comunicado enviado/i)).toBeVisible()

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/mensajes")
    await expect(page.getByRole("heading", { name: /mensajes/i })).toBeVisible()
    await expect(page.getByText(subject)).toBeVisible()

    const inbox = await apiJson<any>(page, "/api/mensajes/recibidos/")
    const list = Array.isArray(inbox) ? inbox : inbox?.mensajes || inbox?.results || []
    expect(list.some((message: any) => String(message?.asunto || "").includes(subject))).toBeTruthy()
    expect(failures).toEqual([])
  })

  test("profesor registra sancion y el padre la firma", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const today = localDateString()
    const motivo = uniqueQaText("Sancion E2E")

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.getByRole("button", { name: /nueva sanci/i })).toBeVisible()
    await page.getByRole("button", { name: /nueva sanci/i }).click()
    await expect(page.getByRole("heading", { name: /nueva sanci/i })).toBeVisible()
    await expect.poll(async () => {
      return page.locator("#cursoSan").evaluate((select) => (select as HTMLSelectElement).options.length)
    }).toBeGreaterThan(1)
    await selectOptionMatching(page.locator("#cursoSan"), /1A/)
    await expect(page.locator("#alumnoSan")).toBeEnabled({ timeout: 15_000 })
    await selectOptionMatching(page.locator("#alumnoSan"), /ana.*qa|qa.*ana|QA001/i)
    await page.locator("#fechaSan").fill(today)
    await page.locator("#mensajeSan").fill(motivo)

    const createResponse = page.waitForResponse((response) => {
      return (
        response.url().includes("/api/sanciones") &&
        response.request().method() === "POST" &&
        response.status() >= 200 &&
        response.status() < 300
      )
    })
    await page.getByRole("button", { name: /guardar sanci/i }).click()
    await createResponse

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/alumnos/QA001?from=mis-sanciones&tab=sanciones")

    const sanctionRow = page.getByRole("row", { name: new RegExp(motivo, "i") })
    await expect(sanctionRow).toBeVisible({ timeout: 15_000 })
    const signResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/sanciones/") && response.url().includes("/firmar") && response.status() < 400
    })
    await sanctionRow.getByRole("button", { name: /^firmar$/i }).click()
    await signResponse
    await expect(sanctionRow.getByText(/firmada/i)).toBeVisible()

    const payload = await apiJson<any>(page, "/api/sanciones/?alumno=QA001")
    const sanciones = Array.isArray(payload) ? payload : payload?.results || []
    expect(
      sanciones.some((sancion: any) => {
        return String(sancion?.motivo || sancion?.mensaje || "").includes(motivo) && sancion?.firmada === true
      })
    ).toBeTruthy()
    expect(failures).toEqual([])
  })

  test("padre responde un mensaje en hilo y el profesor ve la respuesta", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const subject = uniqueQaText("Hilo E2E familia")
    const body = uniqueQaText("Mensaje inicial hilo E2E")
    const reply = uniqueQaText("Respuesta padre hilo E2E")

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/mensajes")
    await page.getByRole("button", { name: /mensaje nuevo/i }).click()
    await page.getByRole("button", { name: /a la familia/i }).click()
    await selectOptionMatching(page.locator("#curso"), /1A/)
    await selectOptionMatching(page.locator("#dest"), /ana.*qa|qa.*ana/i)
    await page.locator("#asunto").fill(subject)
    await page.locator("#msg").fill(body)

    const sendResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/mensajes/enviar") && response.status() < 400
    })
    await page.getByRole("button", { name: /^enviar$/i }).click()
    await sendResponse
    await expect(page.getByText(/comunicado enviado/i)).toBeVisible()

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/mensajes")
    await expect(page.getByText(subject)).toBeVisible({ timeout: 15_000 })

    const inbox = await apiJson<any>(page, "/api/mensajes/recibidos/")
    const messages = Array.isArray(inbox) ? inbox : inbox?.mensajes || inbox?.results || []
    const received = messages.find((message: any) => String(message?.asunto || "").includes(subject))
    expect(received?.thread_id || received?.id).toBeTruthy()

    await page.goto(`/mensajes/hilo/${received.thread_id || received.id}`)
    await expect(page.getByText(subject)).toBeVisible()
    await page.locator("#mensaje").fill(reply)

    const replyResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/mensajes/responder") && response.status() < 400
    })
    await page.getByRole("button", { name: /enviar respuesta/i }).click()
    await replyResponse
    await expect(page.getByText(/actualizando hilo/i)).toBeVisible()

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto(`/mensajes/hilo/${received.thread_id || received.id}`)
    await expect(page.getByText(reply)).toBeVisible({ timeout: 15_000 })

    const threadUrl = received.thread_id
      ? `/api/mensajes/conversacion/thread/${received.thread_id}/`
      : `/api/mensajes/conversacion/${received.id}/`
    const thread = await apiJson<any>(page, threadUrl)
    const threadMessages = Array.isArray(thread?.mensajes) ? thread.mensajes : []
    expect(threadMessages.some((message: any) => String(message?.contenido || "").includes(reply))).toBeTruthy()
    expect(failures).toEqual([])
  })
})
