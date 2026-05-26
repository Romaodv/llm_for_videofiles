from pathlib import Path

from backend.app.config import settings
from backend.app.parsers.srt import SrtCue, cues_to_srt
from backend.app.services.progress import ProgressCallback


class TranscriptionService:
    """Whisper transcription boundary.

    Purpose: isolate the heavy optional dependency. Flow: video path in, SRT
    path plus cues out. Responsibilities: model loading and SRT timestamp
    generation only.
    """

    def transcribe_to_srt(self, video_path: Path, progress: ProgressCallback | None = None) -> tuple[Path, list[SrtCue]]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper nao esta instalado. Rode `python -m pip install -e .` "
                "e confirme que ffmpeg esta disponivel no PATH."
            ) from exc

        settings.ensure_dirs()
        if progress:
            progress("whisper_model", 12, "Carregando Whisper", f"modelo={settings.whisper_model}, device={settings.whisper_device}, compute={settings.whisper_compute_type}")
        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        if progress:
            progress("transcription", 18, "Iniciando transcricao", "Extraindo fala e timestamps com faster-whisper")
        segments, info = model.transcribe(str(video_path), vad_filter=True)
        duration = float(getattr(info, "duration", 0) or 0)

        cues: list[SrtCue] = []
        for index, segment in enumerate(segments, start=1):
            text = segment.text.strip()
            if not text:
                continue
            cues.append(
                SrtCue(
                    index=index,
                    start_seconds=float(segment.start),
                    end_seconds=float(segment.end),
                    text=text,
                )
            )
            if progress:
                local_percent = 20 + (float(segment.end) / duration * 34 if duration else min(index, 100) / 100 * 34)
                progress(
                    "transcription",
                    local_percent,
                    "Transcrevendo audio",
                    f"{index} legendas geradas, ultimo timestamp {float(segment.end):.1f}s",
                )

        if progress:
            progress("srt", 56, "Gravando SRT", f"{len(cues)} legendas com timestamps preservados")
        srt_path = settings.transcript_dir / f"{video_path.stem}.srt"
        srt_path.write_text(cues_to_srt(cues), encoding="utf-8")
        if progress:
            progress("srt", 58, "SRT salvo", str(srt_path))
        return srt_path, cues
