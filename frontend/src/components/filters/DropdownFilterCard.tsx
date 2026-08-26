import React, { useState } from 'react'
import { ChevronDown } from 'lucide-react'

interface DropdownFilterCardProps {
  title: string
  icon: React.ReactNode
  activeBadgeText?: string
  onReset?: () => void
  children: React.ReactNode
  defaultOpen?: boolean
}

export const DropdownFilterCard: React.FC<DropdownFilterCardProps> = ({
  title,
  icon,
  activeBadgeText,
  onReset,
  children,
  defaultOpen = true,
}) => {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: `1px solid ${open ? 'var(--accent-primary)' : 'var(--border-color)'}`,
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
    >
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: '100%',
          padding: '10px 14px',
          background: 'transparent',
          border: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          color: 'var(--text-primary)',
          fontSize: '0.82rem',
          fontWeight: 600,
          fontFamily: 'inherit',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {icon}
          <span>{title}</span>
          {activeBadgeText && (
            <span
              style={{
                fontSize: '0.7rem',
                padding: '1px 6px',
                borderRadius: 'var(--radius-full)',
                background: 'rgba(56, 189, 248, 0.15)',
                color: 'var(--accent-primary)',
                fontWeight: 700,
                marginLeft: '4px',
              }}
            >
              {activeBadgeText}
            </span>
          )}
        </div>
        <ChevronDown
          size={15}
          color="var(--text-muted)"
          style={{
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s ease',
          }}
        />
      </button>

      {open && (
        <div
          style={{
            padding: '10px 12px 12px',
            borderTop: '1px solid var(--border-subtle)',
            background: 'var(--bg-card)',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          {onReset && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingBottom: '6px',
                borderBottom: '1px solid var(--border-subtle)',
                fontSize: '0.72rem',
                color: 'var(--text-muted)',
              }}
            >
              <span>Filter options</span>
              <button
                onClick={onReset}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--accent-primary)',
                  cursor: 'pointer',
                  fontSize: '0.72rem',
                  fontWeight: 500,
                  padding: 0,
                }}
              >
                Reset
              </button>
            </div>
          )}
          {children}
        </div>
      )}
    </div>
  )
}
