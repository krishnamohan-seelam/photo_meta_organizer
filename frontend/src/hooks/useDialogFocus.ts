import { useEffect } from 'react'
import type { RefObject } from 'react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Modal focus handling: move focus into the dialog when it opens (the `initial` element, or
 * the first focusable one), keep Tab / Shift+Tab inside it, and give focus back to whatever
 * had it before when the dialog closes (unmounts).
 */
export function useDialogFocus(
  containerRef: RefObject<HTMLElement | null>,
  initialRef?: RefObject<HTMLElement | null>
) {
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null

    const focusables = () =>
      [...container.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null)
    ;(initialRef?.current ?? focusables()[0] ?? container).focus()

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const items = focusables()
      if (items.length === 0) {
        e.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || !container.contains(active))) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (active === last || !container.contains(active))) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      if (previous?.isConnected) previous.focus()
    }
    // Refs are stable, so this runs once per mount; dialogs unmount when they close.
  }, [containerRef, initialRef])
}
