import React, { useEffect, useRef } from 'react'

interface LoadMoreProps {
  loaded: number
  total: number
  hasMore: boolean
  loading: boolean
  onLoadMore: () => void
}

/**
 * Footer of a paged list (PMO-27): loads the next page when it scrolls into view, and offers a
 * button for keyboard users and for layouts where it never leaves the viewport.
 */
export const LoadMore: React.FC<LoadMoreProps> = ({ loaded, total, hasMore, loading, onLoadMore }) => {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el || !hasMore || loading) return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) onLoadMore()
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, loading, onLoadMore])

  if (!hasMore) return null
  return (
    <div ref={ref} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px', padding: '16px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
      <span role="status">{loading ? 'Loading more photos…' : `${loaded} of ${total} photos loaded`}</span>
      {!loading && (
        <button type="button" className="btn btn-secondary" onClick={onLoadMore} style={{ padding: '4px 10px', fontSize: '0.75rem' }}>
          Load more
        </button>
      )}
    </div>
  )
}
