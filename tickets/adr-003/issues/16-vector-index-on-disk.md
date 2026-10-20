# 16: Vector index on disk (R6)

**What to build:** Semantic search starts fast after a restart even at 100k photos.

**Blocked by:** 01 Migration runner and baseline (R1)

**Status:** ready-for-agent

- [ ] A per-model embeddings_generation counter is bumped in the same transaction as any embedding write
- [ ] The normalised matrix and hash list are stored as a memory-mapped .npy pair whose header holds the generation; a mismatch triggers a rebuild
- [ ] nearest() sits behind a VectorIndex port; no ANN library is added
- [ ] Cold-start time is measured at 100k and recorded
