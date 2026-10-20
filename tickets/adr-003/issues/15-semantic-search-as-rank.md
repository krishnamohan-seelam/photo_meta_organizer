# 15: Semantic search as a ranking mode (R9)

**What to build:** Searching by meaning works with every view, Select All and export, with normal paging.

**Blocked by:** 14 Search state in the URL (R8)

**Status:** ready-for-agent

- [ ] SearchRequest accepts rank by text or like_hash; results carry score and a rank_token
- [ ] Later pages send (token, offset); an expired token returns 410 and the client reruns from page 1
- [ ] The 200 cap is replaced by the top N (default 500) or scores within a margin of the best, whichever is fewer; both are settings; 'show everything' pages the whole filtered set
- [ ] SemanticResults, semanticLimit and the lightbox's semantic paging are deleted
