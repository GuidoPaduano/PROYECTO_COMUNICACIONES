import { expect, test } from "@playwright/test"

import { apiJson, loginAs } from "./helpers"

test.describe("QA resiliencia de ficha del alumno", () => {
  test("notas, sanciones y asistencias muestran errores independientes y permiten reintentar", async ({
    page,
  }) => {
    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)

    const payload = await apiJson<any>(page, "/api/padres/mis-hijos/")
    const hijos = Array.isArray(payload?.results)
      ? payload.results
      : Array.isArray(payload)
        ? payload
        : []
    const alumno = hijos.find((item: any) => item?.id_alumno === "QA001") || hijos[0]
    expect(alumno?.id).toBeTruthy()

    let failNotas = true
    let failSanciones = true
    let failAsistencias = true

    await page.route(/\/api\/notas\/?\?.*/, async (route) => {
      if (!failNotas) {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Notas temporalmente no disponibles." }),
      })
    })
    await page.route(/\/api\/alumnos\/[^/]+\/notas\/?$/, async (route) => {
      if (!failNotas) {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Notas temporalmente no disponibles." }),
      })
    })
    await page.route(/\/api\/sanciones\/?\?.*/, async (route) => {
      if (!failSanciones) {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Sanciones temporalmente no disponibles." }),
      })
    })
    await page.route(/\/api\/asistencias\/?\?.*/, async (route) => {
      if (!failAsistencias) {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Asistencias temporalmente no disponibles." }),
      })
    })

    await page.goto(`/alumnos/${alumno.id}?from=%2Fmis-hijos&tab=notas`)

    await expect(page.getByText("Notas temporalmente no disponibles.")).toBeVisible()
    await expect(page.getByText(/no se encontraron notas con los filtros actuales/i)).toBeHidden()

    const retryNotas = page.getByRole("button", { name: /reintentar notas/i })
    await expect(retryNotas).toBeVisible()
    failNotas = false
    await retryNotas.click()
    await expect(page.getByText("Notas temporalmente no disponibles.")).toBeHidden()

    await page.getByText("Sanciones", { exact: true }).first().click()
    await expect(page.getByText("Sanciones temporalmente no disponibles.")).toBeVisible()
    await expect(page.getByText(/no hay sanciones registradas/i)).toBeHidden()

    const retrySanciones = page.getByRole("button", { name: /reintentar sanciones/i })
    await expect(retrySanciones).toBeVisible()
    failSanciones = false
    await retrySanciones.click()
    await expect(page.getByText("Sanciones temporalmente no disponibles.")).toBeHidden()

    await page.getByText("Inasistencias", { exact: true }).first().click()
    await expect(page.getByText("Asistencias temporalmente no disponibles.")).toBeVisible()
    await expect(page.getByText(/aún no hay asistencias cargadas/i)).toBeHidden()

    const retryAsistencias = page.getByRole("button", { name: /reintentar asistencias/i })
    await expect(retryAsistencias).toBeVisible()
    failAsistencias = false
    await retryAsistencias.click()
    await expect(page.getByText("Asistencias temporalmente no disponibles.")).toBeHidden()
  })
})
