import { expect, test, type Page } from "@playwright/test"

import { apiJson, apiResponse, loginAs, QA_SCHOOL, uniqueQaText, watchRuntimeFailures } from "./helpers"

function compactId(prefix: string) {
  return `${prefix}${Date.now().toString().slice(-8)}`
}

function listFromPayload(payload: any, key: string) {
  if (Array.isArray(payload)) return payload
  return payload?.[key] || payload?.results || payload?.data || []
}

async function importCsv(page: Page, csv: string, commit: boolean) {
  return await page.evaluate(
    async ({ csv, commit, school }) => {
      const form = new FormData()
      form.append("file", new File([csv], "qa-import.csv", { type: "text/csv" }))
      form.append("commit", commit ? "true" : "false")
      form.append("school", school)
      const response = await fetch("/api/admin/alumnos/import/", {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "X-School": school,
        },
        body: form,
      })
      const data = await response.json().catch(() => ({}))
      return { status: response.status, ok: response.ok, data }
    },
    { csv, commit, school: QA_SCHOOL }
  )
}

test.describe("QA local admin and import flows", () => {
  test("admin colegio crea curso y profesor asignado solo accede a ese curso", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const code = compactId("QAC")
    const username = `qa_prof_${Date.now()}`

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)

    const initial = await apiJson<any>(page, "/api/admin/school-courses/")
    const school = listFromPayload(initial, "schools")[0]
    expect(school?.id).toBeTruthy()
    const existingCourse = listFromPayload(school, "courses").find((course: any) => String(course?.code || "").includes("1A"))
    expect(existingCourse?.id).toBeTruthy()

    const createCourse = await apiResponse<any>(page, `/api/admin/school-courses/${school.id}/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        name: `Curso ${code}`,
        is_active: true,
      }),
    })
    expect(createCourse.ok, JSON.stringify(createCourse.data)).toBeTruthy()
    const newCourse = createCourse.data?.course
    expect(newCourse?.id).toBeTruthy()

    const createUser = await apiResponse<any>(page, "/api/admin/users/create/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        first_name: "QA",
        last_name: "Profesor",
        email: `${username}@test.local`,
        password: "QaLocal123!",
        password_confirm: "QaLocal123!",
        role: "Profesores",
        school_course_ids: [newCourse.id],
      }),
    })
    expect(createUser.ok, JSON.stringify(createUser.data)).toBeTruthy()
    const user = createUser.data?.user
    expect(user?.id).toBeTruthy()
    expect(user?.assigned_school_courses?.some((course: any) => Number(course.id) === Number(newCourse.id))).toBe(true)

    const overview = await apiJson<any>(page, "/api/admin/staff/")
    const createdInOverview = listFromPayload(overview, "users").find((item: any) => item?.username === username)
    expect(createdInOverview?.assigned_school_courses?.some((course: any) => Number(course.id) === Number(newCourse.id))).toBe(true)

    await loginAs(page, username)
    await expect(page).toHaveURL(/\/dashboard/)
    const ownCourseRoster = await apiResponse(page, `/api/alumnos/?school_course_id=${encodeURIComponent(String(newCourse.id))}`)
    expect(ownCourseRoster.ok, JSON.stringify(ownCourseRoster.data)).toBeTruthy()

    const otherCourseRoster = await apiResponse(page, `/api/alumnos/?school_course_id=${encodeURIComponent(String(existingCourse.id))}`)
    expect(otherCourseRoster.status).toBe(403)
    expect(failures).toEqual([])
  })

  test("admin plataforma previsualiza e importa alumnos por CSV; admin colegio no puede importar", async ({ page }) => {
    const failures = watchRuntimeFailures(page)
    const courseCode = compactId("IMP")
    const legajo = compactId("LEG")
    const csv = `nombre,apellido,curso,legajo\nImportado,QA,${courseCode},${legajo}\n`

    await loginAs(page, "qa_school_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/colegio)/)
    const forbidden = await importCsv(page, csv, false)
    expect(forbidden.status).toBe(403)

    await loginAs(page, "qa_platform_admin")
    await expect(page).toHaveURL(/\/(?:dashboard|admin\/plataforma|admin\/colegio)/)

    const preview = await importCsv(page, csv, false)
    expect(preview.ok, JSON.stringify(preview.data)).toBeTruthy()
    expect(preview.data?.summary?.valid).toBe(1)
    expect(preview.data?.summary?.errors).toBe(0)
    expect(preview.data?.summary?.created).toBe(0)
    expect(preview.data?.courses_to_create?.some((course: any) => course?.code === courseCode)).toBe(true)

    const committed = await importCsv(page, csv, true)
    expect(committed.status).toBe(201)
    expect(committed.data?.summary?.created).toBe(1)
    expect(committed.data?.summary?.created_courses).toBe(1)
    expect(committed.data?.created?.some((student: any) => student?.id_alumno === legajo)).toBe(true)

    const duplicatePreview = await importCsv(page, csv, false)
    expect(duplicatePreview.ok, JSON.stringify(duplicatePreview.data)).toBeTruthy()
    expect(duplicatePreview.data?.summary?.skipped).toBe(1)

    const invalid = await importCsv(page, "nombre,apellido,curso,legajo\nSinCurso,QA,,\n", false)
    expect(invalid.ok, JSON.stringify(invalid.data)).toBeTruthy()
    expect(invalid.data?.summary?.errors).toBeGreaterThan(0)
    expect(failures).toEqual([])
  })
})
