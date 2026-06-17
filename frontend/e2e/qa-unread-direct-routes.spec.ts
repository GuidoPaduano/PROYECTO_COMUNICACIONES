import { expect, test, type Page } from "@playwright/test"

import {
  apiJson,
  loginAs,
  uniqueQaText,
  watchRuntimeFailures,
} from "./helpers"

async function sendFamilyMessageViaApi(page: Page, subject: string, body: string) {
  await loginAs(page, "qa_profesor")
  await expect(page).toHaveURL(/\/dashboard/)

  const catalog = await apiJson<any>(page, "/api/notas/catalogos/")
  const courses = Array.isArray(catalog?.cursos) ? catalog.cursos : []
  const course = courses.find((item: any) =>
    /1A/i.test(String(item?.nombre || item?.label || item?.code || item?.id || ""))
  )
  const schoolCourseId = course?.school_course_id ?? course?.id
  expect(schoolCourseId).toBeTruthy()

  const payload = await apiJson<any>(
    page,
    `/api/alumnos/?school_course_id=${encodeURIComponent(String(schoolCourseId))}`
  )
  const students = Array.isArray(payload?.alumnos) ? payload.alumnos : []
  const student = students.find((item: any) => String(item?.id_alumno || item?.legajo || "") === "QA001")
  const studentId = student?.id ?? student?.alumno_id ?? student?.pk
  const parentId = student?.padre?.id
  expect(studentId).toBeTruthy()
  expect(parentId).toBeTruthy()

  await apiJson(page, "/api/mensajes/enviar/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      receptor_id: Number(parentId),
      alumno_id: Number(studentId),
      asunto: subject,
      contenido: body,
      tipo: "comunicado",
    }),
  })
}

async function findMessage(page: Page, subject: string) {
  const inbox = await apiJson<any>(page, "/api/mensajes/recibidos/")
  const messages = Array.isArray(inbox) ? inbox : inbox?.mensajes || inbox?.results || []
  return messages.find((message: any) => String(message?.asunto || "").includes(subject))
}

async function clearParentUnread(page: Page) {
  await loginAs(page, "qa_padre")
  await expect(page).toHaveURL(/\/dashboard/)
  await apiJson(page, "/api/mensajes/marcar_todos_leidos/", { method: "POST" })
  await apiJson(page, "/api/notificaciones/marcar_todas_leidas/", { method: "POST" })
}

function notificationBadge(page: Page) {
  return page.locator(".sidebar-bell .sidebar-pill")
}

async function openMobileMenu(page: Page) {
  await page.locator(".app-icon-button").first().click()
  await expect(page.locator(".app-sidebar")).toHaveClass(/app-sidebar--open/)
}

test.describe("QA unread y rutas directas", () => {
  test("abrir un hilo por URL directa baja el contador y persiste tras refresh", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const subject = uniqueQaText("Unread URL directa")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await apiJson(page, "/api/mensajes/marcar_todos_leidos/", { method: "POST" })
    await sendFamilyMessageViaApi(page, subject, "Mensaje para validar lectura directa")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await expect.poll(async () => (await apiJson<any>(page, "/api/mensajes/unread_count/")).count).toBe(1)
    const message = await findMessage(page, subject)
    expect(message?.thread_id || message?.id).toBeTruthy()

    await page.goto(`/mensajes/hilo/${message.thread_id || message.id}`)
    await expect(page.getByText(subject)).toBeVisible()
    await expect.poll(async () => (await apiJson<any>(page, "/api/mensajes/unread_count/")).count).toBe(0)

    await page.reload()
    await expect(page.getByText(subject)).toBeVisible()
    expect((await apiJson<any>(page, "/api/mensajes/unread_count/")).count).toBe(0)
    expect(failures).toEqual([])
  })

  test("leer un hilo sincroniza el badge de mensajes en otra pestaña", async ({ page, context }) => {
    const failures = watchRuntimeFailures(page)
    const subject = uniqueQaText("Unread entre pestañas")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await apiJson(page, "/api/mensajes/marcar_todos_leidos/", { method: "POST" })
    await sendFamilyMessageViaApi(page, subject, "Mensaje para sincronizar pestañas")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const message = await findMessage(page, subject)
    expect(message?.thread_id || message?.id).toBeTruthy()

    const otherPage = await context.newPage()
    const otherFailures = watchRuntimeFailures(otherPage)
    await otherPage.goto("/dashboard")
    const otherBadge = otherPage.locator('a[href="/mensajes"] .sidebar-pill')
    await expect(otherBadge).toHaveText("1", { timeout: 15_000 })

    await page.goto(`/mensajes/hilo/${message.thread_id || message.id}`)
    await expect(page.getByText(subject)).toBeVisible()
    await expect(otherBadge).toHaveCount(0, { timeout: 15_000 })

    expect(failures).toEqual([])
    expect(otherFailures).toEqual([])
    await otherPage.close()
  })

  test("responder un hilo crea un no leido para el profesor y abrirlo lo limpia", async ({
    page,
  }) => {
    const failures = watchRuntimeFailures(page)
    const subject = uniqueQaText("Unread respuesta")
    const reply = uniqueQaText("Respuesta padre")

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await apiJson(page, "/api/mensajes/marcar_todos_leidos/", { method: "POST" })
    await sendFamilyMessageViaApi(page, subject, "Mensaje inicial para respuesta")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    const message = await findMessage(page, subject)
    expect(message?.thread_id || message?.id).toBeTruthy()

    await page.goto(`/mensajes/hilo/${message.thread_id || message.id}`)
    await expect(page.getByText(subject)).toBeVisible()
    await page.locator("#mensaje").fill(reply)
    const replyResponse = page.waitForResponse((response) => {
      return response.url().includes("/api/mensajes/responder") && response.status() < 400
    })
    await page.getByRole("button", { name: /enviar respuesta/i }).click()
    await replyResponse

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await expect
      .poll(async () => (await apiJson<any>(page, "/api/mensajes/unread_count/")).count)
      .toBe(1)
    await expect(page.locator('a[href="/mensajes"] .sidebar-pill')).toHaveText("1")

    await page.goto(`/mensajes/hilo/${message.thread_id || message.id}`)
    await expect(page.getByText(reply)).toBeVisible()
    await expect
      .poll(async () => (await apiJson<any>(page, "/api/mensajes/unread_count/")).count)
      .toBe(0)
    await page.reload()
    await expect(page.getByText(reply)).toBeVisible()
    expect((await apiJson<any>(page, "/api/mensajes/unread_count/")).count).toBe(0)
    expect(failures).toEqual([])
  })

  test("marcar todo leido en mensajes limpia el contador y sincroniza otra pestana", async ({
    page,
    context,
  }) => {
    const failures = watchRuntimeFailures(page)
    const firstSubject = uniqueQaText("Marcar todo uno")
    const secondSubject = uniqueQaText("Marcar todo dos")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await apiJson(page, "/api/mensajes/marcar_todos_leidos/", { method: "POST" })
    await sendFamilyMessageViaApi(page, firstSubject, "Primer mensaje no leido")
    await sendFamilyMessageViaApi(page, secondSubject, "Segundo mensaje no leido")

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await expect
      .poll(async () => (await apiJson<any>(page, "/api/mensajes/unread_count/")).count)
      .toBe(2)

    const otherPage = await context.newPage()
    const otherFailures = watchRuntimeFailures(otherPage)
    await otherPage.goto("/dashboard")
    const otherBadge = otherPage.locator('a[href="/mensajes"] .sidebar-pill')
    await expect(otherBadge).toHaveText("2", { timeout: 15_000 })

    await page.goto("/mensajes")
    await expect(page.getByText(firstSubject)).toBeVisible()
    await expect(page.getByText(secondSubject)).toBeVisible()
    await page.getByRole("button", { name: /marcar todo le.do/i }).click()

    await expect
      .poll(async () => (await apiJson<any>(page, "/api/mensajes/unread_count/")).count)
      .toBe(0)
    await expect(page.locator('a[href="/mensajes"] .sidebar-pill')).toHaveCount(0)
    await expect(otherBadge).toHaveCount(0, { timeout: 15_000 })
    await otherPage.reload()
    await expect(otherPage.locator('a[href="/mensajes"] .sidebar-pill')).toHaveCount(0)

    expect(failures).toEqual([])
    expect(otherFailures).toEqual([])
    await otherPage.close()
  })

  test("rutas operativas cargadas directamente sobreviven refresh", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/agregar_nota")
    await expect(page.getByRole("heading", { name: /carga de notas/i })).toBeVisible()
    await page.reload()
    await expect(page.getByRole("heading", { name: /carga de notas/i })).toBeVisible()

    await loginAs(page, "qa_preceptor")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/pasar_asistencia")
    await expect(page.getByRole("heading", { name: /asistencia/i })).toBeVisible()
    await page.reload()
    await expect(page.getByRole("heading", { name: /asistencia/i })).toBeVisible()
    expect(failures).toEqual([])
  })

  test("rutas administrativas directas respetan el rol y sobreviven refresh", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/admin/colegio")
    await expect(page.getByText(/acceso restringido/i)).toBeVisible()
    await page.goto("/admin/plataforma")
    await expect(page.getByText(/acceso restringido/i)).toBeVisible()

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/admin\/colegio|\/dashboard/)
    await page.goto("/admin/colegio/usuarios")
    await expect(page.getByRole("heading", { name: /usuarios/i })).toBeVisible()
    await page.reload()
    await expect(page.getByRole("heading", { name: /usuarios/i })).toBeVisible()

    await loginAs(page, "qa_platform_admin")
    await expect(page).toHaveURL(/\/admin\/colegio|\/dashboard/)
    await page.goto("/admin/plataforma/colegios")
    await expect(page.getByRole("heading", { name: /colegios/i })).toBeVisible()
    await page.reload()
    await expect(page.getByRole("heading", { name: /colegios/i })).toBeVisible()
    expect(failures).toEqual([])
  })

  test("abrir una notificacion baja el badge y navega al mensaje", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const subject = uniqueQaText("Notificacion individual")

    await clearParentUnread(page)
    await sendFamilyMessageViaApi(page, subject, "Notificacion para validar apertura")
    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)

    await expect(notificationBadge(page)).toHaveText("1", { timeout: 15_000 })
    await page.locator(".sidebar-bell button").click()
    const notificationItem = page.getByRole("menuitem").filter({ hasText: subject })
    await expect(notificationItem).toBeVisible()
    await notificationItem.click()

    await expect(page).toHaveURL(/\/mensajes\/hilo\//)
    await expect(page.getByText(subject)).toBeVisible()
    await expect.poll(async () => (await apiJson<any>(page, "/api/notificaciones/unread_count/")).count).toBe(0)
    expect(failures).toEqual([])
  })

  test("marcar todas las notificaciones sincroniza otra pestaña", async ({ page, context }) => {
    const failures = watchRuntimeFailures(page)
    const subject = uniqueQaText("Notificaciones entre pestañas")

    await clearParentUnread(page)
    await sendFamilyMessageViaApi(page, subject, "Notificacion para sincronizar pestañas")
    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)

    const otherPage = await context.newPage()
    const otherFailures = watchRuntimeFailures(otherPage)
    await otherPage.goto("/dashboard")
    await expect(notificationBadge(page)).toHaveText("1", { timeout: 15_000 })
    await expect(notificationBadge(otherPage)).toHaveText("1", { timeout: 15_000 })

    await page.locator(".sidebar-bell button").click()
    await page.getByRole("button", { name: /marcar todas le/i }).click()

    await expect.poll(async () => (await apiJson<any>(page, "/api/notificaciones/unread_count/")).count).toBe(0)
    await expect(notificationBadge(page)).toHaveCount(0)
    await expect(notificationBadge(otherPage)).toHaveCount(0, { timeout: 15_000 })
    expect(failures).toEqual([])
    expect(otherFailures).toEqual([])
    await otherPage.close()
  })

  test("la campana tolera un error del preview y conserva la pagina operativa", async ({ page }) => {
    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.route("**/api/notificaciones/recientes/**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Servicio temporalmente no disponible" }),
      })
    })

    await page.locator(".sidebar-bell button").click()
    await expect(page.getByText(/no ten.*notificaciones por ahora/i)).toBeVisible()
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.locator(".app-sidebar")).toBeVisible()
  })

  test("padre y alumno conservan sus rutas directas despues de refresh", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_padre")
    await expect(page).toHaveURL(/\/dashboard/)
    await page.goto("/mis-hijos?alumno=QA001&tab=sanciones")
    await expect(page).toHaveURL(/\/alumnos\/[^?]+.*from=%2Fmis-hijos/)
    await expect(page.getByRole("heading", { name: /ana qa/i })).toBeVisible()
    await expect(page.getByText(/sanciones/i).first()).toBeVisible()
    await page.reload()
    await expect(page.getByRole("heading", { name: /ana qa/i })).toBeVisible()

    await loginAs(page, "qa_alumno")
    await expect(page).toHaveURL(/\/dashboard/)
    for (const route of [
      { path: "/mis-notas", from: "mis-notas", text: /notas/i },
      { path: "/mis-asistencias", from: "mis-asistencias", text: /inasistencias|asistencias/i },
      { path: "/mis-sanciones", from: "mis-sanciones", text: /sanciones/i },
    ]) {
      await page.goto(route.path)
      await expect(page).toHaveURL(new RegExp(`/alumnos/[^?]+.*from=${route.from}`))
      await expect(page.getByText(route.text).first()).toBeVisible()
      await page.reload()
      await expect(page).toHaveURL(new RegExp(`from=${route.from}`))
      await expect(page.getByText(route.text).first()).toBeVisible()
    }
    expect(failures).toEqual([])
  })

  test("menus mobile exponen solo las rutas principales de cada rol", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    await openMobileMenu(page)
    await expect(page.locator('.app-sidebar a[href="/mis-cursos"]')).toBeVisible()
    await expect(page.locator('.app-sidebar a[href="/pasar_asistencia"]')).toHaveCount(0)

    await loginAs(page, "qa_preceptor")
    await expect(page).toHaveURL(/\/dashboard/)
    await openMobileMenu(page)
    await page.locator('.app-sidebar a[href="/pasar_asistencia"]').click()
    await expect(page).toHaveURL(/\/pasar_asistencia/)
    await expect(page.getByRole("heading", { name: /asistencia/i })).toBeVisible()

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/admin\/colegio|\/dashboard/)
    await page.goto("/admin/colegio")
    await openMobileMenu(page)
    await expect(page.locator('.app-sidebar .sidebar-link[href="/admin/colegio"]')).toBeVisible()
    await expect(page.locator(".app-sidebar .sidebar-link")).toHaveCount(1)

    await loginAs(page, "qa_platform_admin")
    await expect(page).toHaveURL(/\/admin\/colegio|\/dashboard/)
    await page.goto("/admin/plataforma")
    await openMobileMenu(page)
    await expect(page.locator('.app-sidebar .sidebar-link[href="/admin/plataforma"]')).toBeVisible()
    await expect(page.locator('.app-sidebar .sidebar-link[href="/admin/colegio"]')).toBeVisible()
    expect(failures).toEqual([])
  })
})
