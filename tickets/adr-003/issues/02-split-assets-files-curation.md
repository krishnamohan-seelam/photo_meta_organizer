# 02: Split the model into assets, files and curation (R3 storage)

**What to build:** The library stores each Asset once, its Files separately, and Curation on the Asset. Search, facets, collections, embeddings and AI suggestions work as before; the API still shows one path (the primary file).

**Blocked by:** 01 Migration runner and baseline (R1)

**Status:** done (2026-10-24). See ADR-003 "Implementation log" for deviations, the benchmark and the rehearsal.

- [x] Migration 0002 rebuilds photos into assets, files and curation (plus asset labels) in one transaction, lossless for existing one-path-per-hash libraries
- [x] Editing a file points its files row at the new Asset; curation is moved if no other file references the old Asset and copied if one does
- [x] Search joins files for path and size filters and returns distinct Assets; facets count Assets
- [x] replace() and the dedupe command are removed
- [x] Rehearsed against a copy of a real library, with the pre-migration backup, before it ships
- [x] The 100k-photo search benchmark is re-measured and recorded
- [x] Decide whether removed_at and ignored_files (ticket 12) belong in this migration or a later one: a later one (ticket 12), so 0002 stays a pure reshaping
