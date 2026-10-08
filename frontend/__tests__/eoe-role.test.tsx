import { getEffectiveGroups, setPreviewRole } from "@/app/_lib/auth"

describe("EOE permissions", () => {
  beforeEach(() => window.localStorage.clear())

  it("keeps EOE identity and shares Preceptor permissions", () => {
    expect(getEffectiveGroups({ groups: ["EOE"] })).toEqual(["EOE", "Preceptores"])
    expect(getEffectiveGroups({ groups: ["Padres"] })).toEqual(["Padres"])
  })

  it("applies EOE preview only for superusers", () => {
    setPreviewRole("EOE")
    expect(getEffectiveGroups({ groups: [], is_superuser: true })).toEqual(["EOE", "Preceptores"])
    expect(getEffectiveGroups({ groups: ["Padres"] })).toEqual(["Padres"])
  })
})
