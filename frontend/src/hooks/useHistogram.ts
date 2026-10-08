import { useEffect, useState } from 'react'
import { LruCache, binRgb, type RgbHistogram } from '../utils/histogram'

/** Pixels sampled per row: enough for a 64-bin histogram, cheap to read back. */
const SAMPLE_WIDTH = 160
const cache = new LruCache<string, RgbHistogram | null>(200)

function compute(img: HTMLImageElement): RgbHistogram | null {
  const scale = Math.min(1, SAMPLE_WIDTH / (img.naturalWidth || SAMPLE_WIDTH))
  const w = Math.max(1, Math.round(img.naturalWidth * scale))
  const h = Math.max(1, Math.round(img.naturalHeight * scale))
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(img, 0, 0, w, h)
  // Throws for a tainted canvas: the caller treats that as "no histogram".
  return binRgb(ctx.getImageData(0, 0, w, h))
}

/**
 * RGB histogram of a photo's thumbnail (FR-1e.2), computed after the image loads and cached per hash.
 * `null` means the pixels cannot be read (decode error, tainted canvas, demo placeholder): the
 * inspector then hides the section rather than drawing a fake one (FR-1e.3).
 */
export function useHistogram(hash: string | undefined, src: string | undefined): RgbHistogram | null | 'loading' {
  const [result, setResult] = useState<{ hash: string; value: RgbHistogram | null } | null>(null)

  useEffect(() => {
    if (!hash || !src) return
    if (cache.get(hash) !== undefined) return
    let cancelled = false
    const img = new Image()
    img.decoding = 'async'
    const done = (value: RgbHistogram | null) => {
      cache.set(hash, value)
      if (!cancelled) setResult({ hash, value })
    }
    img.onload = () => {
      // Off the critical path: render first, read pixels when the browser is idle-ish.
      setTimeout(() => {
        try {
          done(compute(img))
        } catch {
          done(null)
        }
      }, 0)
    }
    img.onerror = () => done(null)
    img.src = src
    return () => {
      cancelled = true
    }
  }, [hash, src])

  if (!hash || !src) return null
  const cached = cache.get(hash)
  if (cached !== undefined) return cached
  return result?.hash === hash ? result.value : 'loading'
}
