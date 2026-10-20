# 06: Typer CLI split

**What to build:** The command line is organised as one module per command with shared output formatting, and behaves as before.

**Blocked by:** 05 One scan pipeline (R4)

**Status:** ready-for-agent

- [ ] Typer added as a runtime dependency (pyproject and lock committed)
- [ ] main.py split into one module per command; every existing command, flag, output and exit code preserved
- [ ] Output formatting shared with the API response mapping where they overlap
- [ ] CLI integration tests pass unchanged
