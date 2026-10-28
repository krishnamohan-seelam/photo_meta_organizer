# 14: Search state in the URL (R8)

**What to build:** Views and searches are linkable, and Back, Forward and reopen-where-I-left-off work.

**Blocked by:** 13 Query tokens for every filter

**Status:** done (2026-10-28). `utils/urlState.ts` turns the view (`view=library|timeline|map|kanban|analytics`), the filters (`q`, through `utils/query.ts`), `sort=<field>-<asc|desc>`, a search by meaning (`meaning=` or `like=<hash>&name=`) and `photo=<hash>` into a query string and back; defaults are left out and parameters it does not own (`demo=1`) are kept. `stores/useViewStore.ts` holds that state and `startUrlSync()` (called in `main.tsx`) mirrors it: pushState for view/filter/sort changes, replaceState for the inspected photo and for typing in the query bar within 1 s of the last change, and `popstate` reads the URL back. `useUiStore` keeps only transient state (dialogs, panels, layout, toasts, lightbox); selection is in `useSelectionStore`. `useInspectedPhoto()` now returns `{ photo, missing }`; a 404 shows 'This photo is no longer in the library' and leaves the filters alone. The desktop shell stores the last query string in `<userData>/last-view.json` on `did-navigate-in-page` and reopens it (the port changes per launch, so only the query string is kept). `semanticLimit` stays in the view store, out of the URL, until ticket 15 removes it.

- [x] View, filters, sort, semantic query and inspected photo are written to and read from the URL (q reuses the query parser)
- [x] pushState for view and filter changes, replaceState for the inspected photo
- [x] A photo= link to a photo that no longer exists shows 'no longer in the library' and does not alter the filters
- [x] The UI store is split: only selection, dialogs, hover and panel sizes stay in Zustand
- [x] The desktop shell reopens the last URL
