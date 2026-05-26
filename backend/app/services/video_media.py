import shutil
import subprocess
from pathlib import Path

from backend.app.config import settings
from backend.app.db.sqlite import get_connection
from backend.app.services.progress import ProgressCallback


def get_playable_video_path(document_id: int) -> Path:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT source_path, web_video_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not row:
            raise FileNotFoundError("Documento nao encontrado")

    web_path = Path(row["web_video_path"]) if row["web_video_path"] else None
    if web_path and web_path.exists():
        return web_path
    return Path(row["source_path"])


def build_web_video(document_id: int, progress: ProgressCallback | None = None) -> dict:
    settings.ensure_dirs()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, source_path, file_hash, duration_seconds, web_video_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not row:
            raise FileNotFoundError("Documento nao encontrado")

    source_path = Path(row["source_path"])
    if not source_path.exists():
        raise FileNotFoundError(f"Video original nao encontrado: {source_path}")

    output_path = settings.web_video_dir / f"document-{document_id}-{row['file_hash'][:12]}.mp4"
    if output_path.exists() and output_path.stat().st_size > 0:
        if progress:
            progress("cache", 100, "Versao web ja existe", str(output_path))
        save_web_path(document_id, output_path)
        return {"document_id": document_id, "web_video_path": str(output_path), "status": "unchanged"}

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg nao encontrado no PATH. Necessario para converter video para H.264/AAC.")

    temp_path = output_path.with_suffix(".tmp.mp4")
    if temp_path.exists():
        temp_path.unlink()

    duration = float(row["duration_seconds"] or 0)
    if progress:
        progress("ffmpeg", 3, "Preparando conversao web", "H.264 video + AAC audio para compatibilidade com browser")

    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
        str(temp_path),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None
    for line in process.stdout:
        key, _, value = line.strip().partition("=")
        if key == "out_time_ms" and progress:
            try:
                seconds = int(value) / 1_000_000
            except ValueError:
                seconds = 0
            percent = 8 + (seconds / duration * 88 if duration else 20)
            progress("ffmpeg", percent, "Convertendo video para browser", f"{seconds:.1f}s processados de {duration:.1f}s")
        elif key == "progress" and value == "end" and progress:
            progress("ffmpeg", 98, "Finalizando arquivo MP4", "Aplicando faststart e gravando caminho no SQLite")

    stderr = process.stderr.read() if process.stderr else ""
    code = process.wait()
    if code != 0:
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f"ffmpeg falhou ao converter video: {stderr[-1200:]}")

    temp_path.replace(output_path)
    save_web_path(document_id, output_path)
    if progress:
        progress("sqlite", 100, "Versao web salva", str(output_path))
    return {"document_id": document_id, "web_video_path": str(output_path), "status": "converted"}


def save_web_path(document_id: int, output_path: Path) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE documents SET web_video_path = ? WHERE id = ?",
            (str(output_path), document_id),
        )
