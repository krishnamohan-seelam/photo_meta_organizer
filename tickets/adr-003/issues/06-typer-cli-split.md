# 06: Typer CLI split

**What to build:** The command line is organised as one module per command with shared output formatting, and behaves as before.

**Blocked by:** 05 One scan pipeline (R4)

**Status:** done (2026-10-24). `photo_meta_organizer/cli/` (one module per command, `common.py` for start-up, options and the shared error list); `main.py` is the entry point. On "shared with the API response mapping": no CLI output and API wording overlap exactly (each was kept as it was), so what is shared is the start-up and output helpers across commands and the scan options and results from ticket 05. One unit test (`test_datetime_convention`) called the old argparse handler directly and now goes through `main()`; the CLI integration tests are unchanged. Review fixes: help is plain text as argparse printed it (no Rich boxes, no docstring markup, ASCII only), shortened long options (`--dry`) still work through `cli.common.Command` (an ambiguous prefix is a usage error), and Ctrl-C ends with exit code 130 (Typer's). `tests/integration/test_cli_app.py` covers `--version`, the bare command, Ctrl-C, prefixes and help. The sync output still says "deleted" (output kept unchanged); renaming it to the glossary's Missing file is left to ticket 19.

- [x] Typer added as a runtime dependency (pyproject and lock committed)
- [x] main.py split into one module per command; every existing command, flag, output and exit code preserved
- [ ] Output formatting shared with the API response mapping where they overlap (N/A: no CLI output and API wording overlap; see Status)
- [x] CLI integration tests pass unchanged
