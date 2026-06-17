import { expect, test, type Page } from "@playwright/test"

import { loginAs, watchRuntimeFailures } from "./helpers"

async function loginAsPlatformAdmin(page: Page) {
  await loginAs(page, "qa_platform_admin")
  await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)
}

test.describe("QA resiliencia de administracion de plataforma", () => {
  test("admin de colegio recibe acceso restringido en herramientas globales", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)

    for (const path of [
      "/admin/plataforma/admins",
      "/admin/plataforma/alumnos/importar",
      "/admin/plataforma/colegios",
      "/admin/plataforma/cursos",
    ]) {
      await page.goto(path)
      await expect(page.getByText(/acceso restringido/i)).toBeVisible()
    }

    expect(failures).toEqual([])
  })

  test("admins por colegio recupera un error 503 al actualizar", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    let failedOnce = false
    await page.route("**/api/admin/school-admins/**", async (route) => {
      if (!failedOnce) {
        failedOnce = true
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Administradores temporalmente no disponibles" }),
        })
        return
      }
      await route.continue()
    })

    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/admins")
    await expect(page.getByText("Administradores temporalmente no disponibles")).toBeVisible()
    await page.getByRole("button", { name: /actualizar/i }).click()
    await expect(page.getByRole("heading", { name: "Admins por colegio" })).toBeVisible()
    await expect(page.getByRole("cell", { name: /qa local/i }).first()).toBeVisible()
    expect(failures).toEqual([expect.stringMatching(/^503 .*\/api\/admin\/school-admins/)])
  })

  test("edicion de colegio conserva el formulario ante validacion 400", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/colegios")
    await expect(page.getByRole("heading", { name: "Colegios" })).toBeVisible()

    const nameInput = page.getByLabel("Nombre", { exact: true })
    await expect(nameInput).not.toHaveValue("")
    const editedName = "Nombre duplicado QA"
    await nameInput.fill(editedName)

    await page.route("**/api/admin/schools/*", async (route) => {
      if (route.request().method() !== "PATCH") {
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

    await page.getByRole("button", { name: "Guardar cambios" }).click()
    await expect(page.getByText("name: Ya existe un colegio con ese nombre.")).toBeVisible()
    await expect(nameInput).toHaveValue(editedName)
    expect(failures).toEqual([])
  })

  test("borrado informa el error de un trabajo asincronico fallido", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/colegios")
    await expect(page.getByRole("heading", { name: "Colegios" })).toBeVisible()

    await page.route("**/api/admin/schools/*", async (route) => {
      if (route.request().method() !== "DELETE") {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Borrado iniciado.",
          job: { id: 987654, status: "pending" },
          available_schools: [],
        }),
      })
    })
    await page.route("**/api/admin/school-deletion-jobs/987654**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job: {
            id: 987654,
            status: "failed",
            error: "No se pudo completar el borrado de prueba.",
          },
        }),
      })
    })

    const schoolRow = page.getByRole("row").filter({ hasText: "qa-local" })
    await expect(schoolRow).toBeVisible()
    await schoolRow.getByRole("button", { name: /acciones para/i }).click()
    await page.getByRole("menuitem", { name: "Borrar colegio" }).click()
    const dialog = page.getByRole("dialog")
    await dialog.getByRole("button", { name: "Borrar colegio" }).click()

    await expect(page.getByText("No se pudo completar el borrado de prueba.")).toBeVisible()
    await expect(page.getByRole("row").filter({ hasText: "qa-local" })).toBeVisible()
    expect(failures).toEqual([])
  })

  test("importacion invalida muestra detalle y mantiene bloqueada la confirmacion", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/alumnos/importar")
    await expect(page.getByRole("heading", { name: "Importar alumnos" })).toBeVisible()

    await page.getByLabel("Excel o CSV").setInputFiles({
      name: "alumnos-invalidos.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("nombre,apellido,curso,legajo\nSinCurso,QA,,\n"),
    })
    await page.getByRole("button", { name: "Previsualizar" }).click()

    await expect(page.getByText(/0 v.lidos, 1 con error/i)).toBeVisible()
    await expect(page.getByRole("cell", { name: /falta curso/i })).toBeVisible()
    await expect(page.getByRole("button", { name: "Importar", exact: true })).toBeDisabled()
    expect(failures).toEqual([])
  })
})
