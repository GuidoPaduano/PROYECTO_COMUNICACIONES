import { expect, test, type Page } from "@playwright/test"

import { apiJson, apiResponse, loginAs, uniqueQaText, watchRuntimeFailures } from "./helpers"

function listFromPayload(payload: any, key: string) {
  if (Array.isArray(payload)) return payload
  return payload?.[key] || payload?.results || payload?.data || []
}

function qaDate(offsetDays = 0) {
  const date = new Date()
  date.setUTCDate(date.getUTCDate() + offsetDays)
  return date.toISOString().slice(0, 10)
}

async function getQa001(page: Page) {
  await loginAs(page, "qa_padre")
  await expect(page).toHaveURL(/\/dashboard/)
  const hijosPayload = await apiJson<any>(page, "/api/padres/mis-hijos/")
  const hijos = Array.isArray(hijosPayload?.hijos)
    ? hijosPayload.hijos
    : Array.isArray(hijosPayload?.results)
      ? hijosPayload.results
      : hijosPayload
  const alumno = Array.isArray(hijos) ? hijos.find((item: any) => item?.id_alumno === "QA001") || hijos[0] : null
  expect(alumno?.id).toBeTruthy()
  expect(alumno?.school_course_id).toBeTruthy()
  return alumno
}

async function createAttendance(page: Page, alumno: any, tipoAsistencia: string, fecha: string, estado: "ausente" | "tarde" = "ausente") {
  await loginAs(page, "qa_preceptor")
  await expect(page).toHaveURL(/\/dashboard/)
  const response = await apiResponse<any>(page, "/api/asistencias/registrar/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      return_items: true,
      school_course_id: alumno.school_course_id,
      fecha,
      tipo_asistencia: tipoAsistencia,
      items: [
        {
          alumno_id: alumno.id,
          presente: estado === "tarde",
          tarde: estado === "tarde",
        },
      ],
    }),
  })
  expect(response.ok, JSON.stringify(response.data)).toBeTruthy()
  const item = response.data?.items?.[0]
  expect(item?.id).toBeTruthy()
  return item
}

async function attendanceById(page: Page, tipoAsistencia: string, asistenciaId: number | string) {
  const payload = await apiJson<any>(page, `/api/asistencias/alumno_codigo/QA001/?tipo=${encodeURIComponent(tipoAsistencia)}`)
  const asistencias = listFromPayload(payload, "asistencias")
  return asistencias.find((item: any) => Number(item?.id) === Number(asistenciaId))
}

test.describe("QA local advanced attendance flows", () => {
  test("padre usa Firmar todo y firma todas las inasistencias pendientes", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const alumno = await getQa001(page)
    const tipoBase = uniqueQaText("Firma masiva asistencia E2E")
    const first = await createAttendance(page, alumno, `${tipoBase} A`, qaDate(31), "ausente")
    const second = await createAttendance(page, alumno, `${tipoBase} B`, qaDate(32), "tarde")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/alumnos/QA001?tab=asistencias")
    await expect(page.getByRole("row").filter({ hasText: `${tipoBase} A` })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole("row").filter({ hasText: `${tipoBase} B` })).toBeVisible({ timeout: 15_000 })

    await page.getByRole("button", { name: /^firmar todo$/i }).click()
    await expect(page.getByRole("dialog", { name: /firmar todo/i })).toBeVisible()
    await expect(page.getByText(/inasistencias pendientes a firmar/i)).toBeVisible()
    await page.getByRole("button", { name: /confirmar firma/i }).click()

    const rowA = page.getByRole("row").filter({ hasText: `${tipoBase} A` })
    const rowB = page.getByRole("row").filter({ hasText: `${tipoBase} B` })
    await expect(rowA.getByText(/firmada/i)).toBeVisible({ timeout: 15_000 })
    await expect(rowB.getByText(/firmada/i)).toBeVisible({ timeout: 15_000 })

    const signedA = await attendanceById(page, `${tipoBase} A`, first.id)
    const signedB = await attendanceById(page, `${tipoBase} B`, second.id)
    expect(signedA?.firmada).toBe(true)
    expect(signedB?.firmada).toBe(true)
    expect(failures).toEqual([])
  })

  test("preceptor justifica y edita detalle; padre ve ambos datos", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const alumno = await getQa001(page)
    const tipoAsistencia = uniqueQaText("Detalle asistencia E2E")
    const detalle = uniqueQaText("Observacion asistencia E2E")
    const asistencia = await createAttendance(page, alumno, tipoAsistencia, qaDate(33), "ausente")

    await loginAs(page, "qa_preceptor")
    await expect(page).toHaveURL(/\/dashboard/)
    const justifyResponse = await apiResponse(page, `/api/asistencias/${asistencia.id}/justificar/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ justificada: true }),
    })
    expect(justifyResponse.ok, JSON.stringify(justifyResponse.data)).toBeTruthy()
    expect(justifyResponse.data?.justificada).toBe(true)

    const detailResponse = await apiResponse(page, `/api/asistencias/${asistencia.id}/detalle/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ detalle }),
    })
    expect(detailResponse.ok, JSON.stringify(detailResponse.data)).toBeTruthy()
    expect(String(detailResponse.data?.detalle || detailResponse.data?.observacion || "")).toContain(detalle)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/alumnos/QA001?tab=asistencias")
    const parentRow = page.getByRole("row").filter({ hasText: tipoAsistencia })
    await expect(parentRow.getByText(/^Justificada$/i)).toBeVisible({ timeout: 15_000 })
    await expect(parentRow.getByText(detalle)).toBeVisible()
    await expect(parentRow.getByRole("button", { name: /^justificar$/i })).toHaveCount(0)

    const updated = await attendanceById(page, tipoAsistencia, asistencia.id)
    expect(updated?.justificada).toBe(true)
    expect(String(updated?.detalle || updated?.observacion || updated?.observaciones || "")).toContain(detalle)
    expect(failures).toEqual([])
  })

  test("padre y alumno no pueden justificar ni editar detalle de asistencia", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const alumno = await getQa001(page)
    const tipoAsistencia = uniqueQaText("Permisos asistencia E2E")
    const asistencia = await createAttendance(page, alumno, tipoAsistencia, qaDate(34), "ausente")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const padreJustifica = await apiResponse(page, `/api/asistencias/${asistencia.id}/justificar/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ justificada: true }),
    })
    expect(padreJustifica.status).toBe(403)
    const padreDetalle = await apiResponse(page, `/api/asistencias/${asistencia.id}/detalle/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ detalle: "Detalle no permitido padre" }),
    })
    expect(padreDetalle.status).toBe(403)

    await loginAs(page, "qa_alumno")
    await expect(page).toHaveURL(/\/dashboard/)
    const alumnoJustifica = await apiResponse(page, `/api/asistencias/${asistencia.id}/justificar/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ justificada: true }),
    })
    expect(alumnoJustifica.status).toBe(403)
    const alumnoDetalle = await apiResponse(page, `/api/asistencias/${asistencia.id}/detalle/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ detalle: "Detalle no permitido alumno" }),
    })
    expect(alumnoDetalle.status).toBe(403)

    await loginAs(page, "qa_preceptor")
    await expect(page).toHaveURL(/\/dashboard/)
    const unchanged = await attendanceById(page, tipoAsistencia, asistencia.id)
    expect(unchanged?.justificada).toBeFalsy()
    expect(String(unchanged?.detalle || unchanged?.observacion || unchanged?.observaciones || "")).not.toContain("no permitido")
    expect(failures).toEqual([])
  })
})
