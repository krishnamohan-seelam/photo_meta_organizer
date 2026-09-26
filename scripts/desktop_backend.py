"""Desktop backend runner: the Electron shell's (and the PyInstaller bundle's) entry point.

All logic lives in ``photo_meta_organizer.api.desktop``; see it for the arguments.
"""

import sys
from pathlib import Path

# Running from a source checkout without the package installed: make it importable.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from photo_meta_organizer.api.desktop import main  # noqa: E402

if __name__ == "__main__":
    main()
