import { describe, expect, it } from 'vitest'
import type { GeoCluster } from '../../types/metadata'
import { escapeHtml, formatCount, markerHtml } from './markers'

const cluster = (over: Partial<GeoCluster>): GeoCluster => ({
  latitude: 0,
  longitude: 0,
  count: 5,
  representative_hash: 'abc123',
  label: null,
  ...over,
})

describe('formatCount', () => {
  it.each([
    [7, '7'],
    [999, '999'],
    [1000, '1k'],
    [1234, '1.2k'],
    [9999, '10k'],
    [25_400, '25k'],
  ])('%i -> %s', (n, text) => expect(formatCount(n)).toBe(text))
})

describe('markerHtml', () => {
  it('shows the count for a group, with its place', () => {
    const html = markerHtml(cluster({ count: 12, label: 'Tokyo, Japan' }))
    expect(html).toContain('pmo-bubble')
    expect(html).toContain('>12<')
    expect(html).toContain('Tokyo, Japan')
  })

  it('shows the thumbnail of a single photo', () => {
    const html = markerHtml(cluster({ count: 1 }))
    expect(html).toContain('pmo-pin')
    expect(html).toContain('/api/photos/abc123/thumbnail')
    expect(html).not.toContain('pmo-bubble')
  })

  it('leaves out the label when there is no place', () => {
    expect(markerHtml(cluster({ label: null }))).not.toContain('pmo-marker-label')
  })

  it('escapes anything it interpolates', () => {
    const html = markerHtml(cluster({ label: '<img src=x onerror=alert(1)>' }))
    expect(html).not.toContain('<img src=x')
    expect(html).toContain('&lt;img src=x')
    expect(escapeHtml(`"'&`)).toBe('&quot;&#39;&amp;')
  })
})
