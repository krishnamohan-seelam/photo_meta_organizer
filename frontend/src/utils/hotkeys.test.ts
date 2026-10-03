import { describe, expect, it } from 'vitest'
import { shouldIgnoreHotkey } from './hotkeys'
import { filmstripWindow } from './filmstrip'

/** Dispatch a real keydown on `target` (attached to the page) and return the event the listener saw. */
function keyOn(target: HTMLElement, init: KeyboardEventInit = {}): KeyboardEvent {
  document.body.appendChild(target)
  const seen: KeyboardEvent[] = []
  target.addEventListener('keydown', (e) => seen.push(e), { once: true })
  target.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', bubbles: true, ...init }))
  target.remove()
  return seen[0]
}

describe('shouldIgnoreHotkey (PMO-29)', () => {
  it('fires for a plain key on the page', () => {
    expect(shouldIgnoreHotkey(keyOn(document.createElement('div')))).toBe(false)
  })

  it.each(['ctrlKey', 'metaKey', 'altKey'])('ignores %s combinations', (modifier) => {
    expect(shouldIgnoreHotkey(keyOn(document.createElement('div'), { [modifier]: true }))).toBe(true)
  })

  it.each(['input', 'textarea', 'select'])('ignores typing in a %s', (tag) => {
    expect(shouldIgnoreHotkey(keyOn(document.createElement(tag)))).toBe(true)
  })
})

describe('filmstripWindow', () => {
  const cases: [number, number, number, [number, number]][] = [
    [0, 5, 13, [0, 5]],
    [0, 100, 13, [0, 13]],
    [50, 100, 13, [44, 57]],
    [99, 100, 13, [87, 100]],
  ]
  it.each(cases)('index %i of %i, size %i', (index, total, size, expected) => {
    expect(filmstripWindow(index, total, size)).toEqual(expected)
  })
})
