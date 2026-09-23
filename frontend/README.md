# Photo Meta Organizer: Frontend

The React single-page app for browsing and curating an indexed photo library. It talks to the FastAPI backend in [`../photo_meta_organizer/api`](../photo_meta_organizer/api) and is also the UI of the Electron desktop app in [`../desktop`](../desktop). For the project overview, see the [root README](../README.md).

**Stack:** React 19, TypeScript, Vite, Zustand (state), TanStack Virtual (gallery), Lucide (icons), Oxlint (lint).

## Commands

Run from `frontend/` (or use the root shortcuts `npm run frontend:dev` and `npm run frontend:build`).

```bash
npm install
npm run dev        # Vite dev server on http://localhost:5173
npm run build      # tsc -b && vite build; typechecks, then writes dist/
npm run lint       # oxlint
npm run preview    # serve the built dist/ locally
```

- **Dev mode needs the backend running** on `http://localhost:8000` (see the root README). Vite proxies `/api` to it, so the browser only ever talks to `localhost:5173` and no CORS is involved.
- **Production:** `npm run build` writes `dist/`. FastAPI serves it at `/` (assets at `/assets`), so one port serves both the API and the UI. If `dist/` is missing, the backend's `/` returns a "Frontend not built" page.
- **No test runner is set up yet.** The checks available are `npm run build` (types) and `npm run lint`.
- **Lint baseline:** `oxlint` currently reports 4 warnings: 3 that pre-date recent work (`App.tsx` effect and dependency warnings, and `LightboxModal.tsx` mutating a prop) and 1 inherent to TanStack Virtual (`react/incompatible-library`). Don't add new ones.

## Source layout

```
src/
├── App.tsx                 Loads all photos, applies the filters, lays out the views
├── api/client.ts           fetch helpers; every URL is relative (/api/...)
├── stores/
│   ├── useUiStore.ts       Theme, active view, filters, inspected photo, lightbox, toast
│   └── useSelectionStore.ts  Multi-select set of file hashes
├── types/
│   ├── metadata.ts         Hand-written copy of the backend's response models
│   └── electron.d.ts       window.electronAPI (desktop shell only)
└── components/
    ├── header/             AppHeader, CommandPalette (Ctrl+K)
    ├── filters/            FilterSidebar, DropdownFilterCard
    ├── gallery/            PhotoGallery (virtualized grid), PhotoCard
    ├── inspector/          ExifInspector
    ├── lightbox/           LightboxModal
    ├── collections/        SelectionDock (batch actions)
    ├── timeline/  maps/  kanban/  dashboard/   the other views
```

## How data flows

1. `App.tsx` calls `fetchPhotos` for page 1 with `page_size=500`, then fetches the remaining pages in parallel, and keeps **every photo in one `useState`**.
2. The filters (camera, tags, collection, year, search text) are applied **in the browser** in a `useMemo` over that list. The backend's `POST /api/search` is not used yet. Note that the tag filter here matches *any* selected tag, whereas the backend and CLI match *all* of them.
3. Views receive the filtered list as a prop. Edits (rating, flag, tags) call the API, then the app reloads everything through an `onRefresh` callback or the `photos-updated` window event.

**Demo fallback:** `photos` starts as a built-in `SAMPLE_PHOTOS` list, and an empty result or any API error leaves it in place. You cannot currently tell "backend down" from "empty library" from "showing demo data" (fake file hashes: their thumbnails and saves fail).

## Conventions that matter

**Read stores through selectors.** Never call `useUiStore()` or `useSelectionStore()` with no selector: the component would re-render on every store change (a toast, a slider drag), and with thousands of photos that is what made the UI slow.

```tsx
// one field
const setLightboxIndex = useUiStore((s) => s.setLightboxIndex)

// several fields: shallow-compare the picked object
const { gridItemSize, setGridItemSize } = useUiStore(
  useShallow((s) => ({ gridItemSize: s.gridItemSize, setGridItemSize: s.setGridItemSize })),
)
```

**Selection is read as a boolean.** `PhotoCard` uses `useSelectionStore((s) => s.selectedHashes.has(photo.file_hash))`. Do not use `isSelected()` for rendering: it reads `get()` and is not reactive, so a component that only subscribes to it will never update.

**`PhotoCard` is memoised** and takes `photo` and `index`. It reads its own inspected and selected state and opens the lightbox itself, so a card re-renders only when its own photo or state changes. Keep its props primitive or stable.

## The gallery (`components/gallery/PhotoGallery.tsx`)

The Studio grid is a **row virtualizer** (TanStack Virtual), so only the rows near the viewport exist in the DOM.

- The column count is computed from the scroll container's width (observed with a `ResizeObserver`) and the "Size" slider, matching what `repeat(auto-fill, minmax(size, 1fr))` would give.
- Row heights start from an estimate (`cardWidth × 0.75 + CARD_INFO_HEIGHT + gap`) and are then **measured** after render (`measureElement`). `CARD_INFO_HEIGHT` is 78 px, the measured height of the text block under the 4:3 thumbnail. Update it if you change the card's layout, or the scrollbar will drift.
- The toolbar sits above the scroll area, so it stays visible while scrolling.
- Measured on a 700-photo library in headless Edge: DOM elements 8,704 → 525, `<img>` tags 700 → 18, and 20 grid-size changes 740 ms → ~350 ms. The scroll height stayed within 1%.
- **Not virtualized yet:** the Timeline view still renders every photo.

To re-measure: serve `dist/` over a copy of a real library, open it in headless Edge over the DevTools protocol, and compare `document.querySelectorAll('*').length` and `querySelectorAll('img').length` before and after a change. (Headless Edge prints nothing to stdout on Windows, so `--dump-dom` does not work; use the protocol.)

## Desktop (Electron) integration

When loaded by the desktop shell, `window.electronAPI` is available (typed in `types/electron.d.ts`): `openDirectory()`, `showItemInFolder(path)`, `getBackendInfo()`, and `isDesktop`. "Scan Folder" in `AppHeader.tsx` uses the native folder picker when present and falls back to `window.prompt` in a browser. The renderer still uses relative `/api` URLs, so it must be loaded from the backend's origin or the Vite dev server.

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `L` | Toggle Lights Out |
| `Ctrl + K` | Command palette |
| `Esc`, `←`, `→` | Close / previous / next in the lightbox |
| `P`, `1`-`5` | Flag as pick / rate the photo in the lightbox |

The global `L` handler ignores only text inputs and does not check modifier keys, so `Ctrl + L` also triggers it.

## Known limitations

Documented in detail in [`../design_docs/design_flaws.md`](../design_docs/design_flaws.md); the work plan is in [`../design_docs/design_flaws_tickets.md`](../design_docs/design_flaws_tickets.md).

- **Placeholder areas:** the camera/tag/collection lists in `FilterSidebar` are hard-coded (with invented counts), the Map Explorer clusters are fixed examples, the EXIF histogram is drawn from sine waves, and ZIP/JSON export only show a toast. The Collections API helpers in `client.ts` are never called.
- **Failed saves look successful.** Several actions catch API errors and show a "(local)" success toast without changing anything. After a reload the change is gone.
- **Unrated photos show four stars** on the gallery cards (`rating || 4`), and a thumbnail that fails to load falls back to a stock image fetched from `images.unsplash.com`.
- **Stale views:** the inspector updates only its own copy of a photo after a save, so the grid and Kanban can show the old rating until the next reload.
- **Types are hand-copied** from the backend (`types/metadata.ts`) and can drift; there is no generated client.
- **Unused dependencies:** `@tanstack/react-query`, `clsx`, and `tailwind-merge` are declared but not used (react-query is planned for the data layer). Styling is mostly inline `style={{…}}` plus CSS variables in `index.css`.
- **Accessibility:** very few ARIA attributes, and some clickable `div`s are not keyboard-reachable.

## Tooling notes

- The React Compiler is not enabled (build-time cost); see the [React docs](https://react.dev/learn/react-compiler/installation) to add it.
- Lint rules live in `.oxlintrc.json` (`react/rules-of-hooks` as an error, `react/only-export-components` as a warning). For type-aware rules, install `oxlint-tsgolint` and set `"options": { "typeAware": true }` there. See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules).
- `@vitejs/plugin-react` (Oxc) is used; `@vitejs/plugin-react-swc` is the alternative.
