import React from 'react'
import { useShallow } from 'zustand/react/shallow'
import {
  Aperture,
  BarChart3,
  CalendarDays,
  Columns3,
  EyeOff,
  Keyboard,
  LayoutGrid,
  MapPin,
  Moon,
  PanelLeft,
  PanelRight,
  Sun,
} from 'lucide-react'
import { useUiStore, type ViewMode } from '../../stores/useUiStore'
import { VIEW_LABELS } from '../../utils/shortcuts'

const VIEW_ICONS: Record<ViewMode, React.ReactNode> = {
  studio: <LayoutGrid size={18} />,
  timeline: <CalendarDays size={18} />,
  map: <MapPin size={18} />,
  kanban: <Columns3 size={18} />,
  analytics: <BarChart3 size={18} />,
}

const VIEWS: ViewMode[] = ['studio', 'timeline', 'map', 'kanban', 'analytics']

interface RailButtonProps {
  label: string
  shortcut?: string
  /** Set for toggles and views; plain actions leave it out. */
  pressed?: boolean
  onClick: () => void
  className?: string
  children: React.ReactNode
}

/** A 40 px icon button with a tooltip that shows on hover and on keyboard focus (FR-1b.2). */
const RailButton: React.FC<RailButtonProps> = ({ label, shortcut, pressed, onClick, className, children }) => (
  <button
    type="button"
    className={`btn-reset rail-btn${className ? ` ${className}` : ''}`}
    aria-label={label}
    aria-pressed={pressed}
    aria-keyshortcuts={shortcut === '\\' ? 'Backslash' : shortcut}
    onClick={onClick}
  >
    {children}
    <span className="rail-tip" aria-hidden="true">
      {label}
      {shortcut && <kbd>{shortcut}</kbd>}
    </span>
  </button>
)

/** Views on top, panel and display toggles at the bottom (FR-1b.1). */
export const NavRail: React.FC = () => {
  const s = useUiStore(
    useShallow((st) => ({
      activeView: st.activeView,
      setActiveView: st.setActiveView,
      sidebarOpen: st.sidebarOpen,
      toggleSidebar: st.toggleSidebar,
      inspectorOpen: st.inspectorOpen,
      toggleInspector: st.toggleInspector,
      lightsOut: st.lightsOut,
      toggleLightsOut: st.toggleLightsOut,
      theme: st.theme,
      toggleTheme: st.toggleTheme,
      setShortcutsOpen: st.setShortcutsOpen,
    }))
  )

  return (
    <nav className="rail" aria-label="Views">
      <div className="rail-logo" title="Photo Meta Organizer" aria-hidden="true">
        <Aperture size={18} />
      </div>

      {VIEWS.map((view) => (
        <RailButton
          key={view}
          className="rail-view"
          label={VIEW_LABELS[view].label}
          shortcut={VIEW_LABELS[view].key}
          pressed={s.activeView === view}
          onClick={() => s.setActiveView(view)}
        >
          {VIEW_ICONS[view]}
        </RailButton>
      ))}

      <div className="rail-spacer" />

      {/* Panel toggles only mean something in the Library view (AC-1b.2). */}
      {s.activeView === 'studio' && (
        <>
          <RailButton label="Library panel" shortcut="\" pressed={s.sidebarOpen} onClick={s.toggleSidebar}>
            <PanelLeft size={18} />
          </RailButton>
          <RailButton label="Details panel" shortcut="I" pressed={s.inspectorOpen} onClick={s.toggleInspector}>
            <PanelRight size={18} />
          </RailButton>
        </>
      )}
      <RailButton label="Lights Out" shortcut="L" pressed={s.lightsOut} onClick={s.toggleLightsOut}>
        <EyeOff size={18} />
      </RailButton>
      <RailButton
        label={s.theme === 'dark' ? 'Light theme' : 'Dark theme'}
        onClick={s.toggleTheme}
      >
        {s.theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
      </RailButton>
      <RailButton label="Keyboard shortcuts" shortcut="?" onClick={() => s.setShortcutsOpen(true)}>
        <Keyboard size={18} />
      </RailButton>
    </nav>
  )
}
