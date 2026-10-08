export const BINS = 64

export interface RgbHistogram {
  r: number[]
  g: number[]
  b: number[]
}

/** The part of `ImageData` binning needs, so tests can pass a plain object. */
export interface PixelData {
  data: Uint8ClampedArray
  width: number
  height: number
}

/** Count R, G and B values into 64 bins each (FR-1e.2). Fully transparent pixels are skipped. */
export function binRgb(image: PixelData): RgbHistogram {
  const r = new Array<number>(BINS).fill(0)
  const g = new Array<number>(BINS).fill(0)
  const b = new Array<number>(BINS).fill(0)
  const { data } = image
  for (let i = 0; i + 3 < data.length; i += 4) {
    if (data[i + 3] === 0) continue
    r[data[i] >> 2]++
    g[data[i + 1] >> 2]++
    b[data[i + 2] >> 2]++
  }
  return { r, g, b }
}

/** The value drawn at full height: the 4th-largest bin of all channels, so a clipped spike does not flatten the rest. */
export function histogramScale(h: RgbHistogram): number {
  const sorted = [...h.r, ...h.g, ...h.b].sort((a, b) => b - a)
  return Math.max(1, sorted[3] ?? 0)
}

/** A small least-recently-used map. */
export class LruCache<K, V> {
  private readonly map = new Map<K, V>()
  private readonly limit: number

  constructor(limit: number) {
    this.limit = limit
  }

  get(key: K): V | undefined {
    const value = this.map.get(key)
    if (value !== undefined) {
      this.map.delete(key)
      this.map.set(key, value)
    }
    return value
  }

  set(key: K, value: V): void {
    this.map.delete(key)
    this.map.set(key, value)
    if (this.map.size > this.limit) this.map.delete(this.map.keys().next().value as K)
  }
}
