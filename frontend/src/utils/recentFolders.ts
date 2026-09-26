const KEY = 'pmo_recent_folders'
const MAX = 6

/** Folders the user indexed or synced recently, newest first. Storage may be unavailable: then it is empty. */
export function loadRecentFolders(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((f): f is string => typeof f === 'string').slice(0, MAX) : []
  } catch {
    return []
  }
}

export function rememberFolder(folder: string): void {
  try {
    const next = [folder, ...loadRecentFolders().filter((f) => f !== folder)].slice(0, MAX)
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // Private mode or storage disabled: remembering is a convenience only.
  }
}
