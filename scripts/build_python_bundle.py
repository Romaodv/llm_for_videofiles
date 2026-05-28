#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "vendor" / "python"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "venv", "--copies", str(OUT)], cwd=ROOT, check=True)

    python_bin = OUT / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
    subprocess.run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=ROOT, check=True)

    print(f"Python bundle criado em: {OUT}")
    print("Esse bundle sera incluido pelo Electron Builder como runtime Python embutido.")


if __name__ == "__main__":
    main()
