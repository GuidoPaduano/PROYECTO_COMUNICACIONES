import { expect, test, type Page } from "@playwright/test"
import { loginAs, watchRuntimeFailures } from "./helpers"

test.describe("QA local smoke", () => {
  test("la home publica carga con CSS y lista el colegio QA", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    const schoolsResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/public/schools") && response.status() < 400
    })
    await page.goto("/")
    await schoolsResponse
    await expect(page.getByRole("heading", { name: /eleg/i })).toBeVisible()
    await expect(page.getByPlaceholder(/buscar por nombre/i)).toBeVisible()
    await expect(page.getByRole("heading", { name: /colegios activos/i })).toBeVisible()
    await expect(page.getByText(/cargando colegios/i)).toBeHidden()
    await expect(page.getByRole("link", { name: /qa local|colegio qa/i })).toBeVisible()

    const bodyFont = await page.locator("body").evaluate((body) => getComputedStyle(body).fontFamily)
    expect(bodyFont).not.toMatch(/Times New Roman/i)
    expect(failures).toEqual([])
  })

  test("profesor QA inicia sesion y llega al dashboard", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.getByRole("link", { name: /inicio/i })).toBeVisible()
    await expect(page.getByRole("heading", { name: /qa profesor/i })).toBeVisible()
    expect(failures).toEqual([])
  })

  test("admin de colegio QA inicia sesion y llega al panel del colegio", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/admin\/colegio/)
    await expect(page.getByRole("heading", { name: /herramientas/i })).toBeVisible()
    await expect(page.getByText(/usuarios del colegio/i)).toBeVisible()
    expect(failures).toEqual([])
  })

  test("directivo QA inicia sesion en su colegio sin acceso administrativo", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_directivo")
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.getByRole("heading", { name: /qa directivo/i })).toBeVisible()
    await expect(page.getByRole("link", { name: /admin colegio/i })).toHaveCount(0)
    await expect(page.getByRole("link", { name: /admin plataforma/i })).toHaveCount(0)
    expect(failures).toEqual([])
  })
})
