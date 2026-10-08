import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { useUiStore } from '../../stores/useUiStore'
import { useGlobalHotkeys } from '../../hooks/useGlobalHotkeys'
import { NavRail } from './NavRail'

const initial = useUiStore.getState()

function HotkeyHarness() {
  useGlobalHotkeys()
  return (
    <>
      <NavRail />
      <input aria-label="typing here" />
    </>
  )
}

beforeEach(() => useUiStore.setState({ ...initial, activeView: 'studio', sidebarOpen: true, inspectorOpen: true, lightsOut: false }))

describe('NavRail (FR-1b.1–1b.3)', () => {
  it.each([
    ['Timeline', 'timeline'],
    ['Map', 'map'],
    ['Collections', 'kanban'],
    ['Insights', 'analytics'],
    ['Library', 'studio'],
  ] as const)('clicking %s switches the view', (label, view) => {
    render(<NavRail />)
    fireEvent.click(screen.getByRole('button', { name: label }))
    expect(useUiStore.getState().activeView).toBe(view)
    expect(screen.getByRole('button', { name: label }).getAttribute('aria-pressed')).toBe('true')
  })

  it('shows the panel toggles only in the Library view (AC-1b.2)', () => {
    const { rerender } = render(<NavRail />)
    expect(screen.getByRole('button', { name: 'Library panel' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Library panel' }))
    expect(useUiStore.getState().sidebarOpen).toBe(false)
    useUiStore.setState({ activeView: 'map' })
    rerender(<NavRail />)
    expect(screen.queryByRole('button', { name: 'Library panel' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Details panel' })).toBeNull()
  })
})

describe('global hotkeys (FR-1b.3, G-8)', () => {
  it('switch views and toggle panels from the page', () => {
    render(<HotkeyHarness />)
    fireEvent.keyDown(document.body, { key: 'i' })
    expect(useUiStore.getState().inspectorOpen).toBe(false)
    fireEvent.keyDown(document.body, { key: '\\' })
    expect(useUiStore.getState().sidebarOpen).toBe(false)
    fireEvent.keyDown(document.body, { key: 't' })
    expect(useUiStore.getState().activeView).toBe('timeline')
    fireEvent.keyDown(document.body, { key: 'L' })
    expect(useUiStore.getState().lightsOut).toBe(true)
  })

  it('are ignored while an input has focus', () => {
    render(<HotkeyHarness />)
    const input = screen.getByRole('textbox', { name: 'typing here' })
    input.focus()
    fireEvent.keyDown(input, { key: 'm' })
    fireEvent.keyDown(input, { key: 'l' })
    expect(useUiStore.getState().activeView).toBe('studio')
    expect(useUiStore.getState().lightsOut).toBe(false)
  })

  it('are ignored with a modifier or while a dialog is open', () => {
    render(<HotkeyHarness />)
    fireEvent.keyDown(document.body, { key: 'm', ctrlKey: true })
    expect(useUiStore.getState().activeView).toBe('studio')

    const dialog = document.createElement('div')
    dialog.setAttribute('aria-modal', 'true')
    document.body.appendChild(dialog)
    fireEvent.keyDown(document.body, { key: 'm' })
    dialog.remove()
    expect(useUiStore.getState().activeView).toBe('studio')
  })

  it('? opens the shortcut overlay', () => {
    render(<HotkeyHarness />)
    fireEvent.keyDown(document.body, { key: '?', shiftKey: true })
    expect(useUiStore.getState().shortcutsOpen).toBe(true)
  })
})
