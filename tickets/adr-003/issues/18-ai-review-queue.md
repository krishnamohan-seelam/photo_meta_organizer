# 18: AI review queue

**What to build:** A user can work through AI suggestions in bulk, best first, from the keyboard.

**Blocked by:** None (can start immediately)

**Status:** done (2026-10-25). The retag test already existed and passed (`test_keeps_what_the_user_decided`); `test_a_decision_belongs_to_one_photo_and_one_label` adds accepted labels, a second retag and the other photo. `AnalysisRepository.review_labels/review_items/count_open`; `GET /api/ai-tags/review` (labels, most confident first), `GET /api/ai-tags/review/items?label=` (best first, paged), `GET /api/ai-tags/review/count`, `POST /api/ai-tags/accept-above`; `ResolveAiTagsUseCase.accept_above`. UI: `ReviewSuggestionsDialog` (one label at a time, A accept, R reject, J/K or arrows to move, accept-all with the count shown and a confirm step, default 0.30), opened from the palette or the Library panel's 'Suggested by AI' section.

- [x] First a test that retag() honours existing rejected rows (reject is remembered per asset and label), and a fix if it fails
- [x] A 'Review suggestions' view ordered by the top open suggestion's confidence, grouped by label
- [x] Keys: A accept, R reject, J/K next and previous
- [x] Bulk 'accept all above 0.30 for this label' shows the count before it applies
