import React, { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import { useUiStore } from '../../stores/useUiStore'
import { useFacets } from '../../hooks/useFacets'
import { useCollections } from '../../hooks/useCollections'
import { aiSearchReady, useAnalysisStatus } from '../../hooks/useAnalysis'
import { useLibraryFilters } from '../../hooks/useLibraryFilters'
import { SEARCH_INPUT_ID } from '../../hooks/useGlobalHotkeys'
import { UNKNOWN_DATE } from '../../utils/captureDate'
import {
  QUERY_FIELDS,
  filtersToTokens,
  parseQuery,
  resolveTokens,
  tokenKey,
  tokenText,
  tokensToFilters,
  type QueryContext,
  type QueryField,
  type Token,
} from '../../utils/query'

const LIVE_DELAY_MS = 250
const MAX_SUGGESTIONS = 8

interface Suggestion {
  id: string
  label: string
  detail?: string
  /** A field name to complete into the input, or query text to commit. */
  fill?: string
  commit?: string
  /** Run a search by meaning, or open the AI setup when it is not ready. */
  meaning?: string
}

/** A complete, unquoted `field:value` (a space after it commits it, FR-2b.2). */
const COMPLETE_FIELD = /^[A-Za-z]+:[^"\s]+$/
/** Plain words, edited live as the search text. */
const isPlainText = (draft: string) => draft.trim() !== '' && !/^[A-Za-z]+:/.test(draft.trim()) && !draft.trim().startsWith('"')

function valuesFor(field: QueryField, ctx: { cameras: { name: string; count: number }[]; tags: { name: string; count: number }[]; years: { name: string; count: number }[]; collections: { name: string; count: number }[]; undated: number }) {
  switch (field) {
    case 'make':
      return ctx.cameras
    case 'tag':
      return ctx.tags
    case 'in':
      return ctx.collections
    case 'year':
      return [...[...ctx.years].sort((a, b) => b.name.localeCompare(a.name)), ...(ctx.undated > 0 ? [{ name: UNKNOWN_DATE, count: ctx.undated }] : [])]
    case 'rating':
      return [5, 4, 3, 2, 1].map((n) => ({ name: String(n), count: -1 }))
    case 'pick':
      return [{ name: 'yes', count: -1 }]
    case 'geo':
      return [
        { name: 'yes', count: -1 },
        { name: 'no', count: -1 },
      ]
    default:
      return []
  }
}

/**
 * Filters as typed tokens (FR-2b): another editor of the store's filters, so the panel, the chips and
 * this bar always agree. Invalid tokens are shown in the danger colour and never sent to the server.
 */
export const QueryBar: React.FC = () => {
  const filters = useLibraryFilters()
  const facets = useFacets()
  const collections = useCollections()
  const analysis = useAnalysisStatus()
  const aiReady = aiSearchReady(analysis)
  const [draft, setDraft] = useState('')
  const [invalid, setInvalid] = useState<Token[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()
  const liveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // The search text before the current draft started, restored when the draft stops being plain words.
  const baseText = useRef<string | null>(null)

  const ctx: QueryContext = useMemo(
    () => ({ cameras: facets.cameras.map((c) => c.name), collections: collections.map((c) => c.name) }),
    [facets.cameras, collections]
  )
  const storeTokens = useMemo(() => filtersToTokens(filters), [filters])
  const liveDraft = isPlainText(draft)
  // While plain words are being typed they are the search text: show them in the input, not as a token too.
  const shownTokens = liveDraft ? storeTokens.filter((t) => t.kind !== 'text') : storeTokens

  useEffect(() => () => {
    if (liveTimer.current) clearTimeout(liveTimer.current)
  }, [])

  const apply = (tokens: Token[]) => useUiStore.getState().applyQueryFilters(tokensToFilters(tokens))

  const setLive = (text: string) => {
    if (liveTimer.current) clearTimeout(liveTimer.current)
    liveTimer.current = setTimeout(() => {
      liveTimer.current = null
      useUiStore.getState().setSearchQuery(text)
    }, LIVE_DELAY_MS)
  }

  const onDraftChange = (next: string) => {
    if (baseText.current === null) baseText.current = useUiStore.getState().searchQuery
    setDraft(next)
    setOpen(true)
    setActive(0)
    if (isPlainText(next)) setLive(next.trim())
    else if (liveDraft || next === '') setLive(baseText.current ?? '')
    if (next === '') baseText.current = null
  }

  /** Parse `text`, apply its valid tokens at once (FR-2b.4) and keep the invalid ones on show. */
  const commit = (text: string) => {
    if (liveTimer.current) clearTimeout(liveTimer.current)
    liveTimer.current = null
    const parsed = resolveTokens(parseQuery(text), ctx)
    const valid = parsed.filter((t) => t.kind !== 'invalid')
    const bad = parsed.filter((t) => t.kind === 'invalid')
    // A committed plain draft is already the live search text; re-applying it is harmless.
    if (valid.length > 0) apply([...storeTokens.filter((t) => !(liveDraft && t.kind === 'text')), ...valid])
    else if (liveDraft) useUiStore.getState().setSearchQuery(draft.trim())
    if (bad.length > 0) setInvalid((current) => [...current, ...bad])
    baseText.current = null
    setDraft('')
    setActive(0)
  }

  const removeToken = (token: Token) => {
    if (token.kind === 'invalid') setInvalid((current) => current.filter((t) => t !== token))
    else apply(storeTokens.filter((t) => tokenKey(t) !== tokenKey(token)))
    inputRef.current?.focus()
  }

  const suggestions = useMemo<Suggestion[]>(() => {
    const text = draft.trimStart()
    const m = text.match(/^([A-Za-z]+):"?(.*)$/)
    if (m) {
      const field = m[1].toLowerCase() as QueryField
      if (!QUERY_FIELDS.some((f) => f.field === field)) return []
      const prefix = m[2].toLowerCase()
      const values = valuesFor(field, {
        cameras: facets.cameras,
        tags: facets.tags,
        years: facets.years,
        collections: collections.map((c) => ({ name: c.name, count: c.photo_hashes.length })),
        undated: facets.stats.undated_count,
      })
      const found = values
        .filter((v) => v.name.toLowerCase().startsWith(prefix))
        .slice(0, MAX_SUGGESTIONS)
        .map<Suggestion>((v) => {
          const token: Token = { kind: 'field', field, value: v.name }
          return { id: `v-${field}-${v.name}`, label: tokenText(token), detail: v.count >= 0 ? String(v.count) : undefined, commit: tokenText(token) }
        })
      // Fields without a value list (model, date) commit what was typed.
      if (found.length === 0 && m[2].trim()) return [{ id: 'typed', label: text, commit: text }]
      return found
    }
    const lower = text.toLowerCase()
    const fields = QUERY_FIELDS.filter((f) => f.field.startsWith(lower)).map<Suggestion>((f) => ({
      id: `f-${f.field}`,
      label: `${f.field}:`,
      detail: `${f.description} · ${f.example}`,
      fill: `${f.field}:`,
    }))
    if (!text.trim()) return fields
    const typed: Suggestion = { id: 'text', label: `Search for “${text.trim()}”`, commit: text.trim().includes(' ') ? `"${text.trim()}"` : text.trim() }
    // Offered only when the backend has the AI extra; without the model it leads to the setup dialog.
    const meaning: Suggestion[] = analysis?.runtime_installed
      ? [{ id: 'meaning', label: `Search by meaning “${text.trim()}”`, detail: aiReady ? 'AI' : 'set up first', meaning: text.trim() }]
      : []
    return [typed, ...meaning, ...fields]
  }, [draft, facets, collections, analysis?.runtime_installed, aiReady])

  const current = Math.min(active, Math.max(0, suggestions.length - 1))
  const showList = open && suggestions.length > 0
  const optionId = (s: Suggestion) => `${listId}-${s.id.replace(/[^\w-]/g, '_')}`
  const activeId = showList ? optionId(suggestions[current]) : undefined

  const choose = (s: Suggestion) => {
    if (s.meaning !== undefined) {
      if (aiReady) useUiStore.getState().setSemantic({ kind: 'text', text: s.meaning })
      else useUiStore.getState().setAiDialogOpen(true)
      if (liveTimer.current) clearTimeout(liveTimer.current)
      liveTimer.current = null
      // The words were being applied live as a text filter; a search by meaning replaces that.
      useUiStore.getState().setSearchQuery(baseText.current ?? '')
      baseText.current = null
      setDraft('')
      setOpen(false)
    } else if (s.fill) {
      onDraftChange(s.fill)
      inputRef.current?.focus()
    } else if (s.commit !== undefined) {
      commit(s.commit)
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!showList) return setOpen(true)
      e.preventDefault()
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((current + step + suggestions.length) % suggestions.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      // The highlighted suggestion completes what was typed ("make:so" → make:Sony); otherwise commit as typed.
      if (showList && draft.trim() !== '') choose(suggestions[current])
      else if (draft.trim()) commit(draft)
    } else if (e.key === 'Tab' && showList && draft.trim() !== '') {
      e.preventDefault()
      choose(suggestions[current])
    } else if (e.key === ' ' && COMPLETE_FIELD.test(draft.trim())) {
      e.preventDefault()
      commit(draft)
    } else if (e.key === 'Backspace' && draft === '') {
      const all = [...shownTokens, ...invalid]
      const last = all[all.length - 1]
      if (last) {
        e.preventDefault()
        removeToken(last)
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      e.currentTarget.blur()
    }
  }

  // Keep the highlighted suggestion in view.
  useEffect(() => {
    if (activeId) document.getElementById(activeId)?.scrollIntoView?.({ block: 'nearest' })
  }, [activeId])

  const renderToken = (t: Token) => {
    const label = tokenText(t)
    return (
      <span
        key={tokenKey(t)}
        className={`qtok${t.kind === 'invalid' ? ' qtok-invalid' : ''}`}
        title={t.kind === 'invalid' ? `${t.reason} · not applied` : undefined}
      >
        {t.kind === 'field' ? (
          <>
            <span className="qtok-field">{t.field}:</span>
            <span className="qtok-value">{label.slice(t.field.length + 1)}</span>
          </>
        ) : (
          <span className="qtok-value">{label}</span>
        )}
        {t.kind === 'invalid' && <span className="visually-hidden">, invalid: {t.reason}</span>}
        <button type="button" className="btn-reset" aria-label={`Remove ${label}`} onClick={() => removeToken(t)}>
          <X size={11} />
        </button>
      </span>
    )
  }

  return (
    <div className="query-bar" onClick={() => inputRef.current?.focus()}>
      <Search size={15} aria-hidden="true" className="query-icon" />
      <div className="qtoks" aria-label="Active filters">
        {shownTokens.map(renderToken)}
        {invalid.map(renderToken)}
        <input
          ref={inputRef}
          id={SEARCH_INPUT_ID}
          type="text"
          role="combobox"
          aria-label="Filter photos"
          aria-keyshortcuts="/"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          autoComplete="off"
          spellCheck={false}
          placeholder={shownTokens.length + invalid.length === 0 ? 'Filter… try make:sony tag:night rating:5' : ''}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
        />
      </div>
      <kbd className="kbd-chip">/</kbd>
      {showList && (
        <div id={listId} role="listbox" aria-label="Suggestions" className="qsuggest">
          {suggestions.map((s, i) => (
            <div
              key={s.id}
              id={optionId(s)}
              role="option"
              aria-selected={i === current}
              className="qsuggest-option"
              // mousedown, not click: the input must not lose focus (and close the list) first.
              onMouseDown={(e) => {
                e.preventDefault()
                choose(s)
              }}
              onMouseMove={() => i !== current && setActive(i)}
            >
              <span className="qsuggest-label">{s.label}</span>
              {s.detail && <span className="qsuggest-detail">{s.detail}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
