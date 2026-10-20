# 14: Search state in the URL (R8)

**What to build:** Views and searches are linkable, and Back, Forward and reopen-where-I-left-off work.

**Blocked by:** 13 Query tokens for every filter

**Status:** ready-for-agent

- [ ] View, filters, sort, semantic query and inspected photo are written to and read from the URL (q reuses the query parser)
- [ ] pushState for view and filter changes, replaceState for the inspected photo
- [ ] A photo= link to a photo that no longer exists shows 'no longer in the library' and does not alter the filters
- [ ] The UI store is split: only selection, dialogs, hover and panel sizes stay in Zustand
- [ ] The desktop shell reopens the last URL
