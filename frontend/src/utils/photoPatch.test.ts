import { describe, expect, it } from 'vitest'
import { makePhoto } from '../test/photos'
import { applyBatchAction, applyPatch } from './photoPatch'

describe('applyPatch mirrors the server (PMO-13)', () => {
  it('sets rating and flag', () => {
    const next = applyPatch(makePhoto(), { rating: 4, flagged: true })
    expect(next.rating).toBe(4)
    expect(next.flagged).toBe(true)
  })

  it('an explicit null clears the rating but leaves the flag alone', () => {
    const next = applyPatch(makePhoto({ rating: 3, flagged: true }), { rating: null, flagged: null })
    expect(next.rating).toBeNull()
    expect(next.flagged).toBe(true)
  })

  it('applies labels, then add_tags, then remove_tags, without duplicates', () => {
    const photo = makePhoto({ labels: ['old'] })
    const next = applyPatch(photo, { labels: ['a', 'b', 'a'], add_tags: ['c', 'a'], remove_tags: ['b'] })
    expect(next.labels).toEqual(['a', 'c'])
  })

  it('does not touch the input record', () => {
    const photo = makePhoto({ labels: ['x'] })
    applyPatch(photo, { add_tags: ['y'], rating: 5 })
    expect(photo.labels).toEqual(['x'])
    expect(photo.rating).toBeNull()
  })
})

describe('applyBatchAction', () => {
  it('trims tags and coerces values like the server', () => {
    const photo = makePhoto({ labels: ['keep'] })
    expect(applyBatchAction(photo, 'add_tag', '  new ').labels).toEqual(['keep', 'new'])
    expect(applyBatchAction(photo, 'remove_tag', 'keep').labels).toEqual([])
    expect(applyBatchAction(photo, 'set_rating', 2).rating).toBe(2)
    expect(applyBatchAction(photo, 'set_flag', 1).flagged).toBe(true)
  })
})
