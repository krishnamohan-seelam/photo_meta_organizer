# 02: Split the model into assets, files and curation (R3 storage)

**What to build:** The library stores each Asset once, its Files separately, and Curation on the Asset. Search, facets, collections, embeddings and AI suggestions work as before; the API still shows one path (the primary file).

**Blocked by:** 01 Migration runner and baseline (R1)

**Status:** ready-for-agent

- [ ] Migration 0002 rebuilds photos into assets, files and curation (plus asset labels) in one transaction, lossless for existing one-path-per-hash libraries
- [ ] Editing a file points its files row at the new Asset; curation is moved if no other file references the old Asset and copied if one does
- [ ] Search joins files for path and size filters and returns distinct Assets; facets count Assets
- [ ] replace() and the dedupe command are removed
- [ ] Rehearsed against a copy of a real library, with the pre-migration backup, before it ships
- [ ] The 100k-photo search benchmark is re-measured and recorded
- [ ] Decide whether removed_at and ignored_files (ticket 12) belong in this migration or a later one
