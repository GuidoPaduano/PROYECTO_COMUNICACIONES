import { expect, test, type Page } from "@playwright/test"

import { apiJson, apiResponse, loginAs, uniqueQaText, watchRuntimeFailures } from "./helpers"

function compactId(prefix: string) {
  return `${prefix}${Date.now().toString().slice(-8)}`
}

function listFromPayload(payload: any, key: string) {
  if (Array.isArray(payload)) return payload
  return payload?.[key] || payload?.results || payload?.data || []
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

async function getQaSchoolAndCourse(page: Page) {
  const payload = await apiJson<any>(page, "/api/admin/school-courses/")
  const school = listFromPayload(payload, "schools")[0]
  const course = listFromPayload(school, "courses")[0]
  expect(school?.id).toBeTruthy()
  expect(course?.id).toBeTruthy()
  return { school, course }
}

test.describe("QA local admin UI flows", () => {
  test("admin colegio crea un profesor desde la UI con curso inicial", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const username = `qa_ui_prof_${Date.now()}`

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)
    await page.goto("/admin/colegio/nuevo-usuario")
    await expect(page.getByRole("heading", { name: "Nuevo usuario" })).toBeVisible()

    await page.getByLabel("Apellido").fill("Interfaz")
    await page.getByLabel("Nombre").fill("Profesor")
    await page.getByRole("textbox", { name: "Usuario" }).fill(username)
    await page.getByLabel("Email").fill(`${username}@test.local`)
    await page.getByLabel("Contraseña", { exact: true }).fill("QaLocal123!")
    await page.getByLabel("Confirmar contraseña").fill("QaLocal123!")
    await page.getByText("Profesor/a", { exact: true }).click()

    const courseCard = page.getByText(/1A QA/i).locator("..")
    await courseCard.getByRole("checkbox").check()
    await page.getByRole("button", { name: "Crear usuario" }).click()

    await expect(page.getByText("Usuario creado correctamente.")).toBeVisible()
    const overview = await apiJson<any>(page, "/api/admin/staff/")
    const created = listFromPayload(overview, "users").find((user: any) => user?.username === username)
    expect(created?.staff_role).toBe("Profesores")
    expect(created?.assigned_school_courses?.length).toBe(1)
    expect(failures).toEqual([])
  })

  test("admin colegio asigna un usuario como preceptor desde la UI", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)
    const { course } = await getQaSchoolAndCourse(page)
    const beforeOverview = await apiJson<any>(page, "/api/admin/staff/")
    const originalPreceptorIds = listFromPayload(beforeOverview, "users")
      .filter(
        (user: any) =>
          user?.staff_role === "Preceptores" &&
          user?.assigned_school_courses?.some((item: any) => Number(item.id) === Number(course.id))
      )
      .map((user: any) => Number(user.id))

    await page.goto("/admin/colegio/asignacion-preceptores")
    await expect(page.getByRole("heading", { name: /asignacion a preceptores/i })).toBeVisible()
    await page.getByLabel("Curso").selectOption(String(course.id))
    await page.getByLabel(/buscar preceptor/i).fill("qa_preceptor")

    await page.getByRole("checkbox", { name: /qa_preceptor/i }).check()
    await page.getByRole("button", { name: /guardar asignaci/i }).click()
    await expect(page.getByText(/asignaci.n de preceptores actualizada/i)).toBeVisible()

    const overview = await apiJson<any>(page, "/api/admin/staff/")
    const updated = listFromPayload(overview, "users").find((user: any) => user?.username === "qa_preceptor")
    expect(updated?.staff_role).toBe("Preceptores")
    expect(updated?.assigned_school_courses?.some((item: any) => Number(item.id) === Number(course.id))).toBe(true)

    const restored = await apiResponse<any>(page, `/api/admin/staff/course/${course.id}/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        staff_role: "Preceptores",
        user_ids: originalPreceptorIds,
      }),
    })
    expect(restored.ok, JSON.stringify(restored.data)).toBeTruthy()
    expect(failures).toEqual([])
  })

  test("admin colegio edita nombre y email de un usuario desde el directorio", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const username = `qa_ui_edit_${Date.now()}`

    await loginAs(page, "qa_school_admin")
    const { course } = await getQaSchoolAndCourse(page)
    const created = await apiResponse<any>(page, "/api/admin/users/create/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_name: "Nombre",
        last_name: "Original",
        username,
        email: `${username}@test.local`,
        password: "QaLocal123!",
        password_confirm: "QaLocal123!",
        role: "Profesores",
        school_course_ids: [course.id],
      }),
    })
    expect(created.status, JSON.stringify(created.data)).toBe(201)

    await page.goto("/admin/colegio/usuarios")
    await page.getByRole("button", { name: /Profesores\s+\d+/ }).click()
    await page.getByPlaceholder(/buscar por usuario/i).fill(username)
    const row = page.getByRole("row").filter({ hasText: username })
    await row.getByRole("button", { name: "Editar datos" }).click()

    const dialog = page.getByRole("dialog")
    await dialog.getByLabel("Nombre").fill("Paula")
    await dialog.getByLabel("Apellido").fill("Actualizada")
    await dialog.getByLabel("Email").fill(`${username}.editado@test.local`)
    await dialog.getByRole("button", { name: "Guardar cambios" }).click()

    await expect(dialog).toBeHidden()
    await expect(page.getByRole("status")).toContainText("Usuario actualizado correctamente")
    const directory = await apiJson<any>(page, "/api/admin/school-users/")
    const updated = listFromPayload(directory, "profesores").find(
      (item: any) => item?.username === username
    )
    expect(updated?.full_name).toBe("Paula Actualizada")
    expect(updated?.email).toBe(`${username}.editado@test.local`)
    expect(failures).toEqual([])
  })

  test("admin colegio vincula un alumno sin tutor a un padre desde el directorio", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const legajo = compactId("UIL")

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)
    const { course } = await getQaSchoolAndCourse(page)
    const studentResponse = await apiResponse<any>(page, "/api/alumnos/crear/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nombre: "Alumno",
        apellido: "Sin Tutor",
        id_alumno: legajo,
        school_course_id: course.id,
      }),
    })
    expect(studentResponse.status, JSON.stringify(studentResponse.data)).toBe(201)

    await page.goto("/admin/colegio/usuarios")
    await expect(page.getByRole("heading", { name: "Usuarios del colegio" })).toBeVisible()
    await page.getByRole("button", { name: /Padres\s+\d+/ }).click()

    const parentRow = page.getByRole("row").filter({ hasText: "qa_padre" })
    await parentRow.getByRole("button", { name: "Vincular alumno" }).click()
    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()

    const selects = dialog.getByRole("combobox")
    await selects.nth(0).click()
    const courseLabel = [course.code, course.name].filter(Boolean).join(" - ")
    await page.getByRole("option", { name: new RegExp(escapeRegExp(courseLabel), "i") }).click()
    await selects.nth(1).click()
    await page.getByRole("option", { name: new RegExp(legajo, "i") }).click()
    await dialog.getByRole("button", { name: "Vincular", exact: true }).click()
    await expect(dialog).toBeHidden()

    const directory = await apiJson<any>(page, "/api/admin/school-users/")
    const parent = listFromPayload(directory, "padres").find((item: any) => item?.username === "qa_padre")
    expect(parent?.children?.some((child: any) => child?.id_alumno === legajo)).toBe(true)
    expect(failures).toEqual([])
  })

  test("admin colegio crea un padre desde la UI y vincula su alumno inicial", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const legajo = compactId("UIP")
    const username = `qa_ui_padre_${Date.now()}`

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)
    const { course } = await getQaSchoolAndCourse(page)
    const studentResponse = await apiResponse<any>(page, "/api/alumnos/crear/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nombre: "Hijo",
        apellido: "Familia UI",
        id_alumno: legajo,
        school_course_id: course.id,
      }),
    })
    expect(studentResponse.status, JSON.stringify(studentResponse.data)).toBe(201)

    await page.goto("/admin/colegio/nuevo-usuario")
    await page.getByLabel("Apellido").fill("Familia")
    await page.getByLabel("Nombre").fill("Tutor")
    await page.getByRole("textbox", { name: "Usuario" }).fill(username)
    await page.getByLabel("Email").fill(`${username}@test.local`)
    await page.getByLabel("Contraseña", { exact: true }).fill("QaLocal123!")
    await page.getByLabel("Confirmar contraseña").fill("QaLocal123!")
    await page.getByText("Padre, madre o tutor", { exact: true }).click()
    await page.getByLabel("Buscar alumno").fill(legajo)

    await page.getByRole("checkbox", { name: new RegExp(legajo, "i") }).check()
    await page.getByRole("button", { name: "Crear usuario" }).click()
    await expect(page.getByText("Usuario creado correctamente.")).toBeVisible()

    const directory = await apiJson<any>(page, "/api/admin/school-users/")
    const parent = listFromPayload(directory, "padres").find((item: any) => item?.username === username)
    expect(parent?.children?.some((child: any) => child?.id_alumno === legajo)).toBe(true)

    await page.goto("/admin/colegio/usuarios")
    await page.getByRole("button", { name: /Padres\s+\d+/ }).click()
    await page.getByPlaceholder(/buscar por usuario/i).fill(username)
    await expect(page.getByRole("row").filter({ hasText: username })).toContainText("Hijo Familia UI")
    expect(failures).toEqual([])
  })

  test("admin colegio asigna un profesor y conserva la seleccion tras recargar", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const username = `qa_ui_asig_prof_${Date.now()}`

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)
    const { course } = await getQaSchoolAndCourse(page)
    const created = await apiResponse<any>(page, "/api/admin/users/create/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_name: "Asignacion",
        last_name: "Profesor",
        username,
        email: `${username}@test.local`,
        password: "QaLocal123!",
        password_confirm: "QaLocal123!",
        role: "Profesores",
        school_course_ids: [],
      }),
    })
    expect(created.status, JSON.stringify(created.data)).toBe(201)

    await page.goto("/admin/colegio/asignacion-profesores")
    await expect(page.getByRole("heading", { name: /asignacion a profesores/i })).toBeVisible()
    await page.getByLabel("Curso").selectOption(String(course.id))
    await page.getByLabel(/buscar profesor/i).fill(username)
    const professorCheckbox = page.getByRole("checkbox", { name: new RegExp(username, "i") })
    await professorCheckbox.check()
    await page.getByRole("button", { name: /guardar asignaci/i }).click()
    await expect(page.getByText(/asignaci.n de profesores actualizada/i)).toBeVisible()

    await page.reload()
    await page.getByLabel("Curso").selectOption(String(course.id))
    await page.getByLabel(/buscar profesor/i).fill(username)
    await expect(page.getByRole("checkbox", { name: new RegExp(username, "i") })).toBeChecked()

    const overview = await apiJson<any>(page, "/api/admin/staff/")
    const updated = listFromPayload(overview, "users").find((user: any) => user?.username === username)
    const seededProfessor = listFromPayload(overview, "users").find(
      (user: any) => user?.username === "qa_profesor"
    )
    expect(updated?.assigned_school_courses?.some((item: any) => Number(item.id) === Number(course.id))).toBe(true)
    expect(
      seededProfessor?.assigned_school_courses?.some(
        (item: any) => Number(item.id) === Number(course.id)
      )
    ).toBe(true)
    expect(failures).toEqual([])
  })

  test("un profesor no puede abrir herramientas administrativas por URL directa", async ({ page }) => {
    const failures = watchRuntimeFailures(page)

    await loginAs(page, "qa_profesor")
    await expect(page).toHaveURL(/\/dashboard/)
    for (const path of [
      "/admin/colegio/nuevo-usuario",
      "/admin/colegio/asignacion-profesores",
      "/admin/colegio/asignacion-preceptores",
    ]) {
      await page.goto(path)
      await expect(page.getByText(/acceso restringido/i)).toBeVisible()
    }
    expect(failures).toEqual([])
  })

  test("admin plataforma edita y confirma el borrado de un colegio desde la UI", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const slug = compactId("ui-school-").toLowerCase()
    const name = uniqueQaText("Colegio UI")
    const shortName = compactId("UI")
    const editedShortName = compactId("EDIT")

    await loginAs(page, "qa_platform_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)
    const created = await apiResponse<any>(page, "/api/admin/schools/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        short_name: shortName,
        slug,
        primary_color: "#1D4ED8",
        accent_color: "#16A34A",
        is_active: true,
      }),
    })
    expect(created.status, JSON.stringify(created.data)).toBe(201)

    await page.goto("/admin/plataforma/colegios")
    await expect(page.getByRole("heading", { name: "Colegios" })).toBeVisible()
    await page.getByPlaceholder(/buscar por nombre/i).fill(slug)
    await page.getByRole("row").filter({ hasText: slug }).click()

    await page.getByLabel("Nombre corto").fill(editedShortName)
    await page.getByRole("button", { name: "Guardar cambios" }).click()
    await expect(page.getByText("Colegio actualizado.")).toBeVisible()

    await page.getByRole("button", { name: `Acciones para ${name}` }).click()
    await page.getByRole("menuitem", { name: "Borrar colegio" }).click()
    const dialog = page.getByRole("dialog")
    await expect(dialog.getByRole("heading", { name: /seguro que quiere borrar/i })).toBeVisible()
    await dialog.getByRole("button", { name: "Borrar colegio" }).click()
    await expect(page.getByText("Colegio borrado correctamente.")).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("row").filter({ hasText: slug })).toHaveCount(0)
    expect(failures).toEqual([])
  })
})
