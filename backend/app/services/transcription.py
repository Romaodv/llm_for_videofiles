from pathlib import Path
from threading import Event, Lock, Thread
import math
import subprocess
import tempfile
import time

import httpx

from backend.app.config import settings
from backend.app.parsers.srt import SrtCue, cues_to_srt
from backend.app.services.ffmpeg_runtime import resolve_ffmpeg, resolve_ffprobe
from backend.app.services.progress import ProgressCallback
from backend.app.services.secrets import PROVIDER_GROQ, get_secret


class TranscriptionService:
    """Whisper transcription boundary.

    Purpose: isolate the heavy optional dependency. Flow: video path in, SRT
    path plus cues out. Responsibilities: model loading and SRT timestamp
    generation only.
    """

    def transcribe_to_srt(
        self,
        video_path: Path,
        progress: ProgressCallback | None = None,
        cpu_threads: int | None = None,
        model_name: str | None = None,
        provider: str = "local",
    ) -> tuple[Path, list[SrtCue]]:
        if provider == "groq":
            return self._transcribe_with_groq(video_path, progress)
        if provider != "local":
            raise RuntimeError(f"Provider de transcricao desconhecido: {provider}")

        return self._transcribe_with_local_whisper(video_path, progress, cpu_threads, model_name)

    def _transcribe_with_local_whisper(
        self,
        video_path: Path,
        progress: ProgressCallback | None,
        cpu_threads: int | None,
        model_name: str | None,
    ) -> tuple[Path, list[SrtCue]]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper nao esta instalado. Rode `python -m pip install -e .` "
                "e confirme que ffmpeg esta disponivel no PATH."
            ) from exc

        settings.ensure_dirs()
        effective_cpu_threads = settings.whisper_cpu_threads if cpu_threads is None else cpu_threads
        effective_model = model_name or settings.whisper_model
        threads_label = effective_cpu_threads if effective_cpu_threads > 0 else "auto"
        heartbeat = TranscriptionHeartbeat(
            progress,
            percent=12,
            detail=f"Carregando modelo Whisper com threads={threads_label}",
        )
        heartbeat.start()
        cues: list[SrtCue] = []
        try:
            if progress:
                progress(
                    "whisper_model",
                    12,
                    "Carregando Whisper",
                    f"modelo={effective_model}, device={settings.whisper_device}, compute={settings.whisper_compute_type}, threads={threads_label}",
                )
            model = WhisperModel(
                effective_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
                cpu_threads=effective_cpu_threads,
            )
            heartbeat.update(18, "Modelo carregado; preparando audio e VAD")
            if progress:
                progress("transcription", 18, "Iniciando transcricao", "Extraindo fala e timestamps com faster-whisper")
            segments, info = model.transcribe(
                str(video_path),
                vad_filter=True,
                beam_size=1,
                condition_on_previous_text=False,
            )
            duration = float(getattr(info, "duration", 0) or 0)
            heartbeat.update(20, f"Audio preparado; duracao detectada {duration:.1f}s")

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
                local_percent = 20 + (float(segment.end) / duration * 34 if duration else min(index, 100) / 100 * 34)
                detail = f"{index} legendas geradas, ultimo timestamp {float(segment.end):.1f}s"
                heartbeat.update(local_percent, detail)
                if progress:
                    progress(
                        "transcription",
                        local_percent,
                        "Transcrevendo audio",
                        detail,
                    )
        finally:
            heartbeat.stop()

        if progress:
            progress("srt", 56, "Gravando SRT", f"{len(cues)} legendas com timestamps preservados")
        srt_path = settings.transcript_dir / f"{video_path.stem}.srt"
        srt_path.write_text(cues_to_srt(cues), encoding="utf-8")
        if progress:
            progress("srt", 58, "SRT salvo", str(srt_path))
        return srt_path, cues

    def _transcribe_with_groq(
        self,
        video_path: Path,
        progress: ProgressCallback | None = None,
    ) -> tuple[Path, list[SrtCue]]:
        api_key = (settings.groq_api_key or get_secret(PROVIDER_GROQ) or "").strip()
        if not api_key:
            raise RuntimeError("Groq API key nao configurada. Abra Config e salve a GROQ_API_KEY.")

        ffmpeg = resolve_ffmpeg()

        settings.ensure_dirs()
        if progress:
            progress("groq_audio", 12, "Preparando audio para Groq", "Convertendo para MP3 mono 16 kHz abaixo de 25 MB")

        with tempfile.TemporaryDirectory(prefix="llm_forfiles_groq_") as temp_dir:
            temp_root = Path(temp_dir)
            audio_path = temp_root / f"{video_path.stem}.mp3"
            self._compress_audio_for_groq(ffmpeg, video_path, audio_path)
            audio_parts = [audio_path]

            if audio_path.stat().st_size > settings.groq_max_upload_bytes:
                if progress:
                    progress("groq_audio", 18, "Dividindo audio comprimido", "Arquivo ainda passou de 25 MB; criando partes menores")
                audio_parts = self._split_audio_for_groq(ffmpeg, audio_path, temp_root)

            total_parts = len(audio_parts)
            cues: list[SrtCue] = []
            offset_seconds = 0.0
            for part_index, part_path in enumerate(audio_parts, start=1):
                size_mb = part_path.stat().st_size / (1024 * 1024)
                if size_mb > 25:
                    raise RuntimeError(f"Parte comprimida ainda excede 25 MB: {part_path.name} ({size_mb:.1f} MB)")
                if progress:
                    progress(
                        "groq",
                        20 + (part_index - 1) / max(1, total_parts) * 34,
                        "Transcrevendo via Groq",
                        f"parte {part_index}/{total_parts}, {size_mb:.1f} MB",
                    )
                part_cues, part_duration = self._request_groq_transcription(part_path, api_key, offset_seconds)
                cues.extend(part_cues)
                offset_seconds += part_duration

            cues = [
                SrtCue(index=index, start_seconds=cue.start_seconds, end_seconds=cue.end_seconds, text=cue.text)
                for index, cue in enumerate(cues, start=1)
            ]

        if progress:
            progress("srt", 56, "Gravando SRT", f"{len(cues)} legendas retornadas pela Groq")
        srt_path = settings.transcript_dir / f"{video_path.stem}.srt"
        srt_path.write_text(cues_to_srt(cues), encoding="utf-8")
        if progress:
            progress("srt", 58, "SRT salvo", str(srt_path))
        return srt_path, cues

    def _compress_audio_for_groq(self, ffmpeg: str, source_path: Path, audio_path: Path) -> None:
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-map",
            "0:a:0",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "32k",
            str(audio_path),
        ]
        self._run_ffmpeg(command, "ffmpeg falhou ao comprimir audio para Groq")

    def _split_audio_for_groq(self, ffmpeg: str, audio_path: Path, temp_root: Path) -> list[Path]:
        duration = self._probe_duration(audio_path)
        if duration <= 0:
            raise RuntimeError("Nao foi possivel detectar a duracao do audio comprimido para dividir em partes.")

        size = audio_path.stat().st_size
        target_bytes = int(settings.groq_max_upload_bytes * 0.9)
        part_count = max(2, math.ceil(size / target_bytes))
        segment_seconds = max(60, math.floor(duration / part_count))
        parts_dir = temp_root / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        pattern = parts_dir / "part_%03d.mp3"
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(audio_path),
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-c",
            "copy",
            str(pattern),
        ]
        self._run_ffmpeg(command, "ffmpeg falhou ao dividir audio para Groq")
        parts = sorted(parts_dir.glob("part_*.mp3"))
        if not parts:
            raise RuntimeError("ffmpeg nao gerou partes de audio para envio a Groq.")
        return parts

    def _request_groq_transcription(self, audio_path: Path, api_key: str, offset_seconds: float) -> tuple[list[SrtCue], float]:
        data = {
            "model": settings.groq_whisper_model,
            "response_format": "verbose_json",
            "temperature": "0",
        }
        if settings.groq_transcription_language:
            data["language"] = settings.groq_transcription_language

        with audio_path.open("rb") as file:
            response = httpx.post(
                f"{settings.groq_base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files={"file": (audio_path.name, file, "audio/mpeg")},
                timeout=600,
            )
        if response.status_code >= 400:
            detail = response.text[:1200]
            raise RuntimeError(f"Groq falhou na transcricao ({response.status_code}): {detail}")

        payload = response.json()
        segments = payload.get("segments") or []
        cues: list[SrtCue] = []
        for index, segment in enumerate(segments, start=1):
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            start = float(segment.get("start") or 0) + offset_seconds
            end = float(segment.get("end") or start) + offset_seconds
            cues.append(SrtCue(index=index, start_seconds=start, end_seconds=end, text=text))

        duration = float(payload.get("duration") or 0)
        if duration <= 0:
            duration = self._probe_duration(audio_path)
        if not cues:
            text = str(payload.get("text") or "").strip()
            if text:
                cues.append(SrtCue(index=1, start_seconds=offset_seconds, end_seconds=offset_seconds + duration, text=text))
        return cues, duration

    def _probe_duration(self, path: Path) -> float:
        ffprobe = resolve_ffprobe()
        if not ffprobe:
            return 0.0
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 0.0

    def _run_ffmpeg(self, command: list[str], error_message: str) -> None:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"{error_message}: {result.stderr[-1200:]}")


class TranscriptionHeartbeat:
    def __init__(
        self,
        progress: ProgressCallback | None,
        interval_seconds: int = 8,
        percent: float = 18.0,
        detail: str = "Aguardando primeira legenda do Whisper",
    ) -> None:
        self.progress = progress
        self.interval_seconds = interval_seconds
        self.done = Event()
        self.lock = Lock()
        self.percent = percent
        self.detail = detail
        self.started_at = time.monotonic()
        self.thread: Thread | None = None

    def start(self) -> None:
        if not self.progress:
            return
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()

    def update(self, percent: float, detail: str) -> None:
        with self.lock:
            self.percent = max(self.percent, min(55.0, percent))
            self.detail = detail

    def stop(self) -> None:
        self.done.set()
        if self.thread:
            self.thread.join(timeout=1)

    def _run(self) -> None:
        assert self.progress is not None
        while not self.done.wait(self.interval_seconds):
            elapsed = int(time.monotonic() - self.started_at)
            with self.lock:
                percent = self.percent
                detail = self.detail
            self.progress(
                "transcription",
                percent,
                "Whisper ainda processando",
                f"{detail} · {elapsed}s sem concluir a etapa",
            )
