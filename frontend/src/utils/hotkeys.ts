/**
 * True when a single-key global hotkey (L, P, 1-5, arrows) must NOT fire: the user is
 * typing somewhere, or holds a modifier (Ctrl+1 switches browser tabs, Alt+L is not L).
 */
export function shouldIgnoreHotkey(e: KeyboardEvent): boolean {
  if (e.defaultPrevented || e.isComposing) return true
  if (e.ctrlKey || e.metaKey || e.altKey) return true
  return isEditable(e.target)
}

export function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}
