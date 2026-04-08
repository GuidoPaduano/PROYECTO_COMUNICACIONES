import {
  findCourseOption,
  getCourseDisplayName,
  getCourseSchoolCourseId,
  normalizeCourseList,
  resolveCanonicalCourseValue,
} from "@/app/_lib/courses"

describe("course selection helpers", () => {
  it("prioritizes school_course_id but preserves the course code", () => {
    const courses = normalizeCourseList([
      { id: "1A", code: "1A", nombre: "1A Norte", school_course_id: 14 },
      { id: "2A", code: "2A", nombre: "2A Norte", school_course_id: 15 },
    ])

    expect(findCourseOption(courses, "14")).toMatchObject({
      value: "14",
      courseCode: "1A",
      schoolCourseId: 14,
      label: "1A Norte",
    })
    expect(findCourseOption(courses, "1A")).toMatchObject({
      value: "14",
      courseCode: "1A",
      schoolCourseId: 14,
      label: "1A Norte",
    })
  })

  it("resolves school_course_id from canonical selectors", () => {
    const courses = normalizeCourseList([
      { id: "1A", code: "1A", nombre: "1A Norte", school_course_id: 14 },
    ])

    expect(getCourseSchoolCourseId("14", courses)).toBe(14)
    expect(getCourseSchoolCourseId("1A", courses)).toBe(14)
    expect(resolveCanonicalCourseValue("1A", courses)).toBe("14")
  })

  it("keeps ALL markers resolvable only when they are explicit options", () => {
    const courses = normalizeCourseList(["ALL"])

    expect(findCourseOption(courses, "ALL")).toMatchObject({
      value: "ALL",
      courseCode: "ALL",
      schoolCourseId: null,
    })
    expect(resolveCanonicalCourseValue("ALL", courses)).toBe("ALL")
  })

  it("does not recover ids when the selector list lacks school_course_id", () => {
    const courses = normalizeCourseList([
      { id: "1A", code: "1A", nombre: "1A Norte" },
    ])

    expect(findCourseOption(courses, "1A")).toMatchObject({
      value: "1A",
      courseCode: "1A",
      schoolCourseId: null,
    })
    expect(getCourseSchoolCourseId("1A", courses)).toBeNull()
    expect(resolveCanonicalCourseValue("1A", courses)).toBe("")
    expect(resolveCanonicalCourseValue("1A", [])).toBe("")
  })

  it("resolves legacy route params to school_course_id only when a real catalog match exists", () => {
    const courses = normalizeCourseList([
      { id: "1A", code: "1A", nombre: "1A Norte", school_course_id: 14 },
    ])

    expect(getCourseSchoolCourseId("1A", courses)).toBe(14)
    expect(getCourseSchoolCourseId("14", courses)).toBe(14)
    expect(getCourseSchoolCourseId("1A", [])).toBeNull()
    expect(resolveCanonicalCourseValue("14", courses)).toBe("14")
    expect(resolveCanonicalCourseValue("1A", courses)).toBe("14")
  })

  it("prefers school_course_name and then curso for display labels", () => {
    expect(
      getCourseDisplayName({
        school_course_name: "1A Norte",
        curso: "1A",
      })
    ).toBe("1A Norte")

    expect(
      getCourseDisplayName({
        curso: "2A",
      })
    ).toBe("2A")
  })
})
