import { expect, test } from "@playwright/test"

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

test.describe("QA local signatures", () => {
  test("padre firma una nota y no puede firmarla dos veces", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const today = qaDate()
    const marker = uniqueQaText("Firma nota E2E")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const initialNotas = await apiJson<any>(page, "/api/notas/?id_alumno=QA001")
    const alumnoId = initialNotas?.alumno?.id
    expect(alumnoId).toBeTruthy()

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    const catalog = await apiJson<any>(page, "/api/calificaciones/nueva-nota/datos/")
    const materiaValida =
      listFromPayload(catalog, "materias").find((item: any) => String(item?.id || item?.value || item).trim()) ||
      "Matemática"
    const createNota = await apiResponse(page, "/api/calificaciones/notas/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        alumno: alumnoId,
        materia: String(materiaValida?.id || materiaValida?.value || materiaValida),
        tipo: "Examen",
        resultado: "TEA",
        calificacion: "8",
        cuatrimestre: 1,
        fecha: today,
        observaciones: marker,
      }),
    })
    expect(createNota.ok, JSON.stringify(createNota.data)).toBeTruthy()

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/alumnos/QA001?tab=notas")

    const noteRow = page.getByRole("row", { name: new RegExp(marker, "i") })
    await expect(noteRow).toBeVisible({ timeout: 15_000 })
    const signResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/notas/") && response.url().includes("/firmar") && response.status() < 400
    })
    await noteRow.getByRole("button", { name: /^firmar$/i }).click()
    await signResponse
    await expect(noteRow.getByText(/firmada/i)).toBeVisible()

    const signedPayload = await apiJson<any>(page, "/api/notas/?id_alumno=QA001")
    const notas = listFromPayload(signedPayload, "notas")
    const signedNota = notas.find((nota: any) => String(nota?.observaciones || "").includes(marker))
    expect(signedNota?.id).toBeTruthy()
    expect(signedNota?.firmada).toBe(true)

    const secondSign = await apiResponse(page, `/api/notas/${signedNota.id}/firmar/`, { method: "POST" })
    expect(secondSign.status).toBe(400)
    expect(JSON.stringify(secondSign.data).toLowerCase()).toContain("firmada")

    expect(failures).toEqual([])
  })

  test("padre firma una inasistencia y no puede firmarla dos veces", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const date = qaDate(21)
    const tipoAsistencia = uniqueQaText("Firma asistencia E2E")

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

    await loginAs(page, "qa_preceptor")
    await expect(page).toHaveURL(/\/dashboard/)
    const createAsistencia = await apiResponse(page, "/api/asistencias/registrar/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        return_items: true,
        school_course_id: alumno.school_course_id,
        fecha: date,
        tipo_asistencia: tipoAsistencia,
        items: [
          {
            alumno_id: alumno.id,
            presente: false,
          },
        ],
      }),
    })
    expect(createAsistencia.ok).toBeTruthy()
    const asistenciaId = createAsistencia.data?.items?.[0]?.id
    expect(asistenciaId).toBeTruthy()

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/alumnos/QA001?tab=asistencias")

    const attendanceRow = page
      .getByRole("row")
      .filter({ hasText: tipoAsistencia })
      .filter({ has: page.getByRole("button", { name: /^firmar$/i }) })
    await expect(attendanceRow).toBeVisible({ timeout: 15_000 })
    const signResponse = page.waitForResponse((response) => {
      return response.url().includes(`/api/asistencias/${asistenciaId}/firmar`) && response.status() < 400
    })
    await attendanceRow.getByRole("button", { name: /^firmar$/i }).click()
    await signResponse
    const signedAttendanceRow = page.getByRole("row").filter({ hasText: tipoAsistencia })
    await expect(signedAttendanceRow.getByText(/firmada/i)).toBeVisible()

    const signedPayload = await apiJson<any>(page, `/api/asistencias/alumno_codigo/QA001/?tipo=${encodeURIComponent(tipoAsistencia)}`)
    const asistencias = listFromPayload(signedPayload, "asistencias")
    const signedAsistencia = asistencias.find((item: any) => Number(item?.id) === Number(asistenciaId))
    expect(signedAsistencia?.firmada).toBe(true)

    const secondSign = await apiResponse(page, `/api/asistencias/${asistenciaId}/firmar/`, { method: "POST" })
    expect(secondSign.status).toBe(400)
    expect(JSON.stringify(secondSign.data).toLowerCase()).toContain("firmada")

    expect(failures).toEqual([])
  })
})
