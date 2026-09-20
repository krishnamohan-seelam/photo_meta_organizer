"""Packaging script for Photo Meta Organizer desktop backend.

Uses PyInstaller to bundle the Python runtime and dependencies into a standalone
executable (backend_dist/photo_meta_organizer_backend.exe) for the Windows desktop app.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ENTRY_SCRIPT = ROOT_DIR / "scripts" / "desktop_backend.py"
OUTPUT_DIR = ROOT_DIR / "desktop" / "backend_dist"


def build_backend():
    print(f"[*] Packaging standalone backend from: {ENTRY_SCRIPT}")
    print(f"[*] Target output directory: {OUTPUT_DIR}")

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
        "--collect-all",
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
