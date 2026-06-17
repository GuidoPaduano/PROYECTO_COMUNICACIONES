import { expect, test, type Locator, type Page } from "@playwright/test"

import { loginAs, QA_PASSWORD, QA_SCHOOL, watchRuntimeFailures } from "./helpers"

async function tabUntilFocused(page: Page, locator: Locator, maxTabs = 12) {
  for (let attempt = 0; attempt < maxTabs; attempt += 1) {
    await page.keyboard.press("Tab")
    if (await locator.evaluate((element) => element === document.activeElement)) return
  }
  await expect(locator).toBeFocused()
}

test.describe("QA teclado y semantica para lectores de pantalla", () => {
  test("los errores de login se anuncian y quedan asociados a los campos", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await page.route("**/api/token", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Credenciales de prueba invalidas" }),
      })
    })
    await page.goto(`/login?school=${QA_SCHOOL}`)
    await page.getByLabel("Usuario").fill("usuario_invalido")
    await page.getByLabel(/Contrase.a$/i).fill("clave_invalida")
    await page.getByRole("button", { name: "Ingresar" }).click()

    const alert = page.locator("#login-error")
    await expect(alert).toHaveText("Credenciales de prueba invalidas")
    await expect(page.getByLabel("Usuario")).toHaveAttribute("aria-invalid", "true")
    await expect(page.getByLabel("Usuario")).toHaveAttribute("aria-describedby", "login-error")
    await expect(page.getByLabel(/Contrase.a$/i)).toHaveAttribute("aria-invalid", "true")
    expect(failures).toEqual([])
  })

  test("recuperacion de contrasena anuncia error y resultado exitoso", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    let shouldFail = true
    await page.route("**/api/auth/password-reset/", async (route) => {
      await route.fulfill({
        status: shouldFail ? 503 : 200,
        contentType: "application/json",
        body: JSON.stringify({
          detail: shouldFail ? "Servicio de correo no conectado" : "Solicitud registrada",
        }),
      })
    })
    await page.goto(`/forgot-password?school=${QA_SCHOOL}`)
    const email = page.getByLabel("Email")
    await email.fill("qa@example.com")
    await page.getByRole("button", { name: "Enviar link" }).click()
    await expect(page.locator("#forgot-password-error")).toHaveText("Servicio de correo no conectado")
    await expect(email).toHaveAttribute("aria-invalid", "true")

    shouldFail = false
    await page.getByRole("button", { name: "Enviar link" }).click()
    await expect(page.getByRole("status")).toHaveText("Solicitud registrada")
    await expect(email).not.toHaveAttribute("aria-invalid", "true")
    expect(
      failures.filter(
        (failure) => !failure.includes("503 ") || !failure.includes("/api/auth/password-reset/")
      )
    ).toEqual([])
  })

  test("la validacion de nueva contrasena expone un aviso asociado", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await page.goto(`/reset-password?school=${QA_SCHOOL}&uid=qa&token=qa-token`)
    await page.getByLabel(/Contrase.a nueva/i).fill("QaLocal123!")
    await page.getByLabel(/Repetir contrase.a/i).fill("OtraClave123!")
    await page.getByRole("button", { name: /Actualizar contrase.a/i }).click()

    await expect(page.locator("#reset-password-error")).toContainText(/no coinciden/i)
    await expect(page.getByLabel(/Contrase.a nueva/i)).toHaveAttribute(
      "aria-describedby",
      "reset-password-error"
    )
    await expect(page.getByLabel(/Repetir contrase.a/i)).toHaveAttribute("aria-invalid", "true")
    expect(failures).toEqual([])
  })

  test("el login se completa usando solo teclado", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await page.goto(`/login?school=${QA_SCHOOL}`)
    await expect(page.getByText(/entrar a QA Local/i)).toBeVisible()

    await page.keyboard.press("Tab")
    await expect(page.getByLabel("Usuario")).toBeFocused()
    await page.keyboard.type("qa_profesor")
    await page.keyboard.press("Tab")
    await expect(page.getByLabel("Contraseña")).toBeFocused()
    await page.keyboard.type(QA_PASSWORD)
    await page.keyboard.press("Tab")

    const submit = page.getByRole("button", { name: "Ingresar" })
    await expect(submit).toBeFocused()
    await page.keyboard.press("Enter")

    await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 })
    await expect(page.getByRole("heading", { name: /qa profesor/i })).toBeVisible()
    expect(failures).toEqual([])
  })

  test("el enlace de salto evita recorrer toda la barra lateral", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_padre")
    await page.goto("/dashboard")

    const skipLink = page.getByRole("link", { name: "Saltar al contenido principal" })
    await tabUntilFocused(page, skipLink)
    await expect(skipLink).toBeFocused()
    await expect(skipLink).toBeVisible()
    await page.keyboard.press("Enter")

    const main = page.getByRole("main")
    await expect(main).toBeFocused()
    await expect(main).toHaveAttribute("id", "contenido-principal")
    expect(failures).toEqual([])
  })

  test("la campana conserva un indicador de foco visible", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_padre")
    await page.goto("/dashboard")

    const bell = page.getByRole("button", { name: /Abrir notificaciones/i })
    await tabUntilFocused(page, bell)
    await expect(bell).toBeFocused()
    const outlineStyle = await bell.evaluate((element) => getComputedStyle(element).outlineStyle)
    expect(outlineStyle).not.toBe("none")
    expect(failures).toEqual([])
  })

  test("un mensaje se abre con teclado y Escape restaura el foco", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_profesor")
    await page.goto("/mensajes")
    await expect(page.getByRole("heading", { name: "Mensajes" })).toBeVisible()

    const messageButton = page.getByRole("button", { name: /^Abrir mensaje:/ }).first()
    await expect(messageButton).toBeVisible()
    await messageButton.focus()
    await page.keyboard.press("Enter")

    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole("heading")).toBeVisible()
    await page.keyboard.press("Escape")
    await expect(dialog).toBeHidden()
    await expect(messageButton).toBeFocused()
    expect(failures).toEqual([])
  })

  test("los controles de branding exponen nombres accesibles", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_platform_admin")
    await page.goto("/admin/plataforma/colegios")
    await expect(page.getByRole("heading", { name: "Colegios" })).toBeVisible()

    await expect(page.getByLabel("Selector de color principal")).toBeVisible()
    await expect(page.getByLabel("Color principal", { exact: true })).toBeVisible()
    await expect(page.getByLabel("Selector de color de acento")).toBeVisible()
    await expect(page.getByLabel("Color de acento", { exact: true })).toBeVisible()
    await expect(page.getByRole("button", { name: /Guardar cambios/i })).toBeVisible()
    expect(failures).toEqual([])
  })

  test("las rutas principales tienen un unico h1 y no saltan niveles de encabezado", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_platform_admin")

    for (const path of [
      "/dashboard",
      "/mensajes",
      "/admin/colegio/nuevo-usuario",
      "/admin/plataforma/colegios",
      "/admin/plataforma/alumnos/importar",
    ]) {
      await page.goto(path)
      await expect(page.getByRole("main")).toBeVisible()
      const levels = await page.locator("h1, h2, h3, h4, h5, h6").evaluateAll((headings) =>
        headings
          .filter((heading) => {
            const style = getComputedStyle(heading)
            return (
              style.display !== "none" &&
              style.visibility !== "hidden" &&
              heading.getClientRects().length > 0
            )
          })
          .map((heading) => Number(heading.tagName.slice(1)))
      )
      expect(levels.filter((level) => level === 1), `${path}: niveles ${levels.join(",")}`).toHaveLength(1)
      for (let index = 1; index < levels.length; index += 1) {
        expect(
          levels[index] - levels[index - 1],
          `${path}: salto de h${levels[index - 1]} a h${levels[index]}`
        ).toBeLessThanOrEqual(1)
      }
    }
    expect(failures).toEqual([])
  })
})
