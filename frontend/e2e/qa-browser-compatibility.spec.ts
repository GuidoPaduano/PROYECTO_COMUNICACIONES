import { expect, test, type Page } from "@playwright/test"

import { loginAs, watchRuntimeFailures } from "./helpers"

const viewports = [
  { name: "desktop", width: 1366, height: 768 },
  { name: "tablet", width: 820, height: 1180 },
  { name: "mobile", width: 390, height: 844 },
]

async function navigateFromSidebar(page: Page, linkName: RegExp, compact: boolean) {
  if (compact) {
    const shell = page.locator(".app-shell")
    const sidebarOpen = await shell.evaluate((element) =>
      element.classList.contains("app-shell--sidebar-open")
    )
    if (!sidebarOpen) {
      await page.getByRole("button", { name: /abrir menu lateral/i }).click()
    }
  }
  await page.getByRole("link", { name: linkName }).click({ noWaitAfter: true })
}

async function expectNoPageOverflow(page: Page) {
  await expect
    .poll(async () =>
      page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      }))
    )
    .toMatchObject({
      clientWidth: expect.any(Number),
      scrollWidth: expect.any(Number),
    })

  const widths = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  const overflowing = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth
    const elements = Array.from(document.querySelectorAll("body *")).map((element) => {
      const rect = element.getBoundingClientRect()
      return {
        tag: element.tagName.toLowerCase(),
        className: typeof element.className === "string" ? element.className.slice(0, 160) : "",
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
      }
    })
    return elements
      .filter((element) => element.right > viewportWidth + 1)
      .concat(elements.filter((element) => element.left < -1))
      .slice(0, 10)
  })
  expect(
    widths.scrollWidth,
    `Elementos fuera del viewport: ${JSON.stringify(overflowing)}`
  ).toBeLessThanOrEqual(widths.clientWidth + 1)
}

test.describe("QA compatibilidad de navegadores y dispositivos", () => {
  for (const viewport of viewports) {
    test(`padre navega flujos principales en ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      const compact = viewport.width < 1024
      const failures = watchRuntimeFailures(page)

      await loginAs(page, "qa_padre")
      await expect(page).toHaveURL(/\/dashboard/)
      await expect(page.getByRole("heading", { name: /bienvenido/i })).toBeVisible()
      await expectNoPageOverflow(page)

      await navigateFromSidebar(page, /mis hijos/i, compact)
      await expect(page).toHaveURL(/\/alumnos\/[^/?]+/)
      await expect(page.getByRole("heading", { name: /ana qa/i })).toBeVisible()
      const notesTab = page.getByRole("tab", { name: "Notas" })
      await expect(notesTab).toHaveAttribute("aria-selected", "true")
      await expect(page.getByRole("tabpanel", { name: "Notas" })).toBeVisible()
      await expect(page.getByRole("button", { name: /reintentar notas/i })).toBeHidden()
      await expectNoPageOverflow(page)

      await notesTab.focus()
      await notesTab.press("ArrowRight")
      await expect(page.getByRole("tab", { name: "Sanciones" })).toHaveAttribute(
        "aria-selected",
        "true"
      )

      await navigateFromSidebar(page, /mensajes/i, compact)
      await expect(page).toHaveURL(/\/mensajes/)
      await expect(page.getByRole("heading", { name: /mensajes/i })).toBeVisible()
      await expectNoPageOverflow(page)

      const relevantFailures = failures.filter(
        (failure) => !failure.includes("NetworkError when attempting to fetch resource")
      )
      expect(relevantFailures).toEqual([])
    })
  }
})
