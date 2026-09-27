import type { PhotoMetadata } from '../types/metadata'

/**
 * Timeframe filter value for photos without an EXIF capture date. The backend no
 * longer falls back to the file's modification time (PMO-24), so these are
 * shown as "Unknown date" rather than under the day they were copied.
 */
export const UNKNOWN_DATE = 'unknown'

/** Four-digit capture year, or null when the photo has no capture date. */
export function captureYear(photo: PhotoMetadata): string | null {
  return photo.exif.captured_at ? photo.exif.captured_at.substring(0, 4) : null
}

/** Whether `photo` falls in a timeframe filter value ('all', a year, or UNKNOWN_DATE). */
export function matchesTimeframe(photo: PhotoMetadata, timeframe: string): boolean {
  if (timeframe === 'all') return true
  const year = captureYear(photo)
  return timeframe === UNKNOWN_DATE ? year === null : year === timeframe
}
