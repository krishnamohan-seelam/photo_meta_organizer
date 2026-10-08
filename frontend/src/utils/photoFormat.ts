import type { ExifData, PhotoMetadata } from '../types/metadata'
import { FALLBACK_RATIO, clampRatio } from './justifiedLayout'

const CAMERA_COUNTER = /^(DSC|DSCF|DSC_|IMG|IMG_|R\d|P\d|PXL_|_MG)\w*?[_-]?\d{3,}[_-]?/i

function stripExtension(fileName: string): string {
  const dot = fileName.lastIndexOf('.')
  return dot > 0 ? fileName.slice(0, dot) : fileName
}

/**
 * A human title for a file name (Appendix C): "DSC04928_Tokyo_Tower_Sunset.ARW" is "Tokyo Tower
 * Sunset". A name that is only a camera counter ("IMG_8392.CR3") stays as it is, minus the extension.
 */
export function displayTitle(fileName: string): string {
  const base = stripExtension(fileName)
  // Some tools prefix the counter with underscores ("_DSC9102"); "_MG" is itself a counter prefix.
  const unprefixed = CAMERA_COUNTER.test(base) ? base : base.replace(/^_+/, '')
  const title = unprefixed.replace(CAMERA_COUNTER, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return title === '' || /^[\d\s]+$/.test(title) ? base : title
}

/**
 * Width / height of the photo as its thumbnail shows it. Stored dimensions are the sensor's, but the
 * backend renders thumbnails upright (EXIF transpose), so orientations 5-8 swap them (FR-1c.3).
 */
export function photoAspectRatio(photo: PhotoMetadata): number {
  const { width, height } = photo.dimensions
  if (!width || !height) return FALLBACK_RATIO
  const orientation = photo.exif.orientation ?? 1
  return clampRatio(orientation >= 5 && orientation <= 8 ? height / width : width / height)
}

function trimNumber(value: number): string {
  return String(Number(value.toFixed(1)))
}

/** "35.0 mm" → "35"; null when there is nothing to show. */
function focalMm(exif: ExifData): string | null {
  const mm = exif.focal_length ? parseFloat(exif.focal_length) : NaN
  return Number.isFinite(mm) ? trimNumber(mm) : null
}

/** "1/250s" → "1/250". */
function shutter(exif: ExifData): string | null {
  const value = exif.exposure_time?.trim().replace(/\s*s(ec)?$/i, '')
  return value ? value : null
}

/** The four exposure values for the inspector strip, each "—" when unknown (FR-1e.4). */
export function exposureParts(exif: ExifData): { aperture: string; shutter: string; iso: string; focal: string } {
  return {
    aperture: exif.f_stop ? `ƒ/${trimNumber(exif.f_stop)}` : '—',
    shutter: shutter(exif) ?? '—',
    iso: exif.iso ? String(exif.iso) : '—',
    focal: focalMm(exif) ?? '—',
  }
}

/** "35mm · ƒ/2.8 · 1/250 · ISO 400", leaving out what is unknown (FR-1c.6). */
export function exposureLine(exif: ExifData): string {
  const mm = focalMm(exif)
  const time = shutter(exif)
  return [
    mm && `${mm}mm`,
    exif.f_stop ? `ƒ/${trimNumber(exif.f_stop)}` : null,
    time,
    exif.iso ? `ISO ${exif.iso}` : null,
  ]
    .filter(Boolean)
    .join(' · ')
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * "14 May 2026 · 18:42". Capture times are naive local wall-clock values (ADR D3): the digits are
 * read as written, never converted through a time zone.
 */
export function formatCapturedAt(capturedAt: string | null | undefined): string {
  const m = capturedAt?.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/)
  if (!m) return 'Unknown date'
  const [, year, month, day, hour, minute] = m
  const date = `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`
  return hour ? `${date} · ${hour}:${minute}` : date
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

export function shortHash(hash: string): string {
  return hash.length > 14 ? `${hash.slice(0, 8)}…${hash.slice(-6)}` : hash
}

/** The lens, when the extractor kept it in the raw tags. */
export function lensModel(exif: ExifData): string | null {
  const lens = exif.raw_tags?.LensModel
  return typeof lens === 'string' && lens.trim() ? lens.trim() : null
}

/** "ARW" from "photo.ARW". */
export function fileFormat(fileName: string): string {
  const dot = fileName.lastIndexOf('.')
  return dot > 0 ? fileName.slice(dot + 1).toUpperCase() : '—'
}
