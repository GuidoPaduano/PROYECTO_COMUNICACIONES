import { readFile } from "node:fs/promises"

import { expect, test, type Download, type Page } from "@playwright/test"

import { loginAs, selectOptionMatching, watchRuntimeFailures } from "./helpers"

test.describe("QA descargas, landscape y tactil", () => {
  test.use({ hasTouch: true })
  test.skip(({ browserName }) => browserName === "webkit", "WebKit bloqueado en el runner Windows local")

  test("padre descarga los PDF de la ficha academica", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_padre")
    await page.goto("/alumnos/QA001?tab=notas")
    await expect(page.getByRole("heading", { name: /ana qa/i })).toBeVisible()

    await expectPdfDownload(page, /^notas_ana_qa_\d{4}-\d{2}-\d{2}\.pdf$/)

    await page.getByRole("tab", { name: "Sanciones" }).click()
    await expect(page.getByRole("tabpanel", { name: "Sanciones" })).toBeVisible()
    await expectPdfDownload(page, /^sanciones_ana_qa_\d{4}-\d{2}-\d{2}\.pdf$/)

    await page.getByRole("tab", { name: "Inasistencias" }).click()
    await expect(page.getByRole("tabpanel", { name: "Inasistencias" })).toBeVisible()
    await expectPdfDownload(page, /^inasistencias_ana_qa_\d{4}-\d{2}-\d{2}\.pdf$/)

    expect(failures).toEqual([])
  })

  for (const viewport of [
    { name: "mobile landscape", width: 844, height: 390 },
    { name: "tablet landscape", width: 1180, height: 820 },
  ]) {
    test(`mensajes y ficha no desbordan en ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      const failures = watchRuntimeFailures(page)

      await loginAs(page, "qa_padre")
      await page.goto("/alumnos/QA001?tab=notas")
      await expect(page.getByRole("heading", { name: /ana qa/i })).toBeVisible()
      await expectNoHorizontalOverflow(page)

      await page.goto("/mensajes")
      await expect(page.getByRole("heading", { name: /mensajes/i })).toBeVisible()
      await expectNoHorizontalOverflow(page)

      expect(failures).toEqual([])
    })
  }

  test("formulario de mensaje responde a interaccion tactil en landscape", async ({
    page,
    browserName,
  }) => {
    test.skip(browserName !== "chromium", "La emulacion movil tactil de Playwright requiere Chromium")

    await page.setViewportSize({ width: 844, height: 390 })
    const failures = watchRuntimeFailures(page)
    const forbiddenCourseLoads: string[] = []
    page.on("response", (response) => {
      if (response.status() === 403 && response.url().includes("/api/alumnos?")) {
        forbiddenCourseLoads.push(response.url())
      }
    })

    await loginWithSingleRetry(page, "qa_profesor")
    await page.goto("/mensajes")
    await page.getByRole("button", { name: /mensaje nuevo/i }).tap()
    await page.getByRole("button", { name: /a la familia/i }).tap()
    await expect(page.getByRole("heading", { name: /comunicado a familias/i })).toBeVisible()

    await selectOptionMatching(page.locator("#curso"), /1A/)
    await selectOptionMatching(page.locator("#dest"), /ana.*qa|qa.*ana/i)
    await page.locator("#asunto").tap()
    await page.locator("#asunto").fill("Prueba tactil sin envio")
    await page.locator("#msg").tap()
    await page.locator("#msg").fill("El formulario acepta foco y escritura tactil.")

    await expect(page.locator("#asunto")).toHaveValue("Prueba tactil sin envio")
    await expect(page.locator("#msg")).toHaveValue("El formulario acepta foco y escritura tactil.")
    await expectNoHorizontalOverflow(page)
    expect(forbiddenCourseLoads).toEqual([])
    expect(failures).toEqual([])
  })
})

async function expectPdfDownload(page: Page, fileName: RegExp) {
  const downloadPromise = page.waitForEvent("download")
  await page.getByRole("button", { name: /descargar en pdf/i }).click()
  const download = await downloadPromise
  await expectPdfFile(download, fileName)
}

async function loginWithSingleRetry(page: Page, username: string) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await loginAs(page, username)
    try {
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 })
      return
    } catch (error) {
      if (attempt === 1) throw error
    }
  }
}

async function expectPdfFile(download: Download, fileName: RegExp) {
  expect(download.suggestedFilename()).toMatch(fileName)
  const downloadPath = await download.path()
  expect(downloadPath).toBeTruthy()
  const contents = await readFile(downloadPath!)
  expect(contents.length).toBeGreaterThan(500)
  expect(contents.subarray(0, 5).toString("ascii")).toBe("%PDF-")
}

async function expectNoHorizontalOverflow(page: Page) {
  const widths = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  expect(widths.scrollWidth).toBeLessThanOrEqual(widths.clientWidth + 1)
}
