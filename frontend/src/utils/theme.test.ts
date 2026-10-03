import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadTheme, saveTheme } from './theme'

afterEach(() => localStorage.clear())

describe('theme storage (PMO-36)', () => {
  it('round-trips a saved theme', () => {
    saveTheme('light')
    expect(loadTheme()).toBe('light')
  })

  it('ignores a value it did not write', () => {
    localStorage.setItem('pmo_theme', 'purple')
    expect(loadTheme()).toBeNull()
  })

  it('survives storage that throws (private mode, disabled storage)', () => {
    const denied = () => {
      throw new DOMException('denied', 'SecurityError')
    }
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(denied)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(denied)
    expect(loadTheme()).toBeNull()
    expect(() => saveTheme('dark')).not.toThrow()
  })
})
