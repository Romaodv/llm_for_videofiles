import json
from datetime import datetime, timezone
from pathlib import Path

from backend.app.db.sqlite import get_connection
from backend.app.embeddings.providers import get_embedding_provider
from backend.app.parsers.srt import SrtCue, chunk_cues, parse_srt
from backend.app.services.progress import ProgressCallback
from backend.app.services.transcription import TranscriptionService
from backend.app.utils.hashing import file_sha256


class IndexingService:
    """Manual video indexing workflow.

    Purpose: transcribe only when the user explicitly requests indexing. Flow:
    video -> SRT -> cues -> chunks -> embeddings -> SQLite. Responsibilities:
    persistence and clear reindex behavior.
    """

    def index_video(
        self,
        video_path: Path,
        reindex: bool = False,
        transcribe: bool = True,
        category: str = "Sem categoria",
        transcription_provider: str = "local",
        whisper_cpu_threads: int | None = None,
        whisper_model: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> dict:
        video_path = video_path.expanduser().resolve()
        if progress:
            progress("validate", 2, "Validando arquivo", str(video_path))
        if not video_path.exists():
            raise FileNotFoundError(f"Arquivo nao encontrado: {video_path}")

        if progress:
            progress("hash", 5, "Calculando hash do video", "Detectando se ja existe indexacao valida")
        file_hash = file_sha256(video_path)
        provider = get_embedding_provider()
        if progress:
            progress("provider", 8, "Preparando embeddings", f"provider={provider.name}, model={provider.model}")

        with get_connection() as conn:
            existing = conn.execute("SELECT * FROM documents WHERE source_path = ?", (str(video_path),)).fetchone()
            if existing and existing["file_hash"] == file_hash and not reindex:
                if progress:
                    progress("cache", 100, "Video ja indexado", "Hash igual; reutilizando embeddings, SRT, chunks e topicos salvos")
                return {"document_id": existing["id"], "status": "unchanged", "chunk_count": existing["chunk_count"]}

        if transcribe:
            transcript_path, cues = TranscriptionService().transcribe_to_srt(
                video_path,
                progress,
                whisper_cpu_threads,
                whisper_model,
                transcription_provider,
            )
        else:
            transcript_path = video_path.with_suffix(".srt")
            if not transcript_path.exists():
                raise FileNotFoundError(f"SRT nao encontrado ao lado do video: {transcript_path}")
            cues = parse_srt(transcript_path.read_text(encoding="utf-8"))
            if progress:
                progress("srt", 58, "SRT carregado", f"{len(cues)} legendas lidas de {transcript_path}")

        if progress:
            progress("chunking", 62, "Gerando chunks semanticos", f"{len(cues)} legendas de origem")
        chunks = chunk_cues(cues)
        if progress:
            progress("chunking", 66, "Chunks prontos", f"{len(chunks)} chunks com timestamps e overlap")
        indexed_at = datetime.now(timezone.utc).isoformat()

        with get_connection() as conn:
            if progress:
                progress("sqlite", 68, "Abrindo SQLite", "Removendo versao anterior do mesmo video, se existir")
            conn.execute("DELETE FROM documents WHERE source_path = ?", (str(video_path),))
            cursor = conn.execute(
                """
                INSERT INTO documents (
                    source_path, transcript_path, file_name, file_hash, duration_seconds,
                    indexed_at, saved_at, category, embedding_provider, embedding_model, chunk_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(video_path),
                    str(transcript_path),
                    video_path.name,
                    file_hash,
                    cues[-1].end_seconds if cues else 0,
                    indexed_at,
                    indexed_at,
                    clean_category(category),
                    provider.name,
                    provider.model,
                    len(chunks),
                ),
            )
            document_id = int(cursor.lastrowid)

            if progress:
                progress("sqlite", 72, "Salvando transcript", f"{len(cues)} linhas SRT vinculadas ao documento {document_id}")
            conn.executemany(
                """
                INSERT INTO transcript_cues (document_id, cue_index, start_seconds, end_seconds, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(document_id, cue.index, cue.start_seconds, cue.end_seconds, cue.text) for cue in cues],
            )

            total_chunks = max(1, len(chunks))
            for position, chunk in enumerate(chunks, start=1):
                if progress:
                    progress(
                        "embedding",
                        74 + (position - 1) / total_chunks * 18,
                        "Gerando embeddings",
                        f"chunk {position}/{len(chunks)} · {chunk.start_seconds:.1f}s-{chunk.end_seconds:.1f}s",
                    )
                embedding = provider.embed(chunk.text)
                conn.execute(
                    """
                    INSERT INTO chunks (document_id, chunk_index, start_seconds, end_seconds, text, embedding)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        chunk.index,
                        chunk.start_seconds,
                        chunk.end_seconds,
                        chunk.text,
                        json.dumps(embedding),
                    ),
                )

            conn.execute("DELETE FROM topics WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM document_summaries WHERE document_id = ?", (document_id,))
            if progress:
                progress("sqlite", 98, "Finalizando persistencia", "Embeddings, chunks e SRT salvos; topicos ficam sob demanda via DeepSeek")
            return {"document_id": document_id, "status": "indexed", "chunk_count": len(chunks)}


def clean_category(value: str) -> str:
    normalized = value.strip()
    return normalized or "Sem categoria"
