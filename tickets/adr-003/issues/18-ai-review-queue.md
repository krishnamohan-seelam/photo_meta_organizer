# 18: AI review queue

**What to build:** A user can work through AI suggestions in bulk, best first, from the keyboard.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] First a test that retag() honours existing rejected rows (reject is remembered per asset and label), and a fix if it fails
- [ ] A 'Review suggestions' view ordered by the top open suggestion's confidence, grouped by label
- [ ] Keys: A accept, R reject, J/K next and previous
- [ ] Bulk 'accept all above 0.30 for this label' shows the count before it applies
