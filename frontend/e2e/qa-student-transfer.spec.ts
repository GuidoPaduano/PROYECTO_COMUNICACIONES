import { expect, test, type Page } from "@playwright/test"

import { apiJson, apiResponse, loginAs, watchRuntimeFailures } from "./helpers"

function listFromPayload(payload: any, key: string) {
  if (Array.isArray(payload)) return payload
  return payload?.[key] || payload?.results || payload?.data || []
}

async function children(page: Page) {
  const payload = await apiJson<any>(page, `/api/padres/mis-hijos/?t=${Date.now()}`)
  return listFromPayload(payload, "hijos")
}

async function loginAndWait(page: Page, username: string, expectedUrl: RegExp) {
  await loginAs(page, username)
  try {
    await expect(page).toHaveURL(expectedUrl, { timeout: 10_000 })
    return
  } catch {
    await expect(page.getByRole("heading", { name: /iniciar sesi/i })).toBeVisible()
    await page.getByLabel(/usuario/i).fill(username)
    await page.getByLabel(/contrase/i).fill("QaLocal123!")
    await page.getByRole("button", { name: /ingresar/i }).click()
    await expect(page).toHaveURL(expectedUrl)
  }
}

async function restoreCourse(page: Page, alumnoId: number, schoolCourseId: number) {
  await loginAndWait(page, "qa_platform_admin", /\/(?:dashboard|admin\/plataforma|admin\/colegio)/)
  const restored = await apiResponse<any>(page, "/api/alumnos/transferir/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      alumno_id: alumnoId,
      school_course_id: schoolCourseId,
    }),
  })
  expect(restored.ok, JSON.stringify(restored.data)).toBeTruthy()
}

test.describe("QA transferencia de alumnos", () => {
  test("preceptor transfiere y conserva historial, vinculos y estado tras recarga", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const original = (await children(page)).find((item: any) => item?.id_alumno === "QA001")
    expect(original?.id).toBeTruthy()
    expect(original?.school_course_id).toBeTruthy()

    const notesBefore = listFromPayload(
      await apiJson<any>(page, "/api/notas/?id_alumno=QA001"),
      "notas"
    ).length
    const attendanceBefore = listFromPayload(
      await apiJson<any>(page, "/api/asistencias/alumno_codigo/QA001/?tipo=clases"),
      "asistencias"
    ).length
    const sanctionsBefore = listFromPayload(
      await apiJson<any>(page, "/api/sanciones/?alumno=QA001"),
      "sanciones"
    ).length
    let transferredSuccessfully = false

    await loginAs(page, "qa_preceptor")
    await expect(page).toHaveURL(/\/dashboard/)
    const coursesPayload = await apiJson<any>(page, "/api/alumnos/cursos/")
    const courses = listFromPayload(coursesPayload, "cursos")
    const target = courses.find(
      (course: any) =>
        String(course?.code || course?.id || "").toUpperCase() === "2A" &&
        Number(course?.school_course_id) !== Number(original.school_course_id)
    )
    expect(target?.school_course_id).toBeTruthy()

    try {
      await page.goto("/alumnos/QA001?tab=notas")
      await expect(page.getByRole("button", { name: "Transferir alumno" })).toBeVisible()
      await page.getByRole("button", { name: "Transferir alumno" }).click()
      const dialog = page.getByRole("dialog")
      await expect(dialog.getByRole("heading", { name: "Transferir alumno" })).toBeVisible()
      await dialog.getByRole("combobox").click()
      await page.getByRole("option", { name: new RegExp(String(target.nombre || target.id), "i") }).click()

      const transferResponse = page.waitForResponse(
        (response) =>
          response.url().includes("/api/alumnos/transferir") &&
          response.request().method() === "POST" &&
          response.status() === 200
      )
      await dialog.getByRole("button", { name: "Transferir", exact: true }).click()
      await transferResponse
      transferredSuccessfully = true
      await expect(page.getByText("Alumno transferido correctamente.")).toBeVisible()
      await expect(
        page.locator("main").getByText(String(target.nombre || target.id), { exact: true })
      ).toBeVisible()

      await page.reload()
      await expect(
        page.locator("main").getByText(String(target.nombre || target.id), { exact: true })
      ).toBeVisible()

      const oldRoster = listFromPayload(
        await apiJson<any>(
          page,
          `/api/alumnos/?school_course_id=${encodeURIComponent(String(original.school_course_id))}`
        ),
        "alumnos"
      )
      const newRoster = listFromPayload(
        await apiJson<any>(
          page,
          `/api/alumnos/?school_course_id=${encodeURIComponent(String(target.school_course_id))}`
        ),
        "alumnos"
      )
      expect(oldRoster.some((item: any) => item?.id_alumno === "QA001")).toBe(false)
      expect(newRoster.some((item: any) => item?.id_alumno === "QA001")).toBe(true)

      await loginAs(page, "qa_padre")
      await expect(page).toHaveURL(/\/dashboard/)
      const transferred = (await children(page)).find((item: any) => item?.id_alumno === "QA001")
      expect(Number(transferred?.school_course_id)).toBe(Number(target.school_course_id))
      expect(listFromPayload(await apiJson<any>(page, "/api/notas/?id_alumno=QA001"), "notas").length).toBe(notesBefore)
      expect(
        listFromPayload(
          await apiJson<any>(page, "/api/asistencias/alumno_codigo/QA001/?tipo=clases"),
          "asistencias"
        ).length
      ).toBe(attendanceBefore)
      expect(
        listFromPayload(await apiJson<any>(page, "/api/sanciones/?alumno=QA001"), "sanciones").length
      ).toBe(sanctionsBefore)
    } finally {
      if (transferredSuccessfully) {
        await restoreCourse(page, Number(original.id), Number(original.school_course_id))
      }
    }

    expect(failures).toEqual([])
  })

  test("roles muestran u ocultan la accion segun permisos", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAndWait(page, "qa_school_admin", /\/(?:dashboard|admin\/colegio)/)
    await page.goto("/alumnos/QA001?tab=notas")
    await expect(page.getByRole("button", { name: "Transferir alumno" })).toBeVisible()

    await loginAndWait(page, "qa_profesor", /\/dashboard/)
    await page.goto("/alumnos/QA001?tab=notas")
    await expect(page.getByRole("button", { name: "Transferir alumno" })).toHaveCount(0)

    await loginAndWait(page, "qa_padre", /\/dashboard/)
    await page.goto("/alumnos/QA001?tab=notas")
    await expect(page.getByRole("button", { name: "Transferir alumno" })).toHaveCount(0)
    expect(failures).toEqual([])
  })
})
