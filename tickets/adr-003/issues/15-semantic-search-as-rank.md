# 15: Semantic search as a ranking mode (R9)

**What to build:** Searching by meaning works with every view, Select All and export, with normal paging.

**Blocked by:** 14 Search state in the URL (R8)

**Status:** done (2026-10-28). `SearchRequest.rank` (`text` or `like_hash`, plus `everything`) and `rank_token`; `PaginatedPhotosResponse.scores` and `rank_token`. `application/ranking.py`: `cut_off` (top N, then scores within the margin of the best; `everything` keeps all) and `RankSnapshots` (token -> ranked hashes and scores, TTL 600 s, at most 32, LRU). Settings `semantic_top_n` / `semantic_margin` (`PMO_SEMANTIC_TOP_N` 500, `PMO_SEMANTIC_MARGIN` 0.08). A later page with an unknown or expired token is 410; `usePhotoSearch` sends page 1's token and resets the query to page 1 on 410. `/api/search/ids` returns the ranked list (Select All). Photos removed after the ranking are left out of their page. `POST /api/search/semantic` and its schemas are gone; the inspector's Similar strip is page 1 of a `like_hash` ranking (`useSimilarPhotos`). `SemanticResults`, `semanticLimit` and the lightbox's semantic paging are deleted; `SemanticBanner` names the ranking above the Library with Show everything / Clear (URL `ranked=all`), and the sort buttons hide while ranked. 'Show everything' ranks every analysed photo that passes the filters (unanalysed photos have no score and are not listed). Not done: tuning N and the margin against the 100k benchmark (needs the real model); the defaults are a first guess.

- [x] SearchRequest accepts rank by text or like_hash; results carry score and a rank_token
- [x] Later pages send (token, offset); an expired token returns 410 and the client reruns from page 1
- [x] The 200 cap is replaced by the top N (default 500) or scores within a margin of the best, whichever is fewer; both are settings; 'show everything' pages the whole filtered set
- [x] SemanticResults, semanticLimit and the lightbox's semantic paging are deleted
