import { expect, test, type Page } from "@playwright/test"

import { apiJson, loginAs, watchRuntimeFailures } from "./helpers"

type RouteCheck = {
  path: string
  heading: string | RegExp
}

async function expectSemanticPageStructure(page: Page, route: RouteCheck) {
  await page.goto(route.path)
  await expect(page.getByRole("main")).toBeVisible({ timeout: 25_000 })
  await expect(page.getByRole("heading", { name: route.heading }).first()).toBeVisible({
    timeout: 25_000,
  })

  await expect(page.locator("main")).toHaveCount(1)
  await expect(page.locator("nav")).toHaveCount(1)

  const levels = await page.locator("h1, h2, h3, h4, h5, h6").evaluateAll((headings) =>
    headings
      .filter((heading) => {
        const style = getComputedStyle(heading)
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          heading.getClientRects().length > 0
        )
      })
      .map((heading) => Number(heading.tagName.slice(1)))
  )

  expect(
    levels.filter((level) => level === 1),
    `${route.path}: niveles visibles ${levels.join(",")}`
  ).toHaveLength(1)
  for (let index = 1; index < levels.length; index += 1) {
    expect(
      levels[index] - levels[index - 1],
      `${route.path}: salto de h${levels[index - 1]} a h${levels[index]}`
    ).toBeLessThanOrEqual(1)
  }
}

function asList(data: any) {
  if (Array.isArray(data)) return data
  for (const key of ["results", "cursos", "mensajes", "items"]) {
    if (Array.isArray(data?.[key])) return data[key]
  }
  return []
}

function getCourseRouteId(course: any) {
  return course?.school_course_id ?? course?.id ?? course?.pk ?? course?.code ?? course?.curso
}

test.describe("QA semantica ampliada de rutas protegidas", () => {
  const roleRoutes: Array<{ user: string; routes: RouteCheck[] }> = [
    {
      user: "qa_profesor",
      routes: [
        { path: "/agregar_nota", heading: /nueva nota|carga de notas/i },
        { path: "/mis-cursos", heading: "Cursos" },
        { path: "/calendario", heading: "Calendario" },
        { path: "/reportes", heading: "Reportes" },
        { path: "/perfil", heading: "Perfil" },
      ],
    },
    {
      user: "qa_preceptor",
      routes: [
        { path: "/pasar_asistencia", heading: "Asistencia" },
        { path: "/alumnos", heading: "Alumnos" },
        { path: "/mis-cursos", heading: "Cursos" },
      ],
    },
    {
      user: "qa_padre",
      routes: [
        { path: "/mis-hijos", heading: /ana qa/i },
        { path: "/calendario", heading: "Calendario" },
        { path: "/reportes", heading: "Reportes" },
        { path: "/perfil", heading: "Perfil" },
      ],
    },
    {
      user: "qa_alumno",
      routes: [
        { path: "/mis-notas", heading: /ana qa/i },
        { path: "/mis-sanciones", heading: /ana qa/i },
        { path: "/mis-asistencias", heading: /ana qa/i },
        { path: "/calendario", heading: /calendario/i },
        { path: "/perfil", heading: /perfil/i },
      ],
    },
    {
      user: "qa_school_admin",
      routes: [
        { path: "/admin/colegio", heading: "Admin colegio" },
        { path: "/admin/colegio/usuarios", heading: "Admin colegio" },
        { path: "/admin/colegio/nuevo-usuario", heading: "Admin colegio" },
        { path: "/admin/colegio/asignacion-profesores", heading: "Admin colegio" },
        { path: "/admin/colegio/asignacion-preceptores", heading: "Admin colegio" },
        { path: "/admin/colegio/cursos", heading: "Admin colegio" },
      ],
    },
    {
      user: "qa_platform_admin",
      routes: [
        { path: "/admin/plataforma", heading: "Admin plataforma" },
        { path: "/admin/plataforma/colegios", heading: "Admin plataforma" },
        { path: "/admin/plataforma/colegios/nuevo", heading: "Admin plataforma" },
        { path: "/admin/plataforma/admins", heading: "Admin plataforma" },
        { path: "/admin/plataforma/alumnos/importar", heading: "Admin plataforma" },
        { path: "/admin/plataforma/backups", heading: "Admin plataforma" },
      ],
    },
  ]

  for (const group of roleRoutes) {
    test(`${group.user} conserva landmarks y jerarquia de encabezados`, async ({ page }) => {
      const failures = watchRuntimeFailures(page)
      await loginAs(page, group.user)

      for (const route of group.routes) {
        await expectSemanticPageStructure(page, route)
      }

      expect(failures).toEqual([])
    })
  }
})

test.describe("QA semantica de rutas protegidas dinamicas y legacy", () => {
  test("profesor conserva semantica en el detalle de su curso", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_profesor")
    const courses = asList(await apiJson(page, "/api/cursos/mis-cursos/"))
    const courseId = getCourseRouteId(courses[0])
    expect(courseId).toBeTruthy()

    await expectSemanticPageStructure(page, {
      path: `/mis-cursos/${encodeURIComponent(String(courseId))}`,
      heading: "Cursos",
    })
    await expect(page.getByPlaceholder(/buscar alumno/i)).toBeVisible()
    expect(failures).toEqual([])
  })

  test("preceptor conserva semantica en alumnos por curso y alias legacy", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_preceptor")
    const courses = asList(await apiJson(page, "/api/preceptor/cursos/"))
    const courseId = getCourseRouteId(courses[0])
    expect(courseId).toBeTruthy()

    await page.goto(`/gestion_alumnos/${encodeURIComponent(String(courseId))}`)
    await expect(page).toHaveURL(
      new RegExp(`/alumnos/curso/${encodeURIComponent(String(courseId))}`)
    )
    await expectSemanticPageStructure(page, {
      path: `/alumnos/curso/${encodeURIComponent(String(courseId))}`,
      heading: /alumnos del curso/i,
    })
    await expect(page.getByRole("heading", { name: /alumnos del curso/i })).toBeVisible()
    expect(failures).toEqual([])
  })

  test("padre conserva semantica en historial e hilo directo", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_padre")

    await expectSemanticPageStructure(page, {
      path: "/historial_notas",
      heading: /panel de qa padre/i,
    })

    const inbox = asList(await apiJson(page, "/api/mensajes/recibidos/"))
    const message = inbox[0]
    const threadId = message?.thread_id ?? message?.id
    expect(threadId).toBeTruthy()
    await expectSemanticPageStructure(page, {
      path: `/mensajes/hilo/${encodeURIComponent(String(threadId))}`,
      heading: "Mensajes",
    })
    await expect(page.getByLabel("Mensaje")).toBeVisible()
    expect(failures).toEqual([])
  })

  test("alumno conserva semantica en la ruta legacy de sanciones", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    await loginAs(page, "qa_alumno")
    await expectSemanticPageStructure(page, {
      path: "/alumnos/QA001/sanciones",
      heading: /mis sanciones/i,
    })
    await expect(page.getByRole("heading", { name: /mis sanciones/i })).toBeVisible()
    expect(failures).toEqual([])
  })
})
