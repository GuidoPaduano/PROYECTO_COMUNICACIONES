import { expect, test, type Page } from "@playwright/test"

import { apiJson, apiResponse, loginAs, QA_PASSWORD, QA_SCHOOL, uniqueQaText, watchRuntimeFailures } from "./helpers"

function listFromPayload(payload: any, key: string) {
  if (Array.isArray(payload)) return payload
  return payload?.[key] || payload?.results || payload?.data || []
}

function qaDate(offsetDays = 0) {
  const date = new Date()
  date.setUTCDate(date.getUTCDate() + offsetDays)
  return date.toISOString().slice(0, 10)
}

async function getChildren(page: Page) {
  await loginQa(page, "qa_padre")
  const payload = await apiJson<any>(page, "/api/padres/mis-hijos/")
  const hijos = Array.isArray(payload?.hijos) ? payload.hijos : Array.isArray(payload?.results) ? payload.results : payload
  expect(Array.isArray(hijos)).toBe(true)
  return hijos
}

async function loginQa(page: Page, username: string, target: RegExp = /\/dashboard/) {
  await loginAs(page, username)
  try {
    await expect(page).toHaveURL(target, { timeout: 10_000 })
    return
  } catch (error) {
    if (!page.url().includes("/login")) throw error
  }

  await page.goto(`/login?school=${QA_SCHOOL}`)
  await expect(page.getByRole("heading", { name: /iniciar sesi/i })).toBeVisible()
  await page.getByLabel(/usuario/i).fill(username)
  await page.getByLabel(/contrase/i).fill(QA_PASSWORD)
  await page.getByRole("button", { name: /ingresar/i }).click()
  await expect(page).toHaveURL(target, { timeout: 15_000 })
}

async function createEvent(page: Page, schoolCourseId: number | string, title: string, offsetDays: number) {
  const response = await apiResponse<any>(page, "/api/eventos/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      titulo: title,
      descripcion: `${title} descripcion`,
      fecha: qaDate(offsetDays),
      school_course_id: schoolCourseId,
      tipo_evento: "Evaluación",
    }),
  })
  expect(response.ok, JSON.stringify(response.data)).toBeTruthy()
  expect(response.data?.id).toBeTruthy()
  return response.data
}

function hasEvent(events: any[], title: string) {
  return events.some((event) => String(event?.title || event?.titulo || "").includes(title))
}

test.describe("QA local reports and events", () => {
  test("reportes respetan rol: profesor curso asignado, padre hijo propio y bloqueos", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const hijos = await getChildren(page)
    const qa001 = hijos.find((item: any) => item?.id_alumno === "QA001")
    const qa002 = hijos.find((item: any) => item?.id_alumno === "QA002")
    expect(qa001?.school_course_id).toBeTruthy()
    expect(qa002?.school_course_id).toBeTruthy()

    await loginQa(page, "qa_profesor")
    const report1A = await apiResponse<any>(page, `/api/reportes/curso/${qa001.school_course_id}/`)
    expect(report1A.ok, JSON.stringify(report1A.data)).toBeTruthy()
    expect(report1A.data?.scope).toBe("curso")
    expect(report1A.data?.resumen_notas || report1A.data?.por_materia).toBeTruthy()

    const report2A = await apiResponse(page, `/api/reportes/curso/${qa002.school_course_id}/`)
    expect(report2A.status).toBe(403)

    await loginQa(page, "qa_padre")
    const ownStats = await apiResponse<any>(page, `/api/reportes/mis-estadisticas/?alumno_id=QA001`)
    expect(ownStats.ok, JSON.stringify(ownStats.data)).toBeTruthy()
    expect(ownStats.data?.scope).toBe("mis_estadisticas")
    expect(ownStats.data?.alumno_activo?.id_alumno).toBe("QA001")

    const parentCourseReport = await apiResponse(page, `/api/reportes/curso/${qa001.school_course_id}/`)
    expect(parentCourseReport.status).toBe(403)

    await loginQa(page, "qa_alumno")
    const studentStats = await apiResponse<any>(page, "/api/reportes/mis-estadisticas/")
    expect(studentStats.ok, JSON.stringify(studentStats.data)).toBeTruthy()
    expect(studentStats.data?.alumno_activo?.id_alumno).toBe("QA001")

    const studentCourseReport = await apiResponse(page, `/api/reportes/curso/${qa001.school_course_id}/`)
    expect(studentCourseReport.status).toBe(403)
    expect(failures).toEqual([])
  })

  test("eventos de calendario se ven solo en cursos autorizados", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const hijos = await getChildren(page)
    const qa001 = hijos.find((item: any) => item?.id_alumno === "QA001")
    const qa002 = hijos.find((item: any) => item?.id_alumno === "QA002")
    expect(qa001?.school_course_id).toBeTruthy()
    expect(qa002?.school_course_id).toBeTruthy()

    const title1A = uniqueQaText("Evento 1A E2E")
    const title2A = uniqueQaText("Evento 2A E2E")
    const desde = qaDate(50)
    const hasta = qaDate(55)

    await loginQa(page, "qa_preceptor")
    await createEvent(page, qa001.school_course_id, title1A, 51)
    await createEvent(page, qa002.school_course_id, title2A, 52)

    await loginQa(page, "qa_padre")
    const parentQa001 = await apiJson<any>(page, `/api/padres/hijos/QA001/eventos/?desde=${desde}&hasta=${hasta}`)
    const parentQa001Events = listFromPayload(parentQa001, "results")
    expect(hasEvent(parentQa001Events, title1A)).toBe(true)
    expect(hasEvent(parentQa001Events, title2A)).toBe(false)

    const parentAll = await apiJson<any>(page, `/api/padres/mis-hijos/eventos/?desde=${desde}&hasta=${hasta}`)
    const parentAllEvents = listFromPayload(parentAll, "results")
    expect(hasEvent(parentAllEvents, title1A)).toBe(true)
    expect(hasEvent(parentAllEvents, title2A)).toBe(true)

    await loginQa(page, "qa_alumno")
    const alumnoEvents = await apiJson<any>(page, `/api/eventos/?desde=${desde}&hasta=${hasta}`)
    expect(hasEvent(listFromPayload(alumnoEvents, "results"), title1A)).toBe(true)
    expect(hasEvent(listFromPayload(alumnoEvents, "results"), title2A)).toBe(false)

    await loginQa(page, "qa_profesor")
    const professorOwn = await apiResponse<any>(page, `/api/eventos/?school_course_id=${qa001.school_course_id}&desde=${desde}&hasta=${hasta}`)
    expect(professorOwn.ok, JSON.stringify(professorOwn.data)).toBeTruthy()
    expect(hasEvent(listFromPayload(professorOwn.data, "results"), title1A)).toBe(true)

    const professorOther = await apiResponse(page, `/api/eventos/?school_course_id=${qa002.school_course_id}&desde=${desde}&hasta=${hasta}`)
    expect(professorOther.status).toBe(403)
    expect(failures).toEqual([])
  })
})
