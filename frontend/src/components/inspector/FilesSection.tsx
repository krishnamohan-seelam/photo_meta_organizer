import React from 'react'
import type { PhotoPath } from '../../types/metadata'
import { formatBytes } from '../../utils/photoFormat'

/**
 * Every file that holds this photo (ADR-003 R3), the primary one first. More than one means the
 * same content is kept in several places: a duplicate. Nothing here changes a file on disk.
 */
export const FilesSection: React.FC<{ paths: PhotoPath[] }> = ({ paths }) => {
  if (paths.length === 0) return null
  const duplicate = paths.length > 1
  return (
    <section className="insp-sec" aria-label="Files">
      <h3>{duplicate ? `Stored in ${paths.length} places` : 'File'}</h3>
      <ul className="insp-files">
        {paths.map((p, i) => (
          <li key={p.path} title={p.path}>
            <span className="insp-file-path">{p.path}</span>
            <span className="insp-file-meta">
              {formatBytes(p.size_bytes)}
              {i === 0 && duplicate ? ' · shown' : ''}
              {p.missing ? ' · missing' : ''}
              {p.hidden ? ' · hidden' : ''}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
