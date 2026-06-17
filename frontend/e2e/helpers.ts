import { expect, type Locator, type Page } from "@playwright/test"

export const QA_PASSWORD = process.env.E2E_QA_PASSWORD || "QaLocal123!"
export const QA_SCHOOL = process.env.E2E_QA_SCHOOL || "qa-local"

export function watchRuntimeFailures(page: Page) {
  const failures: string[] = []

  page.on("response", (response) => {
    if (response.status() >= 500) {
      failures.push(`${response.status()} ${response.url()}`)
    }
  })

  page.on("pageerror", (error) => {
    if (error.message.includes("noop-turbopack-hmr")) return
    failures.push(`pageerror ${error.message}`)
  })

  return failures
}

export async function loginAs(page: Page, username: string) {
  await page.goto(`/login?school=${QA_SCHOOL}`)
  await expect(page.getByRole("heading", { name: /iniciar sesi/i })).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`/login\\?school=${QA_SCHOOL}(?:&|$)`), { timeout: 20_000 })
  await expect(page.getByText(/entrar a QA Local/i)).toBeVisible({ timeout: 20_000 })
  await page.getByLabel(/usuario/i).fill(username)
  await page.getByLabel(/contrase/i).fill(QA_PASSWORD)
  await page.getByRole("button", { name: /ingresar/i }).click()
  await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio|admin\/plataforma)/, { timeout: 20_000 })
  await expect(page.locator("main.app-main")).toBeVisible({ timeout: 20_000 })
  await page.waitForLoadState("load")
}

export async function selectOptionMatching(locator: Locator, pattern: RegExp) {
  await expect(locator).toBeVisible()
  await expect.poll(async () => locator.evaluate((select) => (select as HTMLSelectElement).options.length)).toBeGreaterThan(0)
  let match: { index: number; value: string } | null = null
  await expect
    .poll(
      async () => {
        match = await locator.evaluate(
          (select, serializedPattern) => {
            const { source, flags } = serializedPattern as { source: string; flags: string }
            const safeFlags = flags.replace(/g/g, "")
            const normalizedFlags = safeFlags.includes("i") ? safeFlags : `${safeFlags}i`
            const options = Array.from((select as HTMLSelectElement).options)
            for (let index = 0; index < options.length; index += 1) {
              const re = new RegExp(source, normalizedFlags)
              const option = options[index]
              const text = option.textContent || ""
              const value = option.value || ""
              if (re.test(text) || re.test(value)) {
                return { index, value }
              }
            }
            return null
          },
          { source: pattern.source, flags: pattern.flags }
        )
        return match ? `${match.index}:${match.value}` : ""
      },
      { timeout: 15_000 }
    )
    .not.toBe("")

  expect(match).not.toBeNull()
  if (match!.value) {
    await locator.selectOption(match!.value)
  } else {
    await locator.selectOption({ index: match!.index })
  }
  return match!.value
}

export async function apiJson<T = any>(page: Page, path: string, options: RequestInit = {}): Promise<T> {
  return await page.evaluate(
    async ({ path, options, school }) => {
      const headers = {
        Accept: "application/json",
        "X-School": school,
        ...((options.headers as Record<string, string>) || {}),
      }
      const response = await fetch(path, {
        credentials: "include",
        ...options,
        headers,
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || data?.error || `HTTP ${response.status}`)
      }
      return data
    },
    { path, options, school: QA_SCHOOL }
  )
}

export async function apiResponse<T = any>(
  page: Page,
  path: string,
  options: RequestInit = {}
): Promise<{ status: number; ok: boolean; data: T }> {
  return await page.evaluate(
    async ({ path, options, school }) => {
      const headers = {
        Accept: "application/json",
        "X-School": school,
        ...((options.headers as Record<string, string>) || {}),
      }
      const response = await fetch(path, {
        credentials: "include",
        ...options,
        headers,
      })
      const data = await response.json().catch(() => ({}))
      return { status: response.status, ok: response.ok, data }
    },
    { path, options, school: QA_SCHOOL }
  )
}

export function uniqueQaText(prefix: string) {
  return `${prefix} ${Date.now()}`
}

export function localDateString(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}
