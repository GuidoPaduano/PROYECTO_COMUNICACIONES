import path from "node:path"

import { expect, test, type Page } from "@playwright/test"

import { loginAs, watchRuntimeFailures } from "./helpers"

const axePath = path.resolve(__dirname, "../node_modules/axe-core/axe.min.js")

type AxeViolation = {
  id: string
  impact: string | null
  help: string
  nodes: Array<{ target: string[]; failureSummary?: string }>
}

async function expectNoSeriousAxeViolations(page: Page, context: string) {
  await page.evaluate(async () => {
    await Promise.allSettled(document.getAnimations().map((animation) => animation.finished))
  })
  await page.addScriptTag({ path: axePath })
  const violations = await page.evaluate(async () => {
    const axe = (window as typeof window & {
      axe: {
        run: (
          context: Document,
          options: { runOnly: { type: string; values: string[] } }
        ) => Promise<{ violations: AxeViolation[] }>
      }
    }).axe
    const result = await axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      },
    })
    return result.violations.filter((violation) =>
      ["serious", "critical"].includes(String(violation.impact))
    )
  })

  expect(
    violations,
    `${context}: ${JSON.stringify(
      violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        help: violation.help,
        targets: violation.nodes.map((node) => node.target.join(" ")),
      })),
      null,
      2
    )}`
  ).toEqual([])
}

async function expectReflowAtTwoHundredPercent(page: Page) {
  const result = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth
    const offenders = Array.from(document.querySelectorAll("body *"))
      .map((element) => {
        const rect = element.getBoundingClientRect()
        return {
          tag: element.tagName.toLowerCase(),
          className: typeof element.className === "string" ? element.className.slice(0, 120) : "",
          left: Math.round(rect.left),
          right: Math.round(rect.right),
        }
      })
      .filter((element) => element.right > viewportWidth + 1 || element.left < -1)
      .slice(0, 10)

    return {
      viewportWidth,
      pageWidth: document.documentElement.scrollWidth,
      offenders,
    }
  })

  expect(
    result.pageWidth,
    `Elementos fuera del viewport a zoom equivalente 200 %: ${JSON.stringify(result.offenders)}`
  ).toBeLessThanOrEqual(result.viewportWidth + 1)
}

test.describe("QA WCAG automatizada y zoom", () => {
  const routes = [
    { user: "qa_padre", path: "/dashboard", heading: /bienvenido/i },
    { user: "qa_padre", path: "/alumnos/QA001?tab=notas", heading: /ana qa/i },
    { user: "qa_profesor", path: "/mensajes", heading: /mensajes/i },
    { user: "qa_school_admin", path: "/admin/colegio/usuarios", heading: "Usuarios del colegio" },
    { user: "qa_platform_admin", path: "/admin/plataforma/colegios", heading: "Colegios" },
    { user: "qa_platform_admin", path: "/admin/plataforma/alumnos/importar", heading: "Importar alumnos" },
  ]

  for (const route of routes) {
    test(`${route.user} cumple WCAG A-AA en ${route.path}`, async ({ page }) => {
      const failures = watchRuntimeFailures(page)
      await loginAs(page, route.user)
      await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio|admin\/plataforma)/)
      await page.goto(route.path)
      await expect(page.getByRole("heading", { name: route.heading })).toBeVisible({ timeout: 25_000 })
      await expectNoSeriousAxeViolations(page, route.path)
      expect(failures).toEqual([])
    })
  }

  test("rutas principales conservan reflow con zoom equivalente al 200 por ciento", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await page.setViewportSize({ width: 640, height: 800 })
    await loginAs(page, "qa_platform_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio|admin\/plataforma)/)

    for (const route of [
      { path: "/admin/plataforma/colegios", heading: "Colegios" },
      { path: "/admin/plataforma/admins", heading: "Admins por colegio" },
      { path: "/admin/plataforma/alumnos/importar", heading: "Importar alumnos" },
      { path: "/admin/colegio/nuevo-usuario", heading: "Nuevo usuario" },
    ]) {
      await page.goto(route.path)
      await expect(page.getByRole("heading", { name: route.heading })).toBeVisible()
      await expectReflowAtTwoHundredPercent(page)
    }

    expect(failures).toEqual([])
  })
})
