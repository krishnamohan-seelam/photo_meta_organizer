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
    ├── shell/              NavRail (views, panel toggles)
    ├── header/             TopBar, QueryBar, JobStatusPill, CommandPalette (Ctrl+K), ShortcutsOverlay (?)
    ├── filters/            LibraryPanel
    ├── gallery/            LibraryView (toolbar), PhotoGallery (justified grid), PhotoCard, PhotoTable
    ├── inspector/          ExifInspector (real histogram)
    ├── lightbox/           LightboxModal
    ├── collections/        SelectionDock (batch actions, export), NameDialog
    ├── jobs/               FolderJobDialog (Scan / Sync)
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

**Styling:** design tokens are CSS variables at the top of `index.css` (hue-free greys, one amber accent, both themes; see `design_docs/front_enddesign.md` §4.1). The redesigned components use classes in `index.css` and take colours only from the variables; the Dashboard view still uses inline `style={{…}}`, and moving them to classes when you touch them is welcome. There is no Tailwind.

**Accent:** `--accent-primary` is only for selection, picks, primary buttons, active filters and focus. Use the neutral tokens for everything else.

## The Library view (`components/gallery/`)

`LibraryView` puts one toolbar (title, counts, filter chips, sort, layout, size) over either layout; `V` switches them and the choice is remembered. Both keep the filters, the selection, the inspected photo and the top photo in view.

- **Grid (`PhotoGallery`, `PhotoCard`):** justified rows from `utils/justifiedLayout.justifiedRows`, a pure function of the photos' aspect ratios, the container width (observed with a `ResizeObserver`) and the row-height slider. Ratios come from stored dimensions only (`utils/photoFormat.photoAspectRatio`), swapped for EXIF orientations 5-8 because the backend renders thumbnails upright, and clamped to 0.4-3.5. Row heights are therefore exact: the virtualizer never measures, and nothing depends on images having loaded.
- **Table (`PhotoTable`):** fixed 38 px rows, a sticky header, and server sorting on Name, Camera, Captured and Size only (the API cannot sort by the others). A container query hides Lens and Size when the table is narrower than 1000 px.
- **Virtualization:** a test renders 20,000 photos in each layout and asserts at most 60 rows in the DOM. Both prefetch the next page before the end of what is loaded.
- **Keyboard:** `hooks/useLibraryHotkeys` serves both layouts (arrows or J/K, 0-5, P, X, Enter/Space, Esc); it is quiet while typing, with a modifier, or while any dialog is open.
- **Not virtualized:** the Timeline (chapters use `content-visibility: auto`) and Kanban views render the pages loaded so far and load more from a footer.

To measure in a browser: serve `dist/` from the backend, open it in headless Edge over the DevTools protocol, and count `document.querySelectorAll('*')` and `img` before and after a change. (Headless Edge prints nothing to stdout on Windows, so `--dump-dom` does not work; use the protocol.)

## The query bar (`components/header/QueryBar.tsx`, `utils/query.ts`)

The store stays the single source of truth. `utils/query.ts` is pure: `parseQuery` (text to tokens, with `invalid` tokens carrying a reason), `resolveTokens` (match `make:` and `in:` to the library's real names), `tokensToFilters` and `filtersToTokens` (round-trip stable). The bar shows `filtersToTokens(store)`, applies committed tokens with `applyQueryFilters`, keeps invalid tokens locally (never sent), and treats plain words as live search text (250 ms debounce). The syntax is documented in the root README.

## The Kanban board (`components/kanban/`)

Stages are derived from rating, flag and the `export` tag (decision D4: nothing is stored), in `utils/kanban.ts`, and each photo is in exactly one: **Export Ready** (5 stars or tagged `export`), else **Picks** (flagged or 4 stars), else **Inbox**. Forward and back actions are the smallest edit that changes the stage, so moving a card back from Export Ready drops the 5th star and the `export` tag, and moving it back from Picks unflags it and caps the rating at 3.

## Desktop (Electron) integration

When loaded by the desktop shell, `window.electronAPI` is available (typed in `types/electron.d.ts`): `openDirectory()`, `showItemInFolder(path)`, `getBackendInfo()`, and `isDesktop`. The Scan and Sync dialog (`FolderJobDialog`) shows a Browse… button that uses the native folder picker when it is present. The renderer still uses relative `/api` URLs, so it must be loaded from the backend's origin or the Vite dev server.

## Keyboard shortcuts

The full map is in `utils/shortcuts.ts` and in the app under `?`. App-wide keys live in `hooks/useGlobalHotkeys.ts`, Library keys in `hooks/useLibraryHotkeys.ts`, viewer keys in `LightboxModal`.

| Key | Action |
| --- | --- |
| `Ctrl + K` · `/` · `?` | Command palette · focus the query bar · shortcut list |
| `G` `T` `M` `C` `A` | Library · Timeline · Map · Collections · Insights |
| `\` · `I` · `L` · `V` | Library panel · Details panel · Lights Out · grid/table |
| `←` `→` (grid), `J` `K` `↑` `↓` (table) | Move the inspected photo (`Shift` extends the selection in the table) |
| `1`-`5` · `0` · `P` | Rate · clear rating · toggle Pick (Library and viewer) |
| `X` (`Space` in the table) · `Enter` | Toggle selection · open the viewer |
| `Esc` | Close the dialog, then clear the selection |

Single-key shortcuts ignore `Ctrl`/`Alt`/`Meta` combinations, keys typed into inputs, selects, textareas and editable content, and everything while a dialog is open (`utils/shortcuts.dialogOpen`).

## Known limitations

- **Map Explorer:** `maps/LeafletMap.tsx` is the only file that touches Leaflet; clusters come from `POST /api/geo/clusters` (`hooks/useGeoClusters.ts`), the pure viewport and demo-clustering helpers are in `utils/geo.ts`. The view is lazy-loaded from `App.tsx`. The offline basemap is the `world-atlas` outline; `GET /api/config` supplies an opt-in tile server.
- **Query bar limits:** only the fields the search API supports. ISO, aperture, focal length and lens filters, `rating:>=4`, and `pick:no` need backend changes (design doc §9).
- **Batch edits after Select All** update unloaded photos on the server only; loaded ones are updated optimistically and confirmed by counts, not record by record.
- **The view tab for the Kanban board is labelled "Collections"**, which is easy to confuse with the named collections in the sidebar.

## Tooling notes

- The React Compiler is not enabled (build-time cost); see the [React docs](https://react.dev/learn/react-compiler/installation) to add it.
- Lint rules live in `.oxlintrc.json` (`react/rules-of-hooks` as an error, `react/only-export-components` as a warning). For type-aware rules, install `oxlint-tsgolint` and set `"options": { "typeAware": true }` there. See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules).
- Tests: `vitest.config.ts` runs `src/**/*.test.{ts,tsx}` in jsdom; a file that needs Node APIs starts with `// @vitest-environment node`. `tsconfig.test.json` type-checks them as part of `tsc -b`.
- `openapi-typescript` declares a TypeScript 5 peer dependency; an `overrides` entry in `package.json` points it at this project's TypeScript 6. Remove it once a release supports TypeScript 6.
- `@vitejs/plugin-react` (Oxc) is used; `@vitejs/plugin-react-swc` is the alternative.
