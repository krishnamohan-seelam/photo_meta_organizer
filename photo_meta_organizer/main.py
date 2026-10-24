"""Command-line entry point for Photo Meta Organizer.

The commands live in ``photo_meta_organizer.cli`` (one module per command, Typer).

Example:
    $ python -m photo_meta_organizer.main --help
    $ python -m photo_meta_organizer.main index --path /photos
    $ python -m photo_meta_organizer.main paths     # where the library, cache and logs live
"""

import sys

from photo_meta_organizer.cli import run


def main() -> int:
    """Run the command given on the command line; returns the process exit code."""
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
