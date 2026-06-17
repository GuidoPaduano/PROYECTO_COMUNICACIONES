import { readFile } from "node:fs/promises"

import { expect, test } from "@playwright/test"

import { loginAs, watchRuntimeFailures } from "./helpers"

test.describe("QA backups y herramientas destructivas", () => {
  test("superadmin descarga un backup SQLite reconocible desde la UI", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_platform_admin")
    await page.goto("/admin/plataforma/backups")

    const downloadPromise = page.waitForEvent("download")
    await page.getByRole("button", { name: /generar backup completo/i }).click()
    const download = await downloadPromise
    const filePath = await download.path()

    expect(download.suggestedFilename()).toMatch(/^global-backup-.*\.sqlite3$/)
    expect(filePath).toBeTruthy()
    const content = await readFile(filePath!)
    expect(content.length).toBeGreaterThan(1024)
    expect(content.subarray(0, 16).toString("ascii")).toBe("SQLite format 3\u0000")
    await expect(page.getByText(/backup generado y descargado/i)).toBeVisible()
    expect(failures).toEqual([])
  })

  test("usuarios sin privilegios ven acceso restringido en herramientas globales", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)

    await page.goto("/admin/plataforma/backups")
    await expect(page.getByText(/acceso restringido/i)).toBeVisible()
    await expect(page.getByRole("button", { name: /generar backup/i })).toHaveCount(0)

    await page.goto("/admin/plataforma/colegios")
    await expect(page.getByText(/acceso restringido/i)).toBeVisible()
    await expect(page.getByRole("button", { name: /guardar cambios/i })).toHaveCount(0)
    expect(failures).toEqual([])
  })
})
