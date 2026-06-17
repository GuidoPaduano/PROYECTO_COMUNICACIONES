import { expect, test, type Page } from "@playwright/test"

import { loginAs, watchRuntimeFailures } from "./helpers"

async function loginAsPlatformAdmin(page: Page) {
  await loginAs(page, "qa_platform_admin")
  await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect
    .poll(async () =>
      page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        content: document.documentElement.scrollWidth,
      }))
    )
    .toEqual(expect.objectContaining({ viewport: 390, content: 390 }))
}

test.describe("QA alta de colegios y administradores", () => {
  test("admin de colegio recibe acceso restringido al alta global", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)
    await page.goto("/admin/plataforma/colegios/nuevo")
    await expect(page.getByText(/acceso restringido/i)).toBeVisible()
    expect(failures).toEqual([])
  })

  test("alta conserva el formulario ante un colegio duplicado", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/colegios/nuevo")
    await expect(page.getByRole("heading", { name: "Nuevo colegio" })).toBeVisible()

    await page.getByLabel("Nombre", { exact: true }).fill("Colegio QA Local")
    await page.getByLabel("Nombre corto").fill("QA duplicado")
    await page.getByLabel("Slug").fill("qa-local-duplicado")
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

    const createButton = page.getByRole("button", { name: "Crear colegio" })
    await createButton.click()
    await expect(page.locator(".border-red-200").filter({ hasText: /Ya existe un colegio/ })).toBeVisible()
    await expect(createButton).toBeEnabled()
    await expect(page.getByLabel("Nombre", { exact: true })).toHaveValue("Colegio QA Local")
    await expect(page.getByLabel("Nombre corto")).toHaveValue("QA duplicado")
    await expect(page.getByLabel("Slug")).toHaveValue("qa-local-duplicado")
    expect(failures).toEqual([])
  })

  test("admins por colegio presenta estados vacios explicitos", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await page.route("**/api/admin/school-admins**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ schools: [], users: [] }),
      })
    })

    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/admins")
    await expect(page.getByText("No hay colegios para mostrar.")).toBeVisible()
    await expect(page.getByText("Busca un usuario para asignarlo como administrador.")).toBeVisible()
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeDisabled()
    expect(failures).toEqual([])
  })

  test("error al guardar administradores conserva la seleccion", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const school = {
      id: 7001,
      name: "Colegio administradores QA",
      short_name: "Admins QA",
      slug: "admins-qa",
      is_active: true,
      admins_count: 1,
      admins: [
        {
          id: 7101,
          username: "admin_actual",
          full_name: "Admin Actual",
          email: "actual@qa.local",
          is_active: true,
        },
      ],
    }
    const users = [
      ...school.admins,
      {
        id: 7102,
        username: "admin_nuevo",
        full_name: "Admin Nuevo",
        email: "nuevo@qa.local",
        is_active: true,
      },
    ]
    await page.route("**/api/admin/school-admins**", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ schools: [school], users }),
        })
        return
      }
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Uno o más usuarios no son asignables." }),
      })
    })

    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/admins")
    const currentAdmin = page.getByRole("checkbox", { name: /Admin Actual/i })
    const newAdmin = page.getByRole("checkbox", { name: /Admin Nuevo/i })
    await expect(currentAdmin).toBeChecked()
    await newAdmin.check()
    await page.getByRole("button", { name: "Guardar cambios" }).click()

    await expect(page.getByText("Uno o más usuarios no son asignables.")).toBeVisible()
    await expect(currentAdmin).toBeChecked()
    await expect(newAdmin).toBeChecked()
    await expect(page.getByText("2 admins seleccionados")).toBeVisible()
    expect(failures).toEqual([])
  })

  test("descarga de plantilla permite reintentar despues de un 503", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    let attempts = 0
    await page.route("**/api/admin/alumnos/import/template**", async (route) => {
      attempts += 1
      if (attempts === 1) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Plantilla temporalmente no disponible" }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        body: "qa-template",
      })
    })

    await loginAsPlatformAdmin(page)
    await page.goto("/admin/plataforma/alumnos/importar")
    await page.getByRole("button", { name: "Descargar plantilla" }).click()
    await expect(page.getByText("Plantilla temporalmente no disponible")).toBeVisible()

    const downloadPromise = page.waitForEvent("download")
    await page.getByRole("button", { name: "Descargar plantilla" }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe("plantilla-importacion-alumnos.xlsx")
    await expect(page.getByText("Plantilla temporalmente no disponible")).toBeHidden()
    expect(failures).toEqual([expect.stringMatching(/^503 .*\/api\/admin\/alumnos\/import\/template/)])
  })

  test("formularios de plataforma no desbordan en mobile", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await loginAsPlatformAdmin(page)

    for (const { path, heading } of [
      { path: "/admin/plataforma/colegios/nuevo", heading: "Nuevo colegio" },
      { path: "/admin/plataforma/admins", heading: "Admins por colegio" },
      { path: "/admin/plataforma/alumnos/importar", heading: "Importar alumnos" },
      { path: "/admin/plataforma/colegios", heading: "Colegios" },
    ]) {
      await page.goto(path)
      await expect(page.getByRole("heading", { name: heading })).toBeVisible()
      await expectNoHorizontalOverflow(page)
    }

    expect(failures).toEqual([])
  })
})
