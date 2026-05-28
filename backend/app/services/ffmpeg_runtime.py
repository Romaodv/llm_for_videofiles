import os
import shutil
from pathlib import Path

from backend.app.config import settings


def resolve_ffmpeg() -> str:
    ffmpeg = _resolve_binary("ffmpeg", env_var="LLM_FORFILES_FFMPEG_BIN")
    if ffmpeg:
        return ffmpeg
    raise RuntimeError(
        "ffmpeg nao encontrado. Instale o FFmpeg, adicione ao PATH, ou defina "
        "LLM_FORFILES_FFMPEG_BIN com o caminho completo do ffmpeg.exe. "
        "No Windows, um caminho comum e instalar com `winget install -e --id Gyan.FFmpeg.Essentials`."
    )


def resolve_ffprobe() -> str | None:
    ffprobe = _resolve_binary("ffprobe", env_var="LLM_FORFILES_FFPROBE_BIN")
    if ffprobe:
        return ffprobe

    ffmpeg = _resolve_binary("ffmpeg", env_var="LLM_FORFILES_FFMPEG_BIN")
    if not ffmpeg:
        return None

    sibling = Path(ffmpeg).with_name(f"ffprobe{_binary_suffix()}")
    if sibling.exists():
        return str(sibling)
    return None


def _resolve_binary(name: str, env_var: str) -> str | None:
    env_value = os.getenv(env_var, "").strip()
    if env_value:
        candidate = Path(env_value).expanduser()
        if candidate.exists():
            return str(candidate.resolve())

    existing = shutil.which(name)
    if existing:
        return existing

    for candidate in _iter_local_candidates(name):
        if candidate.exists():
            return str(candidate.resolve())

    if os.name == "nt":
        return _find_windows_binary(name)
    return None


def _iter_local_candidates(name: str):
    suffix = _binary_suffix()
    file_name = f"{name}{suffix}"
    project_root = Path(__file__).resolve().parents[3]
    user_root = settings.data_dir.parent

    yield project_root / ".local_tools" / "ffmpeg" / "bin" / file_name
    yield project_root / "vendor" / "ffmpeg" / "bin" / file_name
    yield user_root / "tools" / "ffmpeg" / "bin" / file_name
    yield user_root / ".local_tools" / "ffmpeg" / "bin" / file_name
    yield user_root / "ffmpeg" / "bin" / file_name


def _find_windows_binary(name: str) -> str | None:
    file_name = f"{name}.exe"
    candidates: list[Path] = []

    for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        root_value = os.getenv(env_name, "").strip()
        if not root_value:
            continue
        root = Path(root_value)
        if not root.exists():
            continue
        candidates.extend(root.glob(f"Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/{file_name}"))
        candidates.extend(root.glob(f"ffmpeg*/**/{file_name}"))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return None


def _binary_suffix() -> str:
    return ".exe" if os.name == "nt" else ""
