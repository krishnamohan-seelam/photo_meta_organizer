/**
 * Timeframe filter value for photos without an EXIF capture date. The backend no
 * longer falls back to the file's modification time (PMO-24), so these are
 * shown as "Unknown date" rather than under the day they were copied; the search
 * request asks for them with `has_capture_date: false`.
 */
export const UNKNOWN_DATE = 'unknown'
