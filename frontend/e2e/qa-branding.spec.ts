import { expect, test, type Page } from "@playwright/test"

import { apiResponse, loginAs, watchRuntimeFailures } from "./helpers"

function compactId(prefix: string) {
  return `${prefix}${Date.now().toString().slice(-8)}`
}

async function deleteSchool(page: Page, schoolId: number) {
  const deletion = await apiResponse<any>(page, `/api/admin/schools/${schoolId}/`, {
    method: "DELETE",
  })
  if (!deletion.ok || !deletion.data?.job?.id) return

  await expect
    .poll(
      async () => {
        const status = await apiResponse<any>(
          page,
          `/api/admin/school-deletion-jobs/${deletion.data.job.id}/`
        )
        return status.data?.job?.status
      },
      { timeout: 30_000 }
    )
    .toBe("completed")
}

test.describe("QA branding multi-colegio", () => {
  test("previsualiza, persiste y aisla el branding entre colegios", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const token = Date.now().toString().slice(-8)
    const firstSlug = compactId("brand-a-").toLowerCase()
    const secondSlug = compactId("brand-b-").toLowerCase()
    const firstName = `Colegio Branding A ${token}`
    const secondName = `Colegio Branding B ${token}`
    const editedShortName = `Marca A ${token}`
    const logoUrl = "/imagenes/Logo%20Color.png"
    const primaryColor = "#7C3AED"
    const accentColor = "#EA580C"
    let firstSchoolId = 0
    let secondSchoolId = 0

    await loginAs(page, "qa_platform_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)

    try {
      const first = await apiResponse<any>(page, "/api/admin/schools/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: firstName,
          short_name: `A ${token}`,
          slug: firstSlug,
          primary_color: "#1D4ED8",
          accent_color: "#16A34A",
          is_active: true,
        }),
      })
      expect(first.status, JSON.stringify(first.data)).toBe(201)
      firstSchoolId = Number(first.data.school.id)

      const second = await apiResponse<any>(page, "/api/admin/schools/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: secondName,
          short_name: `Marca B ${token}`,
          slug: secondSlug,
          primary_color: "#0F766E",
          accent_color: "#CA8A04",
          is_active: true,
        }),
      })
      expect(second.status, JSON.stringify(second.data)).toBe(201)
      secondSchoolId = Number(second.data.school.id)

      await page.goto("/admin/plataforma/colegios")
      await page.getByPlaceholder(/buscar por nombre/i).fill(firstSlug)
      await page.getByRole("row").filter({ hasText: firstSlug }).click()

      await page.getByLabel("Nombre corto").fill(editedShortName)
      await page.getByLabel("Logo URL").fill(`/imagenes/logo-inexistente-${token}.png`)
      const preview = page.getByLabel("Vista previa del branding")
      await expect(preview.getByAltText(`Vista previa del logo de ${firstName}`)).toHaveAttribute(
        "src",
        "/imagenes/Logo%20Color.png"
      )

      await page.getByLabel("Logo URL").fill(logoUrl)
      await page.getByLabel("Color principal", { exact: true }).fill(primaryColor)
      await page.getByLabel("Color de acento", { exact: true }).fill(accentColor)

      await expect(preview).toContainText(editedShortName)
      await expect(preview.getByAltText(`Vista previa del logo de ${firstName}`)).toHaveAttribute(
        "src",
        logoUrl
      )
      await expect(preview.getByText("Principal")).toHaveCSS("background-color", "rgb(124, 58, 237)")
      await expect(preview.getByText("Acento")).toHaveCSS("background-color", "rgb(234, 88, 12)")

      await page.getByRole("button", { name: "Guardar cambios" }).click()
      await expect(page.getByText("Colegio actualizado.")).toBeVisible()
      await page.reload()
      await page.getByPlaceholder(/buscar por nombre/i).fill(firstSlug)
      await page.getByRole("row").filter({ hasText: firstSlug }).click()
      await expect(page.getByLabel("Nombre corto")).toHaveValue(editedShortName)
      await expect(page.getByLabel("Logo URL")).toHaveValue(logoUrl)
      await expect(page.getByLabel("Color principal", { exact: true })).toHaveValue(primaryColor)
      await expect(page.getByLabel("Color de acento", { exact: true })).toHaveValue(accentColor)

      await page.goto(`/login?school=${firstSlug}`)
      await expect(page.getByText(new RegExp(`entrar a ${editedShortName}`, "i"))).toBeVisible()
      await expect(page.getByRole("button", { name: /ingresar/i })).toHaveCSS(
        "background-color",
        "rgb(124, 58, 237)"
      )

      await page.goto(`/forgot-password?school=${firstSlug}`)
      await expect(page.getByText(new RegExp(`acceso a ${editedShortName}`, "i"))).toBeVisible()

      await page.goto(`/login?school=${firstSlug}`)
      await page.getByLabel(/usuario/i).fill("qa_platform_admin")
      await page.getByLabel(/contrase/i).fill("QaLocal123!")
      await page.getByRole("button", { name: /ingresar/i }).click()
      await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)
      await expect(page.locator(".app-shell")).toHaveCSS("--school-primary", primaryColor.toLowerCase())
      await expect(page.locator(".sidebar-brand")).toContainText(editedShortName)

      await page.goto(`/login?school=${secondSlug}`)
      await expect(page.getByText(new RegExp(`entrar a Marca B ${token}`, "i"))).toBeVisible()
      await expect(page.getByText(new RegExp(`entrar a ${editedShortName}`, "i"))).toHaveCount(0)
      await expect(page.getByRole("button", { name: /ingresar/i })).toHaveCSS(
        "background-color",
        "rgb(15, 118, 110)"
      )
    } finally {
      await loginAs(page, "qa_platform_admin")
      await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)
      if (firstSchoolId) await deleteSchool(page, firstSchoolId)
      if (secondSchoolId) await deleteSchool(page, secondSchoolId)
    }

    expect(failures).toEqual([])
  })

  test("rechaza colores invalidos y conserva los valores guardados", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_platform_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)
    await page.goto("/admin/plataforma/colegios")
    await page.getByPlaceholder(/buscar por nombre/i).fill("qa-local")
    await page.getByRole("row").filter({ hasText: "qa-local" }).click()

    const originalPrimary = await page.getByLabel("Color principal", { exact: true }).inputValue()
    await page.getByLabel("Color principal", { exact: true }).fill("violeta")
    await page.getByRole("button", { name: "Guardar cambios" }).click()

    await expect(page.getByText(/primary_color: usa un color hexadecimal/i)).toBeVisible()
    await page.reload()
    await page.getByPlaceholder(/buscar por nombre/i).fill("qa-local")
    await page.getByRole("row").filter({ hasText: "qa-local" }).click()
    await expect(page.getByLabel("Color principal", { exact: true })).toHaveValue(originalPrimary)
    expect(failures).toEqual([])
  })
})
