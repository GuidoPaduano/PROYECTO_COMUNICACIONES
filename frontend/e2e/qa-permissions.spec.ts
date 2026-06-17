import { expect, test } from "@playwright/test"

import { apiJson, apiResponse, loginAs, uniqueQaText, watchRuntimeFailures } from "./helpers"

test.describe("QA local permissions and isolation", () => {
  test("alumno QA no puede leer datos academicos de otro alumno", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_alumno")
    await expect(page).toHaveURL(/\/dashboard/)

    const notas = await apiResponse(page, "/api/notas/?id_alumno=QA002")
    expect(notas.status).toBe(403)

    const sanciones = await apiResponse(page, "/api/sanciones/?alumno=QA002")
    expect(sanciones.status).toBe(403)

    const asistencias = await apiResponse(page, "/api/asistencias/alumno_codigo/QA002/?tipo=clases")
    expect(asistencias.status).toBe(403)

    expect(failures).toEqual([])
  })

  test("profesor QA no puede operar sobre alumno de curso no asignado", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const notasPadre = await apiJson<any>(page, "/api/notas/?id_alumno=QA002")
    const alumnoId = notasPadre?.alumno?.id
    expect(alumnoId).toBeTruthy()

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)

    const readNotas = await apiResponse(page, "/api/notas/?id_alumno=QA002")
    expect(readNotas.status).toBe(403)

    const nota = await apiResponse(page, "/api/calificaciones/notas/masivo/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        notas: [
          {
            alumno: alumnoId,
            materia: "Matematica",
            tipo: "Examen",
            resultado: "TEA",
            calificacion: "9",
            cuatrimestre: 1,
            fecha: new Date().toISOString().slice(0, 10),
          },
        ],
      }),
    })
    expect(nota.status).toBe(400)
    expect(JSON.stringify(nota.data).toLowerCase()).toContain("permiso")

    const motivo = uniqueQaText("Sancion no permitida E2E")
    const sancion = await apiResponse(page, "/api/sanciones/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alumno: alumnoId, mensaje: motivo }),
    })
    expect(sancion.status).toBe(403)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const sancionesPadre = await apiJson<any>(page, "/api/sanciones/?alumno=QA002")
    const sanciones = Array.isArray(sancionesPadre) ? sancionesPadre : sancionesPadre?.results || []
    expect(sanciones.some((item: any) => String(item?.motivo || "").includes(motivo))).toBeFalsy()

    expect(failures).toEqual([])
  })

  test("padre QA no puede listar roster de curso ni crear registros academicos", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)

    const hijos = await apiJson<any>(page, "/api/padres/mis-hijos/")
    const list = Array.isArray(hijos?.hijos) ? hijos.hijos : Array.isArray(hijos?.results) ? hijos.results : hijos
    const firstChild = Array.isArray(list) ? list[0] : null
    const schoolCourseId = firstChild?.school_course_id
    expect(schoolCourseId).toBeTruthy()

    const roster = await apiResponse(page, `/api/alumnos/?school_course_id=${encodeURIComponent(String(schoolCourseId))}`)
    expect(roster.status).toBe(403)

    const nota = await apiResponse(page, "/api/calificaciones/notas/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        alumno: firstChild.id,
        materia: "Matematica",
        tipo: "Examen",
        resultado: "TEA",
        calificacion: "10",
        cuatrimestre: 1,
        fecha: new Date().toISOString().slice(0, 10),
      }),
    })
    expect(nota.ok).toBeFalsy()
    expect(nota.status).toBeLessThan(500)

    const sancion = await apiResponse(page, "/api/sanciones/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alumno: firstChild.id, mensaje: uniqueQaText("Sancion padre bloqueada E2E") }),
    })
    expect(sancion.status).toBe(403)

    expect(failures).toEqual([])
  })
})
