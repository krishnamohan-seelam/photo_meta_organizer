"""Packaging script for Photo Meta Organizer desktop backend.

Uses PyInstaller to bundle the Python runtime and dependencies into a standalone
executable (backend_dist/photo_meta_organizer_backend.exe) for the Windows desktop app.
The built UI (frontend/dist) goes into the bundle as ``frontend_dist``, where
``api.app.default_frontend_dist`` looks for it when frozen.

Run through ``npm run backend:package`` (builds the frontend, then runs this with uv's
``build`` dependency group, which provides PyInstaller).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ENTRY_SCRIPT = ROOT_DIR / "scripts" / "desktop_backend.py"
OUTPUT_DIR = ROOT_DIR / "desktop" / "backend_dist"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


def build_backend():
    print(f"[*] Packaging standalone backend from: {ENTRY_SCRIPT}")
    print(f"[*] Target output directory: {OUTPUT_DIR}")

    if not (FRONTEND_DIST / "index.html").is_file():
        # Without it the installed app starts but shows "Frontend not built" (PMO-12).
        print(f"[-] {FRONTEND_DIST} is missing: run `npm run frontend:build` first.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name",
        "photo_meta_organizer_backend",
        "--distpath",
        str(OUTPUT_DIR),
        # Code only: --collect-all would also copy whatever sits in the package directory
        # (logs, coverage reports, local databases) into every installer.
        "--collect-submodules",
        "photo_meta_organizer",
        "--collect-all",
        "uvicorn",
        "--collect-all",
        "fastapi",
        "--collect-all",
        "tinydb",
        "--collect-all",
        "PIL",
        "--collect-all",
        "exifread",
        "--exclude-module",
        "photo_meta_organizer.tests",
        "--add-data",
        f"{FRONTEND_DIST}{os.pathsep}frontend_dist",
        str(ENTRY_SCRIPT),
    ]

    print(f"[*] Executing command: {' '.join(pyinstaller_cmd)}")
    result = subprocess.run(pyinstaller_cmd, cwd=str(ROOT_DIR))

    if result.returncode == 0:
        print("[+] Backend packaging completed successfully!")
    else:
        print(f"[-] Packaging failed with exit code: {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build_backend()
