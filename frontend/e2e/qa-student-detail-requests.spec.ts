import { expect, test } from "@playwright/test"

import { apiJson, loginAs } from "./helpers"

test.describe("QA solicitudes de ficha del alumno", () => {
  test("deduplica detalle, catálogo y vínculos familiares durante la carga inicial", async ({
    page,
  }) => {
    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)

    const payload = await apiJson<any>(page, "/api/padres/mis-hijos/")
    const hijos = Array.isArray(payload?.results)
      ? payload.results
      : Array.isArray(payload)
        ? payload
        : []
    const alumno = hijos.find((item: any) => item?.id_alumno === "QA001") || hijos[0]
    expect(alumno?.id).toBeTruthy()

    const counts = {
      detail: 0,
      catalog: 0,
      children: 0,
      notes: 0,
      sanctions: 0,
      attendance: 0,
    }
    const detailRequests: string[] = []
    const detailResponses: string[] = []
    page.on("request", (request) => {
      const url = new URL(request.url())
      const activePath = new URL(page.url()).pathname
      if (!activePath.startsWith("/alumnos/")) return
      if (/\/api\/alumnos\/[^/]+\/?$/.test(url.pathname)) {
        counts.detail += 1
        detailRequests.push(`${request.method()} ${url.pathname}${url.search}`)
      }
      if (/\/api\/notas\/catalogos\/?$/.test(url.pathname)) counts.catalog += 1
      if (/\/api\/padres\/mis-hijos\/?$/.test(url.pathname)) counts.children += 1
      if (/\/api\/notas\/?$/.test(url.pathname) && url.search) counts.notes += 1
      if (/\/api\/sanciones\/?$/.test(url.pathname) && url.search) counts.sanctions += 1
      if (/\/api\/asistencias\/?$/.test(url.pathname) && url.search) counts.attendance += 1
    })
    page.on("response", (response) => {
      const url = new URL(response.url())
      if (/\/api\/alumnos\/[^/]+\/?$/.test(url.pathname)) {
        detailResponses.push(`${response.status()} ${url.pathname}${url.search}`)
      }
    })

    await page.goto(`/alumnos/${alumno.id}?from=%2Fmis-hijos&tab=notas`)
    await expect(page.getByRole("heading", { name: /ana qa/i })).toBeVisible()
    await expect(page.getByText("Notas", { exact: true }).first()).toBeVisible()
    await page.waitForTimeout(2500)

    expect(
      counts.detail,
      `requests=${JSON.stringify(detailRequests)} responses=${JSON.stringify(detailResponses)}`
    ).toBeLessThanOrEqual(1)
    expect(counts.catalog).toBeLessThanOrEqual(1)
    expect(counts.children).toBeLessThanOrEqual(2)
    expect(counts.notes).toBeLessThanOrEqual(1)
    expect(counts.sanctions).toBeLessThanOrEqual(1)
    expect(counts.attendance).toBeLessThanOrEqual(1)
  })
})
