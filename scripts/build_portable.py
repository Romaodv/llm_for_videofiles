#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "dist"
OUT = OUT_ROOT / "llm-forfiles-portable"

INCLUDES = [
    "backend",
    "frontend/dist",
    "launcher",
    "scripts/launcher.py",
    "pyproject.toml",
    "README.md",
    "AGENTS.md",
]


def main() -> None:
    build_frontend()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    for item in INCLUDES:
        source = ROOT / item
        target = OUT / item
        if not source.exists():
            raise RuntimeError(f"Nao encontrado para empacotar: {source}")
        if source.is_dir():
            shutil.copytree(source, target, ignore=ignore_patterns)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    create_start_scripts()
    print(f"Pacote portatil criado em: {OUT}")


def build_frontend() -> None:
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm nao encontrado. Instale Node/NPM nesta maquina para gerar o bundle portatil.")
    subprocess.run([npm, "install"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)


def ignore_patterns(_dir: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".local_data"}
    return {name for name in names if name in ignored or name.endswith(".pyc")}


def create_start_scripts() -> None:
    linux = OUT / "start.sh"
    linux.write_text("#!/usr/bin/env sh\ncd \"$(dirname \"$0\")\"\npython3 scripts/launcher.py\n", encoding="utf-8")
    linux.chmod(0o755)

    windows = OUT / "start.bat"
    windows.write_text(
        "\n".join(
            [
                "@echo off",
                "cd /d %~dp0",
                "",
                'powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force" >nul 2>nul',
                "",
                "py -3 --version >nul 2>nul",
                "if errorlevel 1 (",
                "  winget --version >nul 2>nul",
                "  if not errorlevel 1 (",
                "    echo Instalando Python 3.12 via winget...",
                "    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent",
                "  )",
                "",
                "  echo Configurando Python padrao no Windows...",
                "  py install default",
                ")",
                "",
                "py -3 --version >nul 2>nul",
                "if errorlevel 1 (",
                "  python --version >nul 2>nul",
                "  if errorlevel 1 (",
                "    echo Nao foi possivel configurar o Python padrao. Instale o Python 3 e tente novamente.",
                "    pause",
                "    exit /b 1",
                "  )",
                "  python scripts\\launcher.py",
                ") else (",
                "  py scripts\\launcher.py",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
