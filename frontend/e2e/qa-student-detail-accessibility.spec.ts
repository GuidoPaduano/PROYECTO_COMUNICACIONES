import { expect, test } from "@playwright/test"

import { loginAs } from "./helpers"

test.describe("QA accesibilidad de ficha del alumno", () => {
  for (const viewport of [
    { name: "desktop", width: 1280, height: 800 },
    { name: "mobile", width: 390, height: 844 },
  ]) {
    test(`navega las secciones con teclado en ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await loginAs(page, "qa_padre")
      await page.goto("/alumnos/QA001?tab=notas")

      const tablist = page.getByRole("tablist", {
        name: "Secciones de la ficha del alumno",
      })
      const notas = tablist.getByRole("tab", { name: "Notas" })
      const sanciones = tablist.getByRole("tab", { name: "Sanciones" })
      const asistencias = tablist.getByRole("tab", { name: "Inasistencias" })

      await expect(notas).toHaveAttribute("aria-selected", "true")
      await expect(page.getByRole("tabpanel", { name: "Notas" })).toBeVisible()

      await notas.focus()
      await expect(notas).toBeFocused()
      await notas.press("ArrowRight")
      await expect(sanciones).toBeFocused()
      await expect(sanciones).toHaveAttribute("aria-selected", "true")
      await expect(page.getByRole("tabpanel", { name: "Sanciones" })).toBeVisible()

      await sanciones.press("End")
      await expect(asistencias).toBeFocused()
      await expect(asistencias).toHaveAttribute("aria-selected", "true")
      await expect(page.getByRole("tabpanel", { name: "Inasistencias" })).toBeVisible()

      await asistencias.press("Home")
      await expect(notas).toBeFocused()
      await expect(notas).toHaveAttribute("aria-selected", "true")
    })
  }

  test("anuncia errores academicos y conserva controles de reintento", async ({ page }) => {
    await loginAs(page, "qa_padre")
    await page.route(/\/api\/notas\/?\?.*/, async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Notas temporalmente no disponibles." }),
      })
    })
    await page.route(/\/api\/alumnos\/[^/]+\/notas\/?$/, async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Notas temporalmente no disponibles." }),
      })
    })

    await page.goto("/alumnos/QA001?tab=notas")

    const alert = page.getByRole("alert").filter({
      hasText: "Notas temporalmente no disponibles.",
    })
    await expect(alert).toBeVisible()
    await expect(alert.getByRole("button", { name: "Reintentar notas" })).toBeVisible()
  })
})
