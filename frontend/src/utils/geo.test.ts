import { describe, expect, it } from 'vitest'
import type { PhotoMetadata } from '../types/metadata'
import {
  boxContains,
  cellDegreesForZoom,
  clusterPhotos,
  clusterTitle,
  normalizeBounds,
  padBounds,
  wrapLongitude,
  zoomIntoCluster,
} from './geo'

function photo(hash: string, lat: number | null, lon = 0, captured: string | null = null): PhotoMetadata {
  return {
    file_hash: hash,
    exif: {
      captured_at: captured,
      location: lat === null ? null : { latitude: lat, longitude: lon, datum: 'WGS84', altitude: null },
    },
  } as unknown as PhotoMetadata
}

describe('cellDegreesForZoom', () => {
  it('matches the backend: 90 degrees at zoom 0 and halving with each level', () => {
    expect(cellDegreesForZoom(0)).toBe(90)
    expect(cellDegreesForZoom(4)).toBeCloseTo(cellDegreesForZoom(3) / 2)
  })
  it('clamps and rounds the zoom', () => {
    expect(cellDegreesForZoom(-3)).toBe(cellDegreesForZoom(0))
    expect(cellDegreesForZoom(99)).toBe(cellDegreesForZoom(20))
    expect(cellDegreesForZoom(5.4)).toBe(cellDegreesForZoom(5))
  })
})

describe('longitude and bounds', () => {
  it('wraps a longitude panned past the date line', () => {
    expect(wrapLongitude(190)).toBe(-170)
    expect(wrapLongitude(-190)).toBe(170)
    expect(wrapLongitude(180)).toBe(180)
    expect(wrapLongitude(35)).toBe(35)
  })
  it('turns a view wider than the world into the whole world', () => {
    expect(normalizeBounds({ south: -95, west: -300, north: 95, east: 300 })).toEqual({
      south: -90,
      west: -180,
      north: 90,
      east: 180,
    })
  })
  it('keeps west > east when the view crosses the date line', () => {
    const box = normalizeBounds({ south: 0, west: 170, north: 10, east: 190 })
    expect(box).toEqual({ south: 0, west: 170, north: 10, east: -170 })
    expect(boxContains(box, 5, 175)).toBe(true)
    expect(boxContains(box, 5, -175)).toBe(true)
    expect(boxContains(box, 5, 0)).toBe(false)
  })
  it('pads a viewport that crosses the date line by its real width', () => {
    // 170E to 170W is 20 degrees wide; a quarter of that is 5 degrees each side.
    expect(padBounds({ south: 0, west: 170, north: 10, east: -170 }, 0.25)).toEqual({
      south: -2.5,
      west: 165,
      north: 12.5,
      east: -165,
    })
  })
  it('pads a Japan-sized viewport that Leaflet reported past 180 degrees', () => {
    const view = normalizeBounds({ south: 10, west: 90, north: 50, east: 186 })
    const padded = padBounds(view, 0.25)
    expect(boxContains(padded, 35.4, 138)).toBe(true)
    expect(padded.west).toBeLessThan(view.west)
  })
  it('pads a viewport by a fraction of its size', () => {
    expect(padBounds({ south: 0, west: 0, north: 10, east: 20 }, 0.5)).toEqual({
      south: -5,
      west: -10,
      north: 15,
      east: 30,
    })
  })
})

describe('zoomIntoCluster', () => {
  it('goes two levels deeper, up to the map maximum', () => {
    expect(zoomIntoCluster(3)).toBe(5)
    expect(zoomIntoCluster(17)).toBe(18)
    expect(zoomIntoCluster(18)).toBe(18)
  })
})

describe('clusterTitle', () => {
  it('uses singular and plural and the place when known', () => {
    expect(clusterTitle({ count: 1, label: null })).toBe('1 photo')
    expect(clusterTitle({ count: 7, label: 'Kyoto, Japan' })).toBe('Kyoto, Japan: 7 photos')
  })
})

describe('clusterPhotos (demo mode)', () => {
  it('groups nearby photos, skips ones without GPS and picks the newest as representative', () => {
    const clusters = clusterPhotos(
      [
        photo('old', 35.68, 139.65, '2020-01-01T00:00:00'),
        photo('new', 35.682, 139.655, '2026-01-01T00:00:00'),
        photo('far', 51.5, -0.12),
        photo('nogps', null),
      ],
      10
    )
    expect(clusters.map((c) => [c.count, c.representative_hash])).toEqual([
      [2, 'new'],
      [1, 'far'],
    ])
    expect(clusters[0].latitude).toBeCloseTo(35.681)
  })
  it('limits to the box', () => {
    const photos = [photo('in', 10, 10), photo('out', 60, 10)]
    const result = clusterPhotos(photos, 5, { south: 0, west: 0, north: 20, east: 20 })
    expect(result.map((c) => c.representative_hash)).toEqual(['in'])
  })
})
