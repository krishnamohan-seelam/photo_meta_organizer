"""Command-line interface (Typer): one module per command, shared start-up in ``common``.

Configures logging at start-up (not import: see ``infrastructure.logging_setup``) and
calls the application use cases, built by the shared composition root
(``application.composition``), so the CLI, the REST API and the desktop backend build
them the same way.
"""

from photo_meta_organizer.cli.app import app, run

__all__ = ["app", "run"]
