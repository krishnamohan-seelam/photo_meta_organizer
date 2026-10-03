import { describe, expect, it } from 'vitest'
import type { PhotoMetadata } from '../types/metadata'
import { makePhoto } from '../test/photos'
import { applyPatch } from './photoPatch'
import { demotion, groupByStage, kanbanStage, promotion, type KanbanStage } from './kanban'

type Fields = Partial<PhotoMetadata>

describe('kanban stages (PMO-35, D4)', () => {
  const cases: [Fields, KanbanStage][] = [
    [{}, 'inbox'],
    [{ rating: 3 }, 'inbox'],
    [{ rating: 4 }, 'picks'],
    [{ flagged: true, rating: 1 }, 'picks'],
    [{ rating: 5 }, 'export'],
    // These two used to appear in two columns at once.
    [{ flagged: true, rating: 5 }, 'export'],
    [{ rating: 2, labels: ['export'] }, 'export'],
  ]
  it.each(cases)('%o is in %s', (fields, stage) => {
    expect(kanbanStage(makePhoto(fields))).toBe(stage)
  })

  it('puts every photo in exactly one column', () => {
    const photos = [
      makePhoto({ file_hash: '1' }),
      makePhoto({ file_hash: '2', flagged: true }),
      makePhoto({ file_hash: '3', flagged: true, rating: 5 }),
      makePhoto({ file_hash: '4', labels: ['export'] }),
    ]
    const groups = groupByStage(photos)
    expect(groups.inbox.map((p) => p.file_hash)).toEqual(['1'])
    expect(groups.picks.map((p) => p.file_hash)).toEqual(['2'])
    expect(groups.export.map((p) => p.file_hash)).toEqual(['3', '4'])
  })

  it('promotion moves exactly one stage forward, and stops at the end', () => {
    let photo = makePhoto()
    photo = applyPatch(photo, promotion(photo)!)
    expect(kanbanStage(photo)).toBe('picks')
    photo = applyPatch(photo, promotion(photo)!)
    expect(kanbanStage(photo)).toBe('export')
    expect(promotion(photo)).toBeNull()
  })

  const demotions: [Fields, KanbanStage][] = [
    [{ rating: 5, flagged: true, labels: ['export', 'travel'] }, 'picks'],
    [{ rating: 2, labels: ['export'] }, 'picks'],
    [{ rating: 5 }, 'picks'],
    [{ rating: 4 }, 'inbox'],
    [{ flagged: true, rating: 2 }, 'inbox'],
  ]
  it.each(demotions)('demoting %o lands in %s', (fields, stage) => {
    const photo = makePhoto(fields)
    expect(kanbanStage(applyPatch(photo, demotion(photo)!))).toBe(stage)
  })

  it('demotion keeps unrelated tags and a low rating', () => {
    const photo = makePhoto({ rating: 2, flagged: true, labels: ['travel'] })
    const next = applyPatch(photo, demotion(photo)!)
    expect(next.rating).toBe(2)
    expect(next.labels).toEqual(['travel'])
    expect(demotion(next)).toBeNull()
  })
})
