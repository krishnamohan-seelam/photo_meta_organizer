import type { ViewMode } from '../stores/useUiStore'

/** Single-key view shortcuts (FR-1b.3). */
export const VIEW_KEYS: Record<string, ViewMode> = {
  g: 'studio',
  t: 'timeline',
  m: 'map',
  c: 'kanban',
  a: 'analytics',
}

export const VIEW_LABELS: Record<ViewMode, { label: string; key: string }> = {
  studio: { label: 'Library', key: 'G' },
  timeline: { label: 'Timeline', key: 'T' },
  map: { label: 'Map', key: 'M' },
  kanban: { label: 'Collections', key: 'C' },
  analytics: { label: 'Insights', key: 'A' },
}

/** The keyboard map shown by the `?` overlay (Appendix B). */
export const SHORTCUTS: { keys: string[]; action: string; scope: string }[] = [
  { keys: ['Ctrl', 'K'], action: 'Command palette', scope: 'Everywhere' },
  { keys: ['/'], action: 'Focus search', scope: 'Everywhere' },
  { keys: ['?'], action: 'This list', scope: 'Everywhere' },
  { keys: ['G', 'T', 'M', 'C', 'A'], action: 'Library · Timeline · Map · Collections · Insights', scope: 'Everywhere' },
  { keys: ['\\'], action: 'Library panel', scope: 'Library' },
  { keys: ['I'], action: 'Details panel', scope: 'Library' },
  { keys: ['L'], action: 'Lights Out', scope: 'Everywhere' },
  { keys: ['V'], action: 'Grid ↔ Table', scope: 'Library' },
  { keys: ['←', '→'], action: 'Previous / next photo (grid, viewer)', scope: 'Library, viewer' },
  { keys: ['J', 'K', '↓', '↑'], action: 'Next / previous row; Shift extends the selection', scope: 'Library table' },
  { keys: ['1', '–', '5'], action: 'Set rating', scope: 'Library, viewer' },
  { keys: ['0'], action: 'Clear rating', scope: 'Library, viewer' },
  { keys: ['P'], action: 'Toggle Pick', scope: 'Library, viewer' },
  { keys: ['X'], action: 'Select / deselect photo (also Space in the table)', scope: 'Library' },
  { keys: ['Enter'], action: 'Open the viewer (also Space in the grid)', scope: 'Library' },
  { keys: ['Esc'], action: 'Close dialog, then clear the selection', scope: 'Everywhere' },
]

/** True while a modal dialog is open: global single-key shortcuts stay quiet then (G-8). */
export function dialogOpen(): boolean {
  return document.querySelector('[aria-modal="true"]') !== null
}
