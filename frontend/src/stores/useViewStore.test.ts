import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { startUrlSync, useViewStore } from './useViewStore'

let stop: () => void = () => {}

beforeEach(() => window.history.replaceState(null, '', '/'))
afterEach(() => stop())

const query = () => new URLSearchParams(window.location.search)

describe('startUrlSync (ADR-003 R8)', () => {
  it('reads the URL into the store on load and keeps parameters it does not own', () => {
    window.history.replaceState(null, '', '/?demo=1&view=map&q=rating%3A5&photo=abc')
    stop = startUrlSync()
    const s = useViewStore.getState()
    expect(s.activeView).toBe('map')
    expect(s.filterRating).toBe(5)
    expect(s.inspectedHash).toBe('abc')
    expect(query().get('demo')).toBe('1')
  })

  it('pushes a history entry for a filter change and replaces it for the inspected photo', () => {
    stop = startUrlSync()
    const before = window.history.length
    useViewStore.getState().setRatingFilter(4)
    expect(query().get('q')).toBe('rating:4')
    expect(window.history.length).toBe(before + 1)

    useViewStore.getState().setInspectedHash('h1')
    expect(query().get('photo')).toBe('h1')
    expect(window.history.length).toBe(before + 1)
  })

  it('reads the URL back on Back/Forward without writing a new entry', () => {
    stop = startUrlSync()
    useViewStore.getState().setActiveView('timeline')
    const length = window.history.length
    window.history.replaceState(null, '', '/?q=make%3ASony')
    window.dispatchEvent(new PopStateEvent('popstate'))
    const s = useViewStore.getState()
    expect(s.activeView).toBe('studio')
    expect(s.filterCameras).toEqual(['Sony'])
    expect(window.history.length).toBe(length)
  })

  it('a stale photo link does not change the filters', () => {
    window.history.replaceState(null, '', '/?q=rating%3A3&photo=gone')
    stop = startUrlSync()
    expect(useViewStore.getState().filterRating).toBe(3)
    expect(query().get('photo')).toBe('gone')
  })
})
