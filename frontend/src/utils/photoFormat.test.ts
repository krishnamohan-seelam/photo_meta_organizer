import { describe, expect, it } from 'vitest'
import { makePhoto } from '../test/photos'
import {
  displayTitle,
  exposureLine,
  exposureParts,
  formatBytes,
  formatCapturedAt,
  lensModel,
  photoAspectRatio,
  shortHash,
} from './photoFormat'

describe('displayTitle (Appendix C)', () => {
  it.each([
    ['DSC04928_Tokyo_Tower_Sunset.ARW', 'Tokyo Tower Sunset'],
    ['IMG_8392.CR3', 'IMG_8392'],
    ['PXL_20260514_184210.jpg', 'PXL_20260514_184210'],
    ['DSCF1234-Harbour-at-dawn.RAF', 'Harbour at dawn'],
    ['_MG_0042_Wedding.jpg', 'Wedding'],
    ['_DSC9102_Fuji_Sunrise.NEF', 'Fuji Sunrise'],
    ['holiday__beach  day.jpeg', 'holiday beach day'],
    ['sunset.jpg', 'sunset'],
    ['no-extension', 'no extension'],
    ['dsc00042_lowercase_counter.jpg', 'lowercase counter'],
  ])('%s → %s', (name, title) => {
    expect(displayTitle(name)).toBe(title)
  })
})

describe('photoAspectRatio', () => {
  it('is width / height', () => {
    expect(photoAspectRatio(makePhoto({ dimensions: { width: 6000, height: 4000 } }))).toBe(1.5)
  })

  it('falls back to 3:2 when a dimension is 0', () => {
    expect(photoAspectRatio(makePhoto({ dimensions: { width: 0, height: 4000 } }))).toBe(1.5)
    expect(photoAspectRatio(makePhoto({ dimensions: { width: 6000, height: 0 } }))).toBe(1.5)
  })

  it.each([5, 6, 7, 8])('swaps width and height for EXIF orientation %i (thumbnails are upright)', (orientation) => {
    const photo = makePhoto({ dimensions: { width: 6000, height: 4000 } })
    photo.exif = { ...photo.exif, orientation }
    expect(photoAspectRatio(photo)).toBeCloseTo(4000 / 6000)
  })

  it.each([1, 2, 3, 4, null])('keeps width and height for orientation %s', (orientation) => {
    const photo = makePhoto({ dimensions: { width: 6000, height: 4000 } })
    photo.exif = { ...photo.exif, orientation }
    expect(photoAspectRatio(photo)).toBe(1.5)
  })

  it('clamps extreme panoramas', () => {
    expect(photoAspectRatio(makePhoto({ dimensions: { width: 20000, height: 1000 } }))).toBe(3.5)
  })
})

describe('exposure formatting', () => {
  it('builds the scrim line, omitting missing values', () => {
    const photo = makePhoto()
    expect(exposureLine(photo.exif)).toBe('35mm · ƒ/2.8 · 1/250 · ISO 400')
    expect(exposureLine({ ...photo.exif, focal_length: null, iso: null })).toBe('ƒ/2.8 · 1/250')
  })

  it('normalises the backend spellings ("35.0 mm", "1/250s")', () => {
    const exif = { ...makePhoto().exif, focal_length: '35.0 mm', exposure_time: '1/250s' }
    expect(exposureParts(exif)).toEqual({ aperture: 'ƒ/2.8', shutter: '1/250', iso: '400', focal: '35' })
  })

  it('shows a dash for each missing strip value', () => {
    const exif = { ...makePhoto().exif, f_stop: null, exposure_time: null, iso: null, focal_length: null }
    expect(exposureParts(exif)).toEqual({ aperture: '—', shutter: '—', iso: '—', focal: '—' })
  })
})

describe('details formatting', () => {
  it('formats the capture time as naive local time', () => {
    expect(formatCapturedAt('2026-05-14T18:42:10')).toBe('14 May 2026 · 18:42')
    // A stray Z is dropped, never converted (ADR D3).
    expect(formatCapturedAt('2026-05-14T18:42:10Z')).toBe('14 May 2026 · 18:42')
    expect(formatCapturedAt(null)).toBe('Unknown date')
  })

  it('formats sizes', () => {
    expect(formatBytes(25_345_678)).toBe('24.2 MB')
    expect(formatBytes(900)).toBe('900 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
  })

  it('shortens hashes', () => {
    expect(shortHash('83c7299b0000000000000000000000000000000000000000000000000ab2386a')).toBe('83c7299b…b2386a')
  })

  it('reads the lens from raw tags when present', () => {
    expect(lensModel({ ...makePhoto().exif, raw_tags: { LensModel: 'FE 35mm F1.4 GM' } })).toBe('FE 35mm F1.4 GM')
    expect(lensModel(makePhoto().exif)).toBeNull()
  })
})
