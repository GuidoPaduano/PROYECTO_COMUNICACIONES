"use client"

const COURSE_CATALOG_MAX_AGE_MS = 30000
const courseCatalogCache = new Map()
const courseCatalogPromises = new Map()

function toCleanString(value) {
  return String(value ?? "").trim()
}

function parseSchoolCourseId(value) {
  const raw = toCleanString(value)
  if (!raw || !/^\d+$/.test(raw)) return null
  try {
    return Number(raw)
  } catch {
    return null
  }
}

function inferCourseCode(raw, schoolCourseId) {
  const candidates = [
    raw?.courseCode,
    raw?.code,
    raw?.curso,
    raw?.course_code,
    raw?.codigo,
    schoolCourseId == null ? raw?.id : "",
    schoolCourseId == null ? raw?.value : "",
  ]

  for (const candidate of candidates) {
    const text = toCleanString(candidate)
    if (!text) continue
    if (schoolCourseId != null && /^\d+$/.test(text)) continue
    return text
  }
  return ""
}

export function normalizeCourseOption(raw) {
  if (raw == null) return null

  if (typeof raw === "string" || typeof raw === "number") {
    const text = toCleanString(raw)
    if (!text) return null
    return {
      value: text,
      label: text,
      courseCode: /^\d+$/.test(text) ? "" : text,
      schoolCourseId: parseSchoolCourseId(text),
      rawSelectorId: text,
      raw,
    }
  }

  const schoolCourseId =
    raw?.school_course_id ??
    raw?.schoolCourseId ??
    null
  const parsedSchoolCourseId = parseSchoolCourseId(schoolCourseId)
  const rawSelectorId = toCleanString(raw?.id ?? raw?.value ?? raw?.curso ?? raw?.code ?? raw?.codigo ?? "")
  const courseCode = inferCourseCode(raw, parsedSchoolCourseId)
  const label = toCleanString(
    raw?.nombre ??
      raw?.label ??
      raw?.school_course_name ??
      raw?.name ??
      courseCode ??
      rawSelectorId
  )
  const value = parsedSchoolCourseId != null ? String(parsedSchoolCourseId) : rawSelectorId || courseCode

  if (!value && !label) return null

  return {
    value: value || label,
    label: label || courseCode || rawSelectorId || value,
    courseCode,
    schoolCourseId: parsedSchoolCourseId,
    rawSelectorId: rawSelectorId || courseCode || value,
    raw,
  }
}

export function normalizeCourseList(input) {
  const items = Array.isArray(input) ? input : []
  const out = []
  const seen = new Set()

  for (const item of items) {
    const course = normalizeCourseOption(item)
    if (!course?.value) continue
    const key = [
      course.schoolCourseId != null ? `sid:${course.schoolCourseId}` : "",
      course.courseCode ? `code:${course.courseCode}` : "",
      `value:${course.value}`,
    ]
      .filter(Boolean)
      .join("|")
    if (seen.has(key)) continue
    seen.add(key)
    out.push(course)
  }

  return out
}

export function parseCourseListPayload(payload) {
  if (Array.isArray(payload)) return normalizeCourseList(payload)
  if (Array.isArray(payload?.cursos)) return normalizeCourseList(payload.cursos)
  if (Array.isArray(payload?.results)) return normalizeCourseList(payload.results)
  return []
}

function getFreshCourseCatalogCache(cacheKey) {
  const entry = courseCatalogCache.get(cacheKey)
  if (!entry) return null
  if (entry.expiresAt <= Date.now()) {
    courseCatalogCache.delete(cacheKey)
    return null
  }
  return entry.data
}

export function invalidateCourseCatalogCache(cacheKey = "") {
  const key = toCleanString(cacheKey)
  if (!key) {
    courseCatalogCache.clear()
    courseCatalogPromises.clear()
    return
  }
  courseCatalogCache.delete(key)
  courseCatalogPromises.delete(key)
}

export async function loadCourseCatalog(options = {}) {
  const fetcher = options?.fetcher
  const urls = Array.isArray(options?.urls) ? options.urls : [options?.urls]
  const cacheKey = toCleanString(options?.cacheKey || "default")
  const force = options?.force === true
  const maxAgeMs =
    Number.isFinite(Number(options?.maxAgeMs)) && Number(options?.maxAgeMs) > 0
      ? Number(options.maxAgeMs)
      : COURSE_CATALOG_MAX_AGE_MS

  if (typeof fetcher !== "function") return []

  const urlList = urls.map((url) => toCleanString(url)).filter(Boolean)
  if (urlList.length === 0) return []

  if (!force) {
    const cached = getFreshCourseCatalogCache(cacheKey)
    if (cached) return cached
  }

  if (!force && courseCatalogPromises.has(cacheKey)) {
    return courseCatalogPromises.get(cacheKey)
  }

  const promise = (async () => {
    let resolved = []

    for (const url of urlList) {
      try {
        const res = await fetcher(url)
        if (!res?.ok) continue
        const data = await res.json().catch(() => ({}))
        const list = parseCourseListPayload(data)
        resolved = list
        if (list.length > 0) break
      } catch {
        // ignore and try next endpoint
      }
    }

    const normalized = normalizeCourseList(resolved)
    courseCatalogCache.set(cacheKey, {
      data: normalized,
      expiresAt: Date.now() + maxAgeMs,
    })
    return normalized
  })()

  courseCatalogPromises.set(cacheKey, promise)

  try {
    return await promise
  } finally {
    if (courseCatalogPromises.get(cacheKey) === promise) {
      courseCatalogPromises.delete(cacheKey)
    }
  }
}

export function findCourseOption(list, selectedValue) {
  const normalizedList = normalizeCourseList(list)
  const wanted = toCleanString(selectedValue)
  if (!wanted) return null

  return (
    normalizedList.find((course) => course.value === wanted) ||
    normalizedList.find((course) => String(course.schoolCourseId ?? "") === wanted) ||
    normalizedList.find((course) => course.courseCode === wanted) ||
    normalizedList.find((course) => course.rawSelectorId === wanted) ||
    null
  )
}

export function getCourseValue(courseLike, list) {
  return findCourseOption(list, courseLike)?.value || normalizeCourseOption(courseLike)?.value || ""
}

export function getCourseCode(courseLike, list) {
  return findCourseOption(list, courseLike)?.courseCode || normalizeCourseOption(courseLike)?.courseCode || ""
}

export function getCourseSchoolCourseId(courseLike, list) {
  const course = findCourseOption(list, courseLike) || normalizeCourseOption(courseLike)
  return course?.schoolCourseId ?? null
}

export function getCourseLabel(courseLike, list) {
  return findCourseOption(list, courseLike)?.label || normalizeCourseOption(courseLike)?.label || ""
}

export function getCourseDisplayName(raw, fallback = "") {
  if (raw == null) return toCleanString(fallback)

  if (typeof raw !== "object") {
    return getCourseLabel(raw) || toCleanString(raw) || toCleanString(fallback)
  }

  const candidates = [
    raw?.school_course_name,
    raw?.course_name,
    raw?.courseName,
    raw?.name,
    raw?.nombre,
    raw?.curso,
    raw?.division,
    raw?.grado,
    fallback,
  ]

  for (const candidate of candidates) {
    const text = toCleanString(candidate)
    if (text) return text
  }

  return ""
}

export function resolveCanonicalCourseValue(courseLike, list) {
  const wanted = toCleanString(courseLike)
  if (!wanted) return ""

  const parsedSchoolCourseId = parseSchoolCourseId(wanted)
  if (parsedSchoolCourseId != null) return String(parsedSchoolCourseId)

  const course = findCourseOption(list, wanted)
  if (!course) return ""
  if (course.courseCode === "ALL") return "ALL"
  if (course.schoolCourseId != null) return String(course.schoolCourseId)
  return ""
}
