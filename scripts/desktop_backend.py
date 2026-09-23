"""Desktop Backend Runner for Photo Meta Organizer.

This script acts as the entrypoint for the Electron desktop shell or PyInstaller
standalone executable. It starts the FastAPI server on the requested host and port
and emits readiness signals on stdout.
"""

import argparse
from pathlib import Path
import sys

# Ensure repository root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from photo_meta_organizer.api.app import create_app
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Photo Meta Organizer Desktop Backend")
    parser.add_argument("--host", default="127.0.0.1", help="Binding host")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--db", default="photos.db", help="Path to database file")
    args = parser.parse_args()

    app = create_app(db_path=args.db)

    # Emit ready token for Electron main process to read
    print(f"DESKTOP_BACKEND_READY:{args.port}", flush=True)

    config = uvicorn.Config(
        app=app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
