import React, { useEffect, useId, useRef } from 'react'
import { Sparkles, X } from 'lucide-react'
import { useAnalysisActions, useAnalysisStatus } from '../../hooks/useAnalysis'
import { useDialogFocus } from '../../hooks/useDialogFocus'
import { useUiStore } from '../../stores/useUiStore'
import { formatBytes } from '../../utils/photoFormat'
import { analysisStep } from '../../utils/analysis'

/**
 * Set up search by meaning: tell the user what is downloaded (size, source, licence) and ask,
 * then analyze the library. Nothing is fetched until the button here is pressed, and photos
 * never leave the machine. Mounted once; open state is in the UI store.
 */
export const AiSetupDialog: React.FC = () => {
  const open = useUiStore((s) => s.aiDialogOpen)
  const setOpen = useUiStore((s) => s.setAiDialogOpen)
  if (!open) return null
  return <DialogBody onClose={() => setOpen(false)} />
}

const DialogBody: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const status = useAnalysisStatus()
  const { startDownload, startAnalysis, isStarting } = useAnalysisActions()
  const dialogRef = useRef<HTMLDivElement>(null)
  const actionRef = useRef<HTMLButtonElement>(null)
  useDialogFocus(dialogRef, actionRef)
  const titleId = useId()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const step = analysisStep(status)

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dialog-header">
          <Sparkles size={18} />
          <h2 id={titleId}>Search by meaning</h2>
          <button type="button" className="btn btn-secondary dialog-close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <p className="dialog-intro">
          Find photos by describing them (“dog on a beach”), find look-alikes, and get tag suggestions you can accept or
          dismiss. Everything runs on this computer; your photos are never uploaded.
        </p>

        {step.kind === 'loading' && <p className="dialog-note">Checking…</p>}

        {step.kind === 'no-runtime' && (
          <p className="dialog-note" role="alert">
            This build does not include the AI components. Install them with <code>uv sync --extra ai</code> and restart.
          </p>
        )}

        {step.kind === 'needs-model' && status && (
          <>
            <dl className="kv ai-facts">
              <dt>Download</dt>
              <dd className="num">{formatBytes(status.download_bytes)}, once</dd>
              <dt>Model</dt>
              <dd>{status.model_id}</dd>
              <dt>From</dt>
              <dd className="ai-source">{status.model_source}</dd>
              <dt>Licence</dt>
              <dd>{status.model_licence}</dd>
            </dl>
            <p className="dialog-note">Only the model is downloaded. Nothing about your photos is sent.</p>
          </>
        )}

        {step.kind === 'busy' && (
          <p className="dialog-note" role="status">
            {step.what === 'model-download' ? 'Downloading the model' : 'Analyzing your photos'}… progress is in the top bar.
            You can close this window and keep working.
          </p>
        )}

        {step.kind === 'needs-analysis' && status && (
          <p className="dialog-note">
            {status.pending_photos.toLocaleString()} of {status.total_photos.toLocaleString()} photos still need analysing.
            It runs in the background (roughly ten photos a second) and can be cancelled; what is done is kept.
          </p>
        )}

        {step.kind === 'ready' && status && (
          <p className="dialog-note" role="status">
            All {status.analyzed_photos.toLocaleString()} photos are analysed. Type in the search bar and choose “Search by
            meaning”. Newly imported photos are picked up the next time you analyse.
          </p>
        )}

        <div className="dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {step.kind === 'ready' || step.kind === 'busy' ? 'Close' : 'Not now'}
          </button>
          {step.kind === 'needs-model' && (
            <button
              ref={actionRef}
              type="button"
              className="btn btn-primary"
              disabled={isStarting}
              onClick={() => void startDownload().then((started) => started && onClose())}
            >
              Download model{status ? ` (${formatBytes(status.download_bytes)})` : ''}
            </button>
          )}
          {step.kind === 'needs-analysis' && (
            <button
              ref={actionRef}
              type="button"
              className="btn btn-primary"
              disabled={isStarting}
              onClick={() => void startAnalysis().then((started) => started && onClose())}
            >
              Analyze {status?.pending_photos.toLocaleString()} photos
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
