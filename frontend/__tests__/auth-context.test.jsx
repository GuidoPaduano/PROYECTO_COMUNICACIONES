import {
  buildSchoolLoginHref,
  clearTokens,
  getPreviewRole,
  getSchoolSlugFromHost,
  getSessionContext,
  sanitizePostLoginPath,
  selectSessionSchool,
  setPreviewRole,
  syncSessionContext,
} from "@/app/_lib/auth"

describe("auth session context", () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    window.localStorage.clear()
  })

  it("stores school context from whoami payload", () => {
    syncSessionContext({
      username: "director",
      full_name: "Ana Director",
      groups: ["Directivos"],
      is_superuser: true,
      school: {
        id: 7,
        name: "Colegio Norte",
        short_name: "Norte",
        slug: "colegio-norte",
        logo_url: "/imagenes/Logo%20Color.png",
        primary_color: "#123456",
        accent_color: "#654321",
        is_active: true,
      },
    })

    expect(getSessionContext()).toEqual({
      userLabel: "Ana Director",
      username: "director",
      groups: ["Directivos"],
      role: "",
      isSuperuser: true,
      school: {
        id: 7,
        name: "Colegio Norte",
        short_name: "Norte",
        slug: "colegio-norte",
        logo_url: "/imagenes/Logo%20Color.png",
        primary_color: "#123456",
        accent_color: "#654321",
        is_active: true,
      },
      availableSchools: [],
    })
  })

  it("stores available schools and lets the superuser switch the active one", () => {
    syncSessionContext({
      username: "admin",
      is_superuser: true,
      school: {
        id: 1,
        name: "Colegio Norte",
        short_name: "Norte",
        slug: "colegio-norte",
        logo_url: "/imagenes/Logo%20Color.png",
        primary_color: "#0c1b3f",
        accent_color: "#1d4ed8",
        is_active: true,
      },
      available_schools: [
        {
          id: 1,
          name: "Colegio Norte",
          short_name: "Norte",
          slug: "colegio-norte",
          logo_url: "/imagenes/Logo%20Color.png",
          primary_color: "#0c1b3f",
          accent_color: "#1d4ed8",
          is_active: true,
        },
        {
          id: 2,
          name: "Colegio Sur",
          short_name: "Sur",
          slug: "colegio-sur",
          logo_url: "/imagenes/tecnova(1).png",
          primary_color: "#123456",
          accent_color: "#abcdef",
          is_active: true,
        },
      ],
    })

    selectSessionSchool("slug:colegio-sur")

    expect(getSessionContext()?.school).toEqual({
      id: 2,
      name: "Colegio Sur",
      short_name: "Sur",
      slug: "colegio-sur",
      logo_url: "/imagenes/tecnova(1).png",
      primary_color: "#123456",
      accent_color: "#abcdef",
      is_active: true,
    })
    expect(getSessionContext()?.availableSchools).toHaveLength(2)
  })

  it("clearTokens limpia el contexto del colegio y la vista previa", () => {
    syncSessionContext({
      username: "admin",
      groups: ["Directivos"],
      school: { id: 1, name: "Escuela Tecnova", slug: "escuela-tecnova", is_active: true },
    })
    setPreviewRole("Padres")

    clearTokens()

    expect(getSessionContext()).toBeNull()
    expect(getPreviewRole()).toBe("")
  })

  it("acepta solo rutas internas seguras para volver despues del login", () => {
    expect(sanitizePostLoginPath("/admin")).toBe("/admin")
    expect(sanitizePostLoginPath("/admin?tab=tools")).toBe("/admin?tab=tools")
    expect(sanitizePostLoginPath("/login")).toBe("")
    expect(sanitizePostLoginPath("https://evil.test")).toBe("")
    expect(sanitizePostLoginPath("//evil.test")).toBe("")
  })

  it("deriva slug de colegio desde hosts compatibles", () => {
    expect(getSchoolSlugFromHost("escuela-tecnova.localhost")).toBe("escuela-tecnova")
    expect(getSchoolSlugFromHost("localhost")).toBe("")
    expect(getSchoolSlugFromHost("127.0.0.1")).toBe("")
  })

  it("arma href de login con query cuando no hay dominio padre configurado", () => {
    expect(buildSchoolLoginHref({ slug: "escuela-tecnova" })).toBe("/login?school=escuela-tecnova")
  })
})
