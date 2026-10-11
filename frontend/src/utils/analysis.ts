import type { AnalysisStatus } from '../types/metadata'

/** Where the user is in setting up search by meaning; one value drives the dialog. */
export type AnalysisStep =
  | { kind: 'loading' }
  | { kind: 'no-runtime' }
  | { kind: 'busy'; what: 'model-download' | 'analyze' }
  | { kind: 'needs-model' }
  | { kind: 'needs-analysis' }
  | { kind: 'ready' }

export function analysisStep(status: AnalysisStatus | undefined): AnalysisStep {
  if (!status) return { kind: 'loading' }
  if (!status.runtime_installed) return { kind: 'no-runtime' }
  if (status.active_job_id) {
    return { kind: 'busy', what: status.active_job_kind === 'model-download' ? 'model-download' : 'analyze' }
  }
  if (!status.model_installed) return { kind: 'needs-model' }
  if (status.pending_photos > 0) return { kind: 'needs-analysis' }
  return { kind: 'ready' }
}

/** A relevance score (cosine similarity) as a short percentage for the result tiles. */
export function formatScore(score: number): string {
  return `${Math.round(Math.max(0, Math.min(1, score)) * 100)}%`
}
