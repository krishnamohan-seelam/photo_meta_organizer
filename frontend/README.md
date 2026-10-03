# Photo Meta Organizer: Frontend

The React single-page app for browsing and curating an indexed photo library. It talks to the FastAPI backend in [`../photo_meta_organizer/api`](../photo_meta_organizer/api) and is also the UI of the Electron desktop app in [`../desktop`](../desktop). For the project overview, see the [root README](../README.md).

**Stack:** React 19, TypeScript, Vite, TanStack Query (server data), Zustand (UI state), TanStack Virtual (gallery), Lucide (icons), Oxlint (lint), Vitest + Testing Library (tests), openapi-typescript (API types).

## Commands

Run from `frontend/` (or use the root shortcuts `npm run frontend:dev` and `npm run frontend:build`).

```bash
npm install
npm run dev        # Vite dev server on http://localhost:5173
npm run build      # tsc -b && vite build; typechecks (tests included), then writes dist/
npm test           # Vitest, once (npm run test:watch to keep it running)
npm run lint       # oxlint
npm run gen:api    # regenerate src/api/schema.ts from openapi.json
npm run preview    # serve the built dist/ locally
```

- **Dev mode needs the backend running** on `http://localhost:8000` (see the root README). Vite proxies `/api` to it, so the browser only ever talks to `localhost:5173` and no CORS is involved.
- **Production:** `npm run build` writes `dist/`. FastAPI serves it at `/` (assets at `/assets`), so one port serves both the API and the UI. If `dist/` is missing, the backend's `/` returns a "Frontend not built" page.
- **Lint baseline:** one warning, inherent to TanStack Virtual (`react/incompatible-library` in `PhotoGallery.tsx`). Don't add new ones.

## API types are generated

`src/api/schema.ts` is generated from the backend's OpenAPI schema and must not be edited by hand. `types/metadata.ts` gives the generated shapes short names (`PhotoMetadata`, `SearchRequest`, `Job`, ...). After changing a route or a schema in `api/schemas.py`:

```bash
python -m scripts.export_openapi       # from the repo root: writes frontend/openapi.json
npm --prefix frontend run gen:api      # writes src/api/schema.ts
```

Commit both files. Two tests fail until you do: `test_openapi_contract.py` (pytest: `openapi.json` vs the running API) and `src/api/schema.test.ts` (Vitest: `schema.ts` vs `openapi.json`). Response fields the server always sends are required in the types, and nullable ones are `T | null`, so handle `null` where the type says so.

## Source layout

```text
src/
├── App.tsx                 Layout, view switch, loading / error / empty states
├── api/
│   ├── client.ts           fetch helpers; one request() with ApiError; every URL is relative (/api/...)
│   └── schema.ts           GENERATED from openapi.json (npm run gen:api)
├── hooks/
│   ├── usePhotos.ts        usePhotoSearch (paged search), useInspectedPhoto, the ['photos'] cache helpers
│   ├── usePhotoMutations.ts  useCuration: optimistic edits with per-photo rollback
│   ├── useFacets.ts        whole-library counts (GET /api/facets)
│   ├── useCollections.ts   useJobs.ts  useExport.ts  useDialogFocus.ts
├── stores/
│   ├── useUiStore.ts       Theme, active view, filters, sort, inspected hash, lightbox, toast
│   └── useSelectionStore.ts  Multi-select set of file hashes (with sizes)
├── utils/                  Pure helpers: search request, photo patching, Kanban stages, hotkeys, theme, ...
├── demo/                   Sample library for ?demo=1
├── types/
│   ├── metadata.ts         Names for the generated API types
│   └── electron.d.ts       window.electronAPI (desktop shell only)
├── test/                   Test setup and the makePhoto() fixture
└── components/
    ├── header/             AppHeader, CommandPalette (Ctrl+K)
    ├── filters/            FilterSidebar, DropdownFilterCard
    ├── gallery/            PhotoGallery (virtualized grid), PhotoCard
    ├── inspector/          ExifInspector
    ├── lightbox/           LightboxModal
    ├── collections/        SelectionDock (batch actions, ZIP export)
    ├── jobs/               FolderJobDialog (Scan / Sync), JobProgress
    ├── states/             Loading, error, empty and stale states; LoadMore
    ├── timeline/  maps/  kanban/  dashboard/   the other views
```

Tests sit next to the code they test (`*.test.ts(x)`). Put new shared code in `utils/`, not `src/lib/`: the root `.gitignore` ignores every `lib/` directory.

## How data flows

1. **The server filters, sorts and pages.** `usePhotoSearch()` is one `useInfiniteQuery` per filter set against `POST /api/search` (200 photos a page). `utils/search.ts` turns the store's filters into the request: dates are naive local ISO strings with no `Z` (ADR D3), and tags are AND (ADR D2). The gallery, Timeline and Kanban load further pages as you scroll or press "Load more".
2. **One cache.** Every photo query lives under the `['photos']` key (search pages, the map's geotagged set, single records); counts and analytics come from `['facets']`. Select All asks `POST /api/search/ids` for every match, not just the loaded pages.
3. **Edits are optimistic.** `useCuration()` (`hooks/usePhotoMutations.ts`) patches every cached copy at once, replaces it with the server's record on success, and on failure puts that photo back and shows an error toast with the server's `detail`. Facets are refetched afterwards. A photo edited out of the current filter stays visible until the next reload.
4. **The store holds only UI state.** The inspector keeps `inspectedHash`; `useInspectedPhoto()` serves the record from the cache or fetches it by hash, so it is never a stale copy.
5. **Honest states.** `App.tsx` shows a loading state, an error state with Retry, an empty-library state with Scan, and keeps cached photos under a banner when a refresh fails. Sample data appears only with `?demo=1`.

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

**Keep store updaters pure.** Side effects (storage, the DOM) do not belong inside a `set()` updater. The theme, for example, is saved through the guarded `utils/theme.ts`, and `App.tsx` applies it to the document in an effect. Wrap every `localStorage` access in `try/catch`: it throws when storage is disabled.

**Selection is read as a boolean.** `PhotoCard` uses `useSelectionStore((s) => s.selectedHashes.has(photo.file_hash))`. Do not use `isSelected()` for rendering: it reads `get()` and is not reactive, so a component that only subscribes to it will never update.

**`PhotoCard` is memoised** and takes `photo` and `index`. It reads its own inspected and selected state and opens the lightbox itself, so a card re-renders only when its own photo or state changes. Keep its props primitive or stable.

**Interactive elements are buttons.** Clickable cards, rows and markers are `<button>`s (the `btn-reset` class removes the button look), never nested inside another button. Dialogs use `useDialogFocus` (focus in, Tab trapped, focus restored). Single-key hotkeys go through `utils/hotkeys.shouldIgnoreHotkey`, which skips modifier combinations and typing in inputs.

**Styling:** CSS variables in `index.css` for the theme; most components still use inline `style={{…}}`. When you touch a component for another reason, moving its styles to classes in `index.css` is welcome (the Kanban board is an example); there is no plan for a big-bang rewrite, and there is no Tailwind.

## The gallery (`components/gallery/PhotoGallery.tsx`)

The Studio grid is a **row virtualizer** (TanStack Virtual), so only the rows near the viewport exist in the DOM.

- The column count is computed from the scroll container's width (observed with a `ResizeObserver`) and the "Size" slider, matching what `repeat(auto-fill, minmax(size, 1fr))` would give.
- Row heights start from an estimate (`cardWidth × 0.75 + CARD_INFO_HEIGHT + gap`) and are then **measured** after render (`measureElement`). `CARD_INFO_HEIGHT` is 78 px, the measured height of the text block under the 4:3 thumbnail. Update it if you change the card's layout, or the scrollbar will drift.
- The toolbar sits above the scroll area, so it stays visible while scrolling.
- Measured on a 700-photo library in headless Edge: DOM elements 8,704 → 525, `<img>` tags 700 → 18, and 20 grid-size changes 740 ms → ~350 ms. The scroll height stayed within 1%.
- **Not virtualized:** the Timeline and Kanban views render the pages loaded so far and load more from a footer.

To re-measure: serve `dist/` over a copy of a real library, open it in headless Edge over the DevTools protocol, and compare `document.querySelectorAll('*').length` and `querySelectorAll('img').length` before and after a change. (Headless Edge prints nothing to stdout on Windows, so `--dump-dom` does not work; use the protocol.)

## The Kanban board (`components/kanban/`)

Stages are derived from rating, flag and the `export` tag (decision D4: nothing is stored), in `utils/kanban.ts`, and each photo is in exactly one: **Export Ready** (5 stars or tagged `export`), else **Picks** (flagged or 4 stars), else **Inbox**. Forward and back actions are the smallest edit that changes the stage, so moving a card back from Export Ready drops the 5th star and the `export` tag, and moving it back from Picks unflags it and caps the rating at 3.

## Desktop (Electron) integration

When loaded by the desktop shell, `window.electronAPI` is available (typed in `types/electron.d.ts`): `openDirectory()`, `showItemInFolder(path)`, `getBackendInfo()`, and `isDesktop`. The Scan and Sync dialog (`FolderJobDialog`) shows a Browse… button that uses the native folder picker when it is present. The renderer still uses relative `/api` URLs, so it must be loaded from the backend's origin or the Vite dev server.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `L` | Toggle Lights Out |
| `Ctrl + K` | Command palette (`↑`/`↓`, `Enter`) |
| `Enter` | Open the inspected photo in the lightbox |
| `Esc`, `←`, `→` | Close / previous / next in the lightbox |
| `P`, `1`-`5` | Flag as pick / rate the photo in the lightbox |

Single-key shortcuts ignore `Ctrl`/`Alt`/`Meta` combinations and keys typed into inputs, selects, textareas and editable content; `L` is also ignored while a dialog is open.

## Known limitations

- **Placeholder areas:** the Map Explorer clusters are fixed examples (only the geotagged count is real), the EXIF histogram is drawn from sine waves, and the command palette's camera and tag filters are hardcoded (Sony, Canon, #travel).
- **No free-text search box:** the store's `searchQuery` is never set by a component, so `search_term` is reachable only through the API and CLI.
- **Batch edits after Select All** update unloaded photos on the server only; loaded ones are updated optimistically and confirmed by counts, not record by record.
- **The view tab for the Kanban board is labelled "Collections"**, which is easy to confuse with the named collections in the sidebar.

## Tooling notes

- The React Compiler is not enabled (build-time cost); see the [React docs](https://react.dev/learn/react-compiler/installation) to add it.
- Lint rules live in `.oxlintrc.json` (`react/rules-of-hooks` as an error, `react/only-export-components` as a warning). For type-aware rules, install `oxlint-tsgolint` and set `"options": { "typeAware": true }` there. See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules).
- Tests: `vitest.config.ts` runs `src/**/*.test.{ts,tsx}` in jsdom; a file that needs Node APIs starts with `// @vitest-environment node`. `tsconfig.test.json` type-checks them as part of `tsc -b`.
- `openapi-typescript` declares a TypeScript 5 peer dependency; an `overrides` entry in `package.json` points it at this project's TypeScript 6. Remove it once a release supports TypeScript 6.
- `@vitejs/plugin-react` (Oxc) is used; `@vitejs/plugin-react-swc` is the alternative.
