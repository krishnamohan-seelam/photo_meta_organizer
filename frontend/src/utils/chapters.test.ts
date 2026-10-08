import { describe, expect, it } from 'vitest'
import type { PhotoMetadata } from '../types/metadata'
import { makePhoto } from '../test/photos'
import { chapterHero, chapterLabel, chapterSubtitle, groupIntoChapters, tileSpan } from './chapters'

let n = 0
function shot(capturedAt: string | null, overrides: Partial<PhotoMetadata> = {}): PhotoMetadata {
  const hash = (n++).toString(16).padStart(64, '0')
  const photo = makePhoto({ file_hash: hash, ...overrides })
  photo.exif = { ...photo.exif, captured_at: capturedAt, ...(overrides.exif ?? {}) }
  return photo
}
const sizes = (chapters: { photos: PhotoMetadata[] }[]) => chapters.map((c) => c.photos.length)

describe('groupIntoChapters (FR-3.1, AC-3.1)', () => {
  it('splits where the gap exceeds 36 hours by default', () => {
    const photos = [
      shot('2026-05-14T08:00:00'),
      shot('2026-05-15T19:00:00'), // 35 h later: same chapter
      shot('2026-05-17T08:00:01'), // 37 h later: new chapter
    ]
    expect(sizes(groupIntoChapters(photos))).toEqual([2, 1])
  })

  it('honours a custom gap', () => {
    const photos = [shot('2026-05-14T08:00:00'), shot('2026-05-14T22:00:00'), shot('2026-05-15T23:00:00')]
    expect(sizes(groupIntoChapters(photos, { gapHours: 12 }))).toEqual([1, 1, 1])
    expect(sizes(groupIntoChapters(photos, { gapHours: 168 }))).toEqual([3])
  })

  it('splits when the calendar month changes, even within the gap', () => {
    const photos = [shot('2026-01-31T22:00:00'), shot('2026-02-01T06:00:00')]
    expect(sizes(groupIntoChapters(photos))).toEqual([1, 1])
  })

  it('puts undated photos in one last chapter', () => {
    const photos = [shot(null), shot('2026-05-14T08:00:00'), shot(null), shot('2026-05-14T09:00:00')]
    const chapters = groupIntoChapters(photos)
    expect(sizes(chapters)).toEqual([2, 2])
    expect(chapters[1].undated).toBe(true)
    expect(chapters[1].photos.every((p) => p.exif.captured_at === null)).toBe(true)
  })

  it('works in descending order too', () => {
    const photos = [shot('2026-05-21T08:00:00'), shot('2026-05-20T08:00:00'), shot('2026-05-14T08:00:00')]
    const chapters = groupIntoChapters(photos)
    expect(sizes(chapters)).toEqual([2, 1])
    expect(chapters[0]).toMatchObject({ start: '2026-05-20T08:00:00', end: '2026-05-21T08:00:00' })
  })

  it('handles one photo and no photos', () => {
    expect(sizes(groupIntoChapters([shot('2026-05-14T08:00:00')]))).toEqual([1])
    expect(groupIntoChapters([])).toEqual([])
  })

  it('gives each chapter a stable id from its first photo', () => {
    const photos = [shot('2026-05-14T08:00:00'), shot('2026-06-14T08:00:00')]
    const [a, b] = groupIntoChapters(photos)
    expect(a.id).toBe(`chapter-${photos[0].file_hash}`)
    expect(b.id).not.toBe(a.id)
  })
})

describe('chapterLabel (FR-3.2, AC-3.2)', () => {
  it.each([
    ['2026-05-16T08:00:00', '2026-05-16T21:00:00', '16 May 2026'],
    ['2026-05-14T08:00:00', '2026-05-21T21:00:00', '14–21 May 2026'],
    ['2026-01-28T08:00:00', '2026-02-02T21:00:00', '28 Jan – 2 Feb 2026'],
    ['2025-12-28T08:00:00', '2026-01-03T21:00:00', '28 Dec 2025 – 3 Jan 2026'],
  ])('%s .. %s → %s', (start, end, label) => {
    expect(chapterLabel(start, end)).toBe(label)
  })
})

describe('chapterHero (FR-3.4, AC-3.3)', () => {
  it('has no hero below four photos', () => {
    expect(chapterHero([shot('2026-05-14T08:00:00'), shot('2026-05-14T09:00:00'), shot('2026-05-14T10:00:00')])).toBeNull()
  })

  it('prefers a pick, then the highest rating, then the earliest', () => {
    const rated = shot('2026-05-14T09:00:00', { rating: 5 })
    const picked = shot('2026-05-14T12:00:00', { flagged: true, rating: 2 })
    const photos = [shot('2026-05-14T08:00:00'), rated, picked, shot('2026-05-14T10:00:00')]
    expect(chapterHero(photos)).toBe(picked.file_hash)
    expect(chapterHero(photos.filter((p) => p !== picked).concat(shot('2026-05-14T13:00:00')))).toBe(rated.file_hash)
  })

  it('breaks full ties by the earliest capture, then by hash, whatever the order', () => {
    const early = shot('2026-05-14T08:00:00', { rating: 3 })
    const late = shot('2026-05-14T18:00:00', { rating: 3 })
    const others = [shot('2026-05-14T09:00:00', { rating: 1 }), shot('2026-05-14T10:00:00', { rating: 1 })]
    expect(chapterHero([late, ...others, early])).toBe(early.file_hash)
    expect(chapterHero([early, ...others, late])).toBe(early.file_hash)
    const twinA = shot('2026-05-14T08:00:00')
    const twinB = shot('2026-05-14T08:00:00')
    const fillers = [shot('2026-05-14T11:00:00'), shot('2026-05-14T12:00:00')]
    expect(chapterHero([twinB, twinA, ...fillers])).toBe(twinA.file_hash < twinB.file_hash ? twinA.file_hash : twinB.file_hash)
  })
})

describe('chapterSubtitle', () => {
  it('counts photos, names up to three models and counts geotags', () => {
    const at = (model: string, geo = false) =>
      shot('2026-05-14T08:00:00', {
        exif: { ...makePhoto().exif, captured_at: '2026-05-14T08:00:00', camera_model: model, location: geo ? { latitude: 1, longitude: 2, altitude: null, datum: 'WGS84' } : null },
      })
    const photos = [at('A7 IV', true), at('A7 IV'), at('X-T5', true), at('Z8'), at('GR III')]
    expect(chapterSubtitle(photos)).toBe('5 photos · A7 IV, X-T5, Z8 +1 · 2 geotagged')
  })
})

describe('tileSpan', () => {
  it('tall portraits, wide panoramas, square-ish stays single', () => {
    expect(tileSpan(0.67)).toBe('tall')
    expect(tileSpan(2)).toBe('wide')
    expect(tileSpan(1.5)).toBe('one')
  })
})
