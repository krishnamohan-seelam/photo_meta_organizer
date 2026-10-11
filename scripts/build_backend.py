"""Packaging script for Photo Meta Organizer desktop backend.

Uses PyInstaller to bundle the Python runtime and dependencies into a standalone
executable (backend_dist/photo_meta_organizer_backend.exe) for the Windows desktop app.
The built UI (frontend/dist) goes into the bundle as ``frontend_dist``, where
``api.app.default_frontend_dist`` looks for it when frozen.

Run through ``npm run backend:package`` (builds the frontend, then runs this with uv's
``build`` dependency group, which provides PyInstaller).
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ENTRY_SCRIPT = ROOT_DIR / "scripts" / "desktop_backend.py"
OUTPUT_DIR = ROOT_DIR / "desktop" / "backend_dist"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
CITIES_TABLE = ROOT_DIR / "photo_meta_organizer" / "infrastructure" / "geo" / "cities.tsv.gz"


AI_PACKAGES = ("onnxruntime", "tokenizers")


def ai_packages_present() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in AI_PACKAGES)


def build_backend():
    print(f"[*] Packaging standalone backend from: {ENTRY_SCRIPT}")
    print(f"[*] Target output directory: {OUTPUT_DIR}")

    if not (FRONTEND_DIST / "index.html").is_file():
        # Without it the installed app starts but shows "Frontend not built" (PMO-12).
        print(f"[-] {FRONTEND_DIST} is missing: run `npm run frontend:build` first.")
        sys.exit(1)

    # Search by meaning (Phase 5) needs the optional `ai` extra. Without it the build still works;
    # the app then answers 503 on the AI routes and the UI says how to enable them. The model itself
    # (~305 MB) is never bundled: the app downloads it on first use, with consent.
    with_ai = ai_packages_present()
    if with_ai:
        print("[*] Including the AI runtime (onnxruntime, tokenizers).")
    else:
        print("[!] onnxruntime/tokenizers are not installed: building WITHOUT search by meaning.")
        print("    Use `npm run backend:package` (it adds --extra ai) to include it.")

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
        # HEIC/HEIF and camera RAW decoders (PMO-23) ship native libraries.
        "--collect-all",
        "pillow_heif",
        "--collect-all",
        "rawpy",
        *(
            arg
            for package in (AI_PACKAGES if with_ai else ())
            for arg in ("--collect-all", package)
        ),
        "--exclude-module",
        "photo_meta_organizer.tests",
        "--add-data",
        f"{FRONTEND_DIST}{os.pathsep}frontend_dist",
        # Offline place names for the Map view: data, so --collect-submodules skips it.
        "--add-data",
        f"{CITIES_TABLE}{os.pathsep}photo_meta_organizer/infrastructure/geo",
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
