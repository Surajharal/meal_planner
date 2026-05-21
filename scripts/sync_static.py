#!/usr/bin/env python3
"""Copy static/ to public/static/ for Vercel CDN (run on deploy via pyproject.toml)."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "static"
DST = ROOT / "public" / "static"


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"Missing source directory: {SRC}")
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    print(f"Synced {SRC} -> {DST}")


if __name__ == "__main__":
    main()
