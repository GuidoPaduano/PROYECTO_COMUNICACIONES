/**
 * Formats a date string as DD-MM-YYYY.
 *
 * Safe against the UTC off-by-one issue: "YYYY-MM-DD" strings are parsed
 * directly from their components without going through Date's UTC constructor.
 * For datetime strings (ISO 8601 with time), local Date methods are used.
 */
export function formatFecha(
  iso: string | null | undefined,
  fallback = "—"
): string {
  if (!iso) return fallback
  const s = String(iso)
  // Fast path for YYYY-MM-DD — pure string manipulation, no timezone risk
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (m) return `${m[3]}-${m[2]}-${m[1]}`
  // Fallback for datetime strings (ISO 8601 with time component)
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  const dd = String(d.getDate()).padStart(2, "0")
  const mm = String(d.getMonth() + 1).padStart(2, "0")
  return `${dd}-${mm}-${d.getFullYear()}`
}

/**
 * Formats a datetime string as DD-MM-YYYY HH:MM.
 */
export function formatFechaHora(
  iso: string | null | undefined,
  fallback = "—"
): string {
  if (!iso) return fallback
  const d = new Date(String(iso))
  if (isNaN(d.getTime())) return String(iso)
  const dd = String(d.getDate()).padStart(2, "0")
  const mm = String(d.getMonth() + 1).padStart(2, "0")
  const hh = String(d.getHours()).padStart(2, "0")
  const min = String(d.getMinutes()).padStart(2, "0")
  return `${dd}-${mm}-${d.getFullYear()} ${hh}:${min}`
}
