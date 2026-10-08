import { create } from 'zustand'
import type { PhotoId } from '../types/metadata'

interface SelectionState {
  selectedHashes: Set<string>
  /** Size of each selected photo, so the dock can total a selection whose photos are not all loaded. */
  selectedSizes: Map<string, number>
  toggleSelect: (hash: string, sizeBytes: number) => void
  /** Replace the selection, e.g. with every match of the current search (`POST /api/search/ids`). */
  selectAll: (photos: PhotoId[]) => void
  /** Add photos to the selection, keeping what is already selected (range selection). */
  addToSelection: (photos: PhotoId[]) => void
  clearSelection: () => void
  isSelected: (hash: string) => boolean
}

export const useSelectionStore = create<SelectionState>((set, get) => ({
  selectedHashes: new Set<string>(),
  selectedSizes: new Map<string, number>(),

  toggleSelect: (hash, sizeBytes) =>
    set((state) => {
      const hashes = new Set(state.selectedHashes)
      const sizes = new Map(state.selectedSizes)
      if (hashes.has(hash)) {
        hashes.delete(hash)
        sizes.delete(hash)
      } else {
        hashes.add(hash)
        sizes.set(hash, sizeBytes)
      }
      return { selectedHashes: hashes, selectedSizes: sizes }
    }),

  selectAll: (photos) =>
    set({
      selectedHashes: new Set(photos.map((p) => p.file_hash)),
      selectedSizes: new Map(photos.map((p) => [p.file_hash, p.size_bytes])),
    }),

  addToSelection: (photos) =>
    set((state) => {
      const hashes = new Set(state.selectedHashes)
      const sizes = new Map(state.selectedSizes)
      for (const p of photos) {
        hashes.add(p.file_hash)
        sizes.set(p.file_hash, p.size_bytes)
      }
      return { selectedHashes: hashes, selectedSizes: sizes }
    }),

  clearSelection: () =>
    set({
      selectedHashes: new Set<string>(),
      selectedSizes: new Map<string, number>(),
    }),

  isSelected: (hash: string) => get().selectedHashes.has(hash),
}))
