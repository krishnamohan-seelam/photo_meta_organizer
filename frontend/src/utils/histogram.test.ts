import { describe, expect, it } from 'vitest'
import { BINS, LruCache, binRgb, histogramScale } from './histogram'

function pixels(...rgba: [number, number, number, number][]) {
  return { data: Uint8ClampedArray.from(rgba.flat()), width: rgba.length, height: 1 }
}

describe('binRgb', () => {
  it('puts every pure red pixel into the top red bin', () => {
    const h = binRgb(pixels([255, 0, 0, 255], [255, 0, 0, 255], [255, 0, 0, 255]))
    expect(h.r[BINS - 1]).toBe(3)
    expect(h.r.slice(0, BINS - 1).every((n) => n === 0)).toBe(true)
    expect(h.g[0]).toBe(3)
    expect(h.b[0]).toBe(3)
  })

  it('bins each channel separately into 64 bins', () => {
    const h = binRgb(pixels([0, 128, 4, 255]))
    expect(h.r).toHaveLength(64)
    expect(h.r[0]).toBe(1)
    expect(h.g[32]).toBe(1)
    expect(h.b[1]).toBe(1)
  })

  it('skips fully transparent pixels', () => {
    const h = binRgb(pixels([255, 255, 255, 0]))
    expect(h.r.reduce((a, b) => a + b, 0)).toBe(0)
  })
})

describe('histogramScale', () => {
  it('normalises against the 4th-largest bin so clipping spikes do not flatten the chart', () => {
    const h = { r: new Array(BINS).fill(0), g: new Array(BINS).fill(0), b: new Array(BINS).fill(0) }
    h.r[63] = 1000 // a clipped highlight spike
    h.g[10] = 40
    h.b[20] = 30
    h.r[5] = 20
    h.g[6] = 10
    expect(histogramScale(h)).toBe(20)
  })

  it('is at least 1', () => {
    const empty = { r: new Array(BINS).fill(0), g: new Array(BINS).fill(0), b: new Array(BINS).fill(0) }
    expect(histogramScale(empty)).toBe(1)
  })
})

describe('LruCache', () => {
  it('evicts the least recently used entry', () => {
    const cache = new LruCache<string, number>(2)
    cache.set('a', 1)
    cache.set('b', 2)
    cache.get('a')
    cache.set('c', 3)
    expect(cache.get('b')).toBeUndefined()
    expect(cache.get('a')).toBe(1)
    expect(cache.get('c')).toBe(3)
  })
})
