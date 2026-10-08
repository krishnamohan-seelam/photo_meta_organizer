# UI prototypes

Three clickable design directions for the frontend. Each one runs on the same 18-photo sample library and contains a **Design notes** panel. The panel goes component by component (header, sidebar, card, inspector and so on) and gives the before, the after and the reason.

| File | Direction | One-line pitch |
|---|---|---|
| `a-darkroom.html` | Darkroom | Photo-first, neutral grey with a single amber accent, nav rail, justified rows, real histogram |
| `b-atelier.html` | Atelier | Editorial, warm paper and serif type, chip filter bar, trips as chapters, museum-label detail sheet |
| `c-console.html` | Console | Dense and keyboard-first, token query bar, facet distribution bars, sortable table, JSON inspector, status bar |
| `index.html` | Hub | Previews, comparison table and a suggested way to combine them |

## Viewing

- Double-click `index.html` (or any prototype) to open it in a browser. No build step and no server needed.
- Or, with the dev server running (`npm run dev` in `frontend/`), open <http://localhost:5173/src/prototypes/index.html>.

## Notes

- These are static HTML, CSS and plain JS, so they are outside the React build. `tsc` only checks `.ts/.tsx`, and Vite bundles only from `index.html` at the frontend root. Nothing here ships in `dist/`.
- `shared/sample-library.js` holds the sample data (field names follow the API's `PhotoMetadata`), procedural SVG stand-in photos and a small lucide icon set.
- `previews/*.jpg` are screenshots used by `index.html`.
- Delete this folder once a direction is chosen and ported into `src/components/`.
