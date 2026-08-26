import { create } from 'zustand'

interface SelectionState {
  selectedHashes: Set<string>
  toggleSelect: (hash: string) => void
  selectAll: (hashes: string[]) => void
  clearSelection: () => void
  isSelected: (hash: string) => boolean
}

export const useSelectionStore = create<SelectionState>((set, get) => ({
  selectedHashes: new Set<string>(),

  toggleSelect: (hash: string) =>
    set((state) => {
      const next = new Set(state.selectedHashes)
      if (next.has(hash)) {
        next.delete(hash)
      } else {
        next.add(hash)
      }
      return { selectedHashes: next }
    }),

  selectAll: (hashes: string[]) =>
    set({
      selectedHashes: new Set(hashes),
    }),

  clearSelection: () =>
    set({
      selectedHashes: new Set<string>(),
    }),

  isSelected: (hash: string) => get().selectedHashes.has(hash),
}))
