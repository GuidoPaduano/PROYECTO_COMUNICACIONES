import { expect, test, type Page } from "@playwright/test"

import { loginAs, watchRuntimeFailures } from "./helpers"

async function expectNoHorizontalOverflow(page: Page) {
  await expect
    .poll(async () =>
      page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        content: document.documentElement.scrollWidth,
      }))
    )
    .toEqual(
      expect.objectContaining({
        viewport: 390,
        content: 390,
      })
    )
}

test.describe("QA resiliencia administrativa", () => {
  test("directorio recupera un error 503 al actualizar", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    let failedOnce = false
    await page.route("**/api/admin/school-users**", async (route) => {
      if (!failedOnce) {
        failedOnce = true
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Directorio temporalmente no disponible" }),
        })
        return
      }
      await route.continue()
    })

    await loginAs(page, "qa_school_admin")
    await page.goto("/admin/colegio/usuarios")
    await expect(page.getByText("Directorio temporalmente no disponible")).toBeVisible()
    await page.getByRole("button", { name: /actualizar/i }).click()
    await expect(page.getByRole("heading", { name: "Usuarios del colegio" })).toBeVisible()
    await expect(page.getByRole("button", { name: /Alumnos\s+\d+/ })).toBeVisible()
    expect(failures).toEqual([expect.stringMatching(/^503 .*\/api\/admin\/school-users/)])
  })

  test("asignaciones recuperan un error 503 y muestran estado vacio", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    let requestCount = 0
    await page.route("**/api/admin/staff**", async (route) => {
      requestCount += 1
      if (requestCount === 1) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Personal temporalmente no disponible" }),
        })
        return
      }
      if (requestCount === 2) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            school: { id: 1, name: "Colegio QA Local", short_name: "QA Local", slug: "qa-local" },
            courses: [],
            users: [],
          }),
        })
        return
      }
      await route.continue()
    })

    await loginAs(page, "qa_school_admin")
    await page.goto("/admin/colegio/asignacion-profesores")
    await expect(page.getByText("Personal temporalmente no disponible")).toBeVisible()
    await page.getByRole("button", { name: /recargar/i }).click()
    await expect(page.getByText("No hay cursos disponibles para este colegio.")).toBeVisible()
    expect(failures).toEqual([expect.stringMatching(/^503 .*\/api\/admin\/staff/)])
  })

  test("alta de usuario conserva el formulario ante validacion 400", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_school_admin")
    await page.goto("/admin/colegio/nuevo-usuario")
    await expect(page.getByRole("heading", { name: "Nuevo usuario" })).toBeVisible()

    await page.getByLabel("Apellido").fill("Duplicado")
    await page.getByLabel("Nombre").fill("Usuario")
    await page.getByRole("textbox", { name: "Usuario" }).fill("qa_school_admin")
    await page.getByLabel("Contraseña", { exact: true }).fill("QaLocal123!")
    await page.getByLabel("Confirmar contraseña").fill("QaLocal123!")
    await page.getByText("Administrador/a de colegio", { exact: true }).click()
    await page.getByRole("button", { name: "Crear usuario" }).click()

    await expect(page.getByText(/ya existe un usuario/i)).toBeVisible()
    await expect(page.getByRole("textbox", { name: "Usuario" })).toHaveValue("qa_school_admin")
    await expect(page.getByLabel("Apellido")).toHaveValue("Duplicado")
    expect(failures).toEqual([])
  })

  test("profesor recibe acceso restringido en cursos y directorio", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    for (const path of ["/admin/colegio/cursos", "/admin/colegio/usuarios"]) {
      await page.goto(path)
      await expect(page.getByText(/acceso restringido/i)).toBeVisible()
    }
    expect(failures).toEqual([])
  })

  test("formularios administrativos no desbordan en mobile", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)

    for (const { path, heading } of [
      { path: "/admin/colegio/nuevo-usuario", heading: "Nuevo usuario" },
      { path: "/admin/colegio/usuarios", heading: "Usuarios del colegio" },
      {
        path: "/admin/colegio/asignacion-profesores",
        heading: "Asignacion a profesores",
      },
      { path: "/admin/colegio/cursos", heading: "Cursos por colegio" },
    ]) {
      await page.goto(path)
      await expect(page.getByRole("heading", { name: heading })).toBeVisible()
      await expectNoHorizontalOverflow(page)
    }
    expect(failures).toEqual([])
  })
})
