import { describe, expect, it } from 'vitest'
import { FALLBACK_RATIO, MAX_RATIO, justifiedRows, rowWidth } from './justifiedLayout'

const items = (...ratios: number[]) => ratios.map((ratio) => ({ ratio }))

describe('justifiedRows', () => {
  it('fills every row but the last to the container width (±1 px)', () => {
    const list = items(1.5, 0.67, 1.5, 1.33, 1, 1.78, 0.75, 1.5, 1.5, 2, 1.2, 0.8, 1.5)
    const rows = justifiedRows(list, 1000, 200, 4)
    expect(rows.length).toBeGreaterThan(2)
    for (const row of rows.slice(0, -1)) {
      expect(Math.abs(rowWidth(list, row, 4) - 1000)).toBeLessThanOrEqual(1)
    }
  })

  it('covers every item once, in order', () => {
    const list = items(1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5)
    const rows = justifiedRows(list, 800, 200)
    expect(rows[0].start).toBe(0)
    rows.slice(1).forEach((row, i) => expect(row.start).toBe(rows[i].end))
    expect(rows[rows.length - 1].end).toBe(list.length)
  })

  it('does not stretch the last row', () => {
    const rows = justifiedRows(items(1.5, 1.5, 1.5, 1), 2000, 200, 4)
    const last = rows[rows.length - 1]
    expect(last.height).toBe(200)
    expect(rowWidth(items(1.5, 1.5, 1.5, 1), last, 4)).toBeLessThan(2000)
  })

  it('shrinks a last row that would overflow at the target height', () => {
    // One item wider than the container at 200 px: it is scaled down to fit.
    const rows = justifiedRows(items(3), 400, 200, 4)
    expect(rows).toEqual([{ start: 0, end: 1, height: 400 / 3 }])
  })

  it('treats a zero, missing or invalid ratio as 3:2', () => {
    const a = justifiedRows(items(0, NaN, -1), 10_000, 100, 0)
    const b = justifiedRows(items(FALLBACK_RATIO, FALLBACK_RATIO, FALLBACK_RATIO), 10_000, 100, 0)
    expect(a).toEqual(b)
  })

  it('clamps a very wide panorama so it cannot take a whole row alone', () => {
    const list = items(12, 1.5)
    const rows = justifiedRows(list, 2000, 200, 0)
    // Clamped to 3.5 the panorama is 700 px wide at 200 px: the next photo still fits in its row.
    expect(rows).toHaveLength(1)
    expect(rows[0].end).toBe(2)
    expect(rowWidth(list, rows[0], 0)).toBeCloseTo(200 * (MAX_RATIO + 1.5))
  })

  it('returns no rows before the container has a width', () => {
    expect(justifiedRows(items(1.5, 1.5), 0, 200)).toEqual([])
  })

  it('returns no rows for no items', () => {
    expect(justifiedRows([], 1000, 200)).toEqual([])
  })
})
