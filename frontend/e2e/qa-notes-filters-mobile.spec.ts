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

async function getChildByCode(page: Page, code: string) {
  await loginAs(page, "qa_padre")
  await expect(page).toHaveURL(/\/dashboard/)
  const payload = await apiJson<any>(page, "/api/padres/mis-hijos/")
  const hijos = Array.isArray(payload?.hijos) ? payload.hijos : Array.isArray(payload?.results) ? payload.results : payload
  const child = Array.isArray(hijos) ? hijos.find((item: any) => item?.id_alumno === code) : null
  expect(child?.id).toBeTruthy()
  return child
}

async function validMateria(page: Page) {
  const catalog = await apiJson<any>(page, "/api/calificaciones/nueva-nota/datos/")
  const materia = listFromPayload(catalog, "materias").find((item: any) => String(item?.id || item?.value || item).trim())
  expect(materia).toBeTruthy()
  return String(materia?.id || materia?.value || materia)
}

async function createNote(page: Page, alumnoId: number | string, observaciones: string, overrides: Record<string, any> = {}) {
  const materia = overrides.materia || (await validMateria(page))
  const response = await apiResponse<any>(page, "/api/calificaciones/notas/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      alumno: alumnoId,
      materia,
      tipo: "Examen",
      resultado: "TEA",
      calificacion: "8",
      nota_numerica: "8",
      cuatrimestre: 1,
      fecha: qaDate(),
      observaciones,
      ...overrides,
    }),
  })
  expect(response.ok, JSON.stringify(response.data)).toBeTruthy()
  expect(response.data?.id).toBeTruthy()
  return { id: response.data.id, materia, version: response.data.version }
}

async function createAttendance(page: Page, alumno: any, tipoAsistencia: string, fecha: string) {
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
      items: [{ alumno_id: alumno.id, presente: false }],
    }),
  })
  expect(response.ok, JSON.stringify(response.data)).toBeTruthy()
  return response.data?.items?.[0]
}

test.describe("QA local notes, filters and mobile", () => {
  test("profesor edita una nota propia y no puede editar una nota de curso no asignado", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const qa001 = await getChildByCode(page, "QA001")
    const originalComment = uniqueQaText("Nota editable E2E")
    const updatedComment = uniqueQaText("Nota editada E2E")

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    const ownNote = await createNote(page, qa001.id, originalComment)
    const editOwn = await apiResponse<any>(page, `/api/calificaciones/notas/${ownNote.id}/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        version: ownNote.version,
        materia: ownNote.materia,
        tipo: "Examen",
        resultado: "TEA",
        calificacion: "9",
        nota_numerica: "9",
        cuatrimestre: 1,
        fecha: qaDate(),
        observaciones: updatedComment,
      }),
    })
    expect(editOwn.ok, JSON.stringify(editOwn.data)).toBeTruthy()

    const staleEdit = await apiResponse<any>(page, `/api/calificaciones/notas/${ownNote.id}/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        version: ownNote.version,
        observaciones: "Edicion obsoleta que no debe persistir",
      }),
    })
    expect(staleEdit.status).toBe(409)
    expect(staleEdit.data?.nota?.observaciones).toBe(updatedComment)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const qa002Payload = await apiJson<any>(page, "/api/notas/?id_alumno=QA002")
    const qa002Notas = listFromPayload(qa002Payload, "notas")
    const otherNote = qa002Notas[0]
    expect(otherNote?.id).toBeTruthy()

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    const editOther = await apiResponse(page, `/api/calificaciones/notas/${otherNote.id}/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ observaciones: "Edicion no permitida QA002" }),
    })
    expect(editOther.status).toBe(403)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/alumnos/QA001?tab=notas")
    const editedRow = page.getByRole("row", { name: new RegExp(updatedComment, "i") })
    await expect(editedRow).toBeVisible({ timeout: 15_000 })
    await expect(editedRow.getByText(/^9(?:\.00)?$/)).toBeVisible()

    const payload = await apiJson<any>(page, "/api/notas/?id_alumno=QA001")
    const notas = listFromPayload(payload, "notas")
    const edited = notas.find((nota: any) => Number(nota?.id) === Number(ownNote.id))
    expect(String(edited?.observaciones || "")).toContain(updatedComment)
    expect(String(edited?.calificacion || edited?.nota_numerica || "")).toContain("9")
    expect(failures).toEqual([])
  })

  test("padre filtra notas por busqueda y asistencias por tipo", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const qa001 = await getChildByCode(page, "QA001")
    const noteMarker = uniqueQaText("Filtro nota visible E2E")
    const noteDecoy = uniqueQaText("Filtro nota oculta E2E")

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await createNote(page, qa001.id, noteMarker)
    await createNote(page, qa001.id, noteDecoy)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/alumnos/QA001?tab=notas")
    await expect(page.getByRole("row", { name: new RegExp(noteMarker, "i") })).toBeVisible({ timeout: 15_000 })
    await page.getByPlaceholder(/materia, nota, comentario/i).first().fill(noteMarker)
    await expect(page.getByRole("row", { name: new RegExp(noteMarker, "i") })).toBeVisible()
    await expect(page.getByRole("row", { name: new RegExp(noteDecoy, "i") })).toHaveCount(0)

    await createAttendance(page, qa001, "informatica", qaDate(41))
    await createAttendance(page, qa001, "catequesis", qaDate(42))
    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/alumnos/QA001?tab=asistencias")
    await expect(page.getByRole("row").filter({ hasText: /inform/i }).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole("row").filter({ hasText: /catequesis/i }).first()).toBeVisible()
    await page.locator("select").nth(1).selectOption("informatica")
    await expect(page.getByRole("row").filter({ hasText: /inform/i }).first()).toBeVisible()
    await expect(page.getByRole("row").filter({ hasText: /catequesis/i })).toHaveCount(0)
    expect(failures).toEqual([])
  })

  test("padre navega en mobile por dashboard, mis hijos, alumno y mensajes sin errores runtime", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.getByRole("heading", { name: /bienvenido/i })).toBeVisible({ timeout: 15_000 })

    await page.goto("/mis-hijos")
    await expect(page.getByRole("heading", { name: /^Ana QA$/i })).toBeVisible({ timeout: 15_000 })

    await page.goto("/alumnos/QA001?tab=asistencias")
    await expect(page.getByRole("heading", { name: /ana qa/i })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/inasistencias/i).first()).toBeVisible()

    await page.goto("/mensajes")
    await expect(page.getByRole("heading", { name: /mensajes/i })).toBeVisible({ timeout: 15_000 })
    expect(failures).toEqual([])
  })
})
