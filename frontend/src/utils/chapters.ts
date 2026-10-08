import type { PhotoMetadata } from '../types/metadata'

/** Default gap that starts a new chapter (FR-3.1); the Timeline lets the viewer change it (FR-3.10). */
export const DEFAULT_GAP_HOURS = 36

export const GAP_PRESETS: { hours: number; label: string }[] = [
  { hours: 12, label: '12 h' },
  { hours: 24, label: '24 h' },
  { hours: 36, label: '36 h' },
  { hours: 72, label: '3 days' },
  { hours: 168, label: '7 days' },
]

export interface Chapter {
  /** Stable while the chapter's first photo stays first. */
  id: string
  photos: PhotoMetadata[]
  /** Earliest and latest capture time (naive local), or null for the undated chapter. */
  start: string | null
  end: string | null
  undated: boolean
}

/** Milliseconds of a naive local timestamp, read as written (ADR D3): only differences are used. */
function naiveMs(value: string): number {
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/)
  if (!m) return NaN
  const [, y, mo, d, h = '0', mi = '0', s = '0'] = m
  return Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s))
}

function finish(photos: PhotoMetadata[]): Chapter {
  const times = photos.map((p) => p.exif.captured_at as string).sort()
  return { id: `chapter-${photos[0].file_hash}`, photos, start: times[0], end: times[times.length - 1], undated: false }
}

/**
 * Trip-like chapters (FR-3.1): walk the photos in their current capture-date order (either
 * direction) and start a new chapter when the gap to the previous photo exceeds `gapHours` or
 * the calendar month changes. Undated photos form one last chapter.
 */
export function groupIntoChapters(photos: PhotoMetadata[], { gapHours = DEFAULT_GAP_HOURS }: { gapHours?: number } = {}): Chapter[] {
  const chapters: Chapter[] = []
  const undated: PhotoMetadata[] = []
  let current: PhotoMetadata[] = []
  let previous: string | null = null
  const gapMs = gapHours * 3_600_000

  for (const photo of photos) {
    const at = photo.exif.captured_at
    if (!at) {
      undated.push(photo)
      continue
    }
    if (previous !== null) {
      const sameMonth = at.slice(0, 7) === previous.slice(0, 7)
      if (!sameMonth || Math.abs(naiveMs(at) - naiveMs(previous)) > gapMs) {
        chapters.push(finish(current))
        current = []
      }
    }
    current.push(photo)
    previous = at
  }
  if (current.length > 0) chapters.push(finish(current))
  if (undated.length > 0) {
    chapters.push({ id: 'chapter-undated', photos: undated, start: null, end: null, undated: true })
  }
  return chapters
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function parts(value: string) {
  return { year: value.slice(0, 4), month: MONTHS[Number(value.slice(5, 7)) - 1], day: String(Number(value.slice(8, 10))) }
}

/** "16 May 2026", "14–21 May 2026", "28 Jan – 2 Feb 2026", "28 Dec 2025 – 3 Jan 2026" (FR-3.2). */
export function chapterLabel(start: string, end: string): string {
  const a = parts(start)
  const b = parts(end)
  if (start.slice(0, 10) === end.slice(0, 10)) return `${a.day} ${a.month} ${a.year}`
  if (a.year === b.year && a.month === b.month) return `${a.day}–${b.day} ${a.month} ${a.year}`
  if (a.year === b.year) return `${a.day} ${a.month} – ${b.day} ${b.month} ${b.year}`
  return `${a.day} ${a.month} ${a.year} – ${b.day} ${b.month} ${b.year}`
}

/** "N photos · models (max 3, then +k) · M geotagged" (FR-3.2). */
export function chapterSubtitle(photos: PhotoMetadata[]): string {
  const models: string[] = []
  for (const p of photos) {
    const model = p.exif.camera_model
    if (model && !models.includes(model)) models.push(model)
  }
  const geotagged = photos.filter((p) => p.exif.location).length
  const shown = models.slice(0, 3).join(', ') + (models.length > 3 ? ` +${models.length - 3}` : '')
  return [`${photos.length} photo${photos.length === 1 ? '' : 's'}`, shown, geotagged > 0 ? `${geotagged} geotagged` : null]
    .filter(Boolean)
    .join(' · ')
}

/**
 * The photo shown 2×2 in a chapter of four or more (FR-3.4): a pick first, then the highest rating,
 * then the earliest capture, then the lowest hash, so the choice never depends on load order.
 */
export function chapterHero(photos: PhotoMetadata[]): string | null {
  if (photos.length < 4) return null
  let best = photos[0]
  const better = (a: PhotoMetadata, b: PhotoMetadata) => {
    if (a.flagged !== b.flagged) return a.flagged
    if ((a.rating ?? 0) !== (b.rating ?? 0)) return (a.rating ?? 0) > (b.rating ?? 0)
    const ta = a.exif.captured_at ?? '￿'
    const tb = b.exif.captured_at ?? '￿'
    if (ta !== tb) return ta < tb
    return a.file_hash < b.file_hash
  }
  for (const p of photos.slice(1)) if (better(p, best)) best = p
  return best.file_hash
}

export type TileSpan = 'one' | 'tall' | 'wide' | 'hero'

/** Mosaic span from the aspect ratio (FR-3.4): portraits take two rows, panoramas two columns. */
export function tileSpan(ratio: number): Exclude<TileSpan, 'hero'> {
  if (ratio < 0.85) return 'tall'
  if (ratio > 1.6) return 'wide'
  return 'one'
}
