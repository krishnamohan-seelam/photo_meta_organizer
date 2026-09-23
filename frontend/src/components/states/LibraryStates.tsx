import React from 'react'
import { AlertTriangle, FolderPlus, Loader2, RefreshCw } from 'lucide-react'

const centred: React.CSSProperties = {
  flex: 1,
  minHeight: 0,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '12px',
  padding: '40px',
  textAlign: 'center',
  color: 'var(--text-muted)',
}

/** First load of the library is in flight. */
export const LoadingState: React.FC = () => (
  <div style={centred} role="status" aria-live="polite">
    <Loader2 size={28} className="spin" />
    <div style={{ fontSize: '0.9rem' }}>Loading your library…</div>
  </div>
)

interface ErrorStateProps {
  message: string
  onRetry: () => void
  retrying: boolean
}

/** The library could not be loaded and there is nothing cached to show. */
export const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry, retrying }) => (
  <div style={centred} role="alert">
    <AlertTriangle size={32} color="var(--accent-danger)" />
    <h3 style={{ color: 'var(--text-primary)' }}>Couldn't load your library</h3>
    <p style={{ fontSize: '0.85rem', maxWidth: '420px' }}>{message}</p>
    <button className="btn btn-primary" onClick={onRetry} disabled={retrying}>
      <RefreshCw size={14} />
      <span>{retrying ? 'Retrying…' : 'Retry'}</span>
    </button>
  </div>
)

interface EmptyLibraryStateProps {
  onScan: () => void
  scanning: boolean
}

/** The backend answered and the library has no photos yet. */
export const EmptyLibraryState: React.FC<EmptyLibraryStateProps> = ({ onScan, scanning }) => (
  <div style={centred}>
    <FolderPlus size={36} color="var(--accent-primary)" />
    <h3 style={{ color: 'var(--text-primary)' }}>Your library is empty</h3>
    <p style={{ fontSize: '0.85rem', maxWidth: '420px' }}>
      Scan a folder to read the EXIF data of its photos and add them to the index.
    </p>
    <button className="btn btn-primary" onClick={onScan} disabled={scanning}>
      <FolderPlus size={14} />
      <span>{scanning ? 'Scanning…' : 'Scan folder'}</span>
    </button>
  </div>
)

interface StaleBannerProps {
  message: string
  onRetry: () => void
  retrying: boolean
}

/** A refresh failed but earlier photos are still cached: keep showing them, and say they may be out of date. */
export const StaleBanner: React.FC<StaleBannerProps> = ({ message, onRetry, retrying }) => (
  <div
    role="alert"
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
      padding: '6px 18px',
      fontSize: '0.8rem',
      color: 'var(--text-primary)',
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--accent-danger)',
    }}
  >
    <AlertTriangle size={14} color="var(--accent-danger)" />
    <span style={{ flex: 1 }}>{message} Showing the last photos that loaded.</span>
    <button className="btn btn-secondary" onClick={onRetry} disabled={retrying} style={{ padding: '2px 10px', fontSize: '0.75rem' }}>
      {retrying ? 'Retrying…' : 'Retry'}
    </button>
  </div>
)
