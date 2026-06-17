import { expect, test, type Page } from "@playwright/test"

import { loginAs, watchRuntimeFailures } from "./helpers"

async function loginAsPlatformAdmin(page: Page) {
  await loginAs(page, "qa_platform_admin")
  await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)
}

test.describe("QA accesibilidad administrativa", () => {
  test("los errores de alta se anuncian como alertas", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/colegios/nuevo")

    await page.getByLabel("Nombre", { exact: true }).fill("Colegio duplicado accesible")
    await page.route("**/api/admin/schools/**", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({
          errors: { name: ["Ya existe un colegio con ese nombre."] },
        }),
      })
    })

    await page.getByRole("button", { name: "Crear colegio" }).click()
    await expect(
      page.getByRole("alert").filter({ hasText: "Ya existe un colegio con ese nombre." })
    ).toBeVisible()
    expect(failures).toEqual([])
  })

  test("un colegio puede seleccionarse usando solo teclado", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await page.route("**/api/admin/school-admins**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          schools: [
            {
              id: 8101,
              name: "Colegio teclado A",
              slug: "teclado-a",
              is_active: true,
              admins_count: 0,
              admins: [],
            },
            {
              id: 8102,
              name: "Colegio teclado B",
              slug: "teclado-b",
              is_active: true,
              admins_count: 0,
              admins: [],
            },
          ],
          users: [],
        }),
      })
    })

    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/admins")
    const secondSchool = page.getByRole("button", { name: /Colegio teclado B/i })
    await secondSchool.focus()
    await expect(secondSchool).toBeFocused()
    await secondSchool.press("Enter")

    await expect(secondSchool).toHaveAttribute("aria-pressed", "true")
    await expect(page.getByText("Colegio teclado B", { exact: true })).toHaveCount(2)
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeEnabled()
    expect(failures).toEqual([])
  })

  test("menu y dialogo destructivo gestionan foco y Escape", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/colegios")
    await expect(page.getByRole("heading", { name: "Colegios" })).toBeVisible()

    const trigger = page.getByRole("button", { name: "Acciones para Colegio QA Local" })
    await trigger.focus()
    await trigger.press("Enter")
    const deleteItem = page.getByRole("menuitem", { name: "Borrar colegio" })
    await expect(deleteItem).toBeFocused()
    await deleteItem.press("Enter")
    await expect(deleteItem).toBeHidden()

    const dialog = page.getByRole("dialog")
    await expect(dialog.getByRole("heading", { name: /seguro que quiere borrar/i })).toBeVisible()
    await expect(dialog).toHaveAccessibleDescription("Esta acción es irreversible.")
    await page.keyboard.press("Escape")
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    expect(failures).toEqual([])
  })

  test("dialogo de nuevo alumno tiene descripcion y restaura el foco", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)
    await page.goto("/admin/colegio/nuevo-usuario")
    await expect(page.getByRole("heading", { name: "Nuevo usuario" })).toBeVisible()

    await page.getByText("Alumno/a", { exact: true }).click()
    const trigger = page.getByRole("button", { name: "Crear alumno" })
    await expect(trigger).toBeEnabled()
    await trigger.focus()
    await trigger.press("Enter")

    const dialog = page.getByRole("dialog")
    await expect(dialog.getByRole("heading", { name: "Crear alumno" })).toBeVisible()
    await expect(dialog).toHaveAccessibleDescription(
      "Completa los datos del alumno y asignalo a un curso del colegio."
    )
    await expect(dialog.getByLabel("Apellido")).toBeFocused()
    await page.keyboard.press("Escape")
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    expect(failures).toEqual([])
  })
})
