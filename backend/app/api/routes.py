from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from backend.app.api.schemas import AskRequest, FileListResponse, IndexVideoRequest, SaveDocumentRequest, SaveSecretRequest, SearchRequest
from backend.app.db.sqlite import get_connection
from backend.app.embeddings.providers import get_embedding_provider
from backend.app.llm.providers import get_llm_provider
from backend.app.services.indexing import IndexingService
from backend.app.services.progress import jobs
from backend.app.services.secrets import PROVIDER_DEEPSEEK, delete_secret, save_secret, secret_status
from backend.app.services.topics import summarize_document_topics_local
from backend.app.services.video_media import build_web_video, get_playable_video_path
from backend.app.vectorstore.sqlite_vector import SqliteVectorStore

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "llm-forfiles"}


@router.get("/files/list", response_model=FileListResponse)
def list_files(path: str | None = None) -> dict:
    current = Path(path or Path.home()).expanduser().resolve()
    if not current.exists() or not current.is_dir():
        raise HTTPException(status_code=404, detail=f"Diretorio nao encontrado: {current}")

    entries = []
    for entry in sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if entry.name.startswith("."):
            continue
        entries.append(
            {
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            }
        )
    parent = str(current.parent) if current.parent != current else None
    return {"path": str(current), "parent": parent, "entries": entries}


@router.post("/videos/index")
def index_video(request: IndexVideoRequest) -> dict:
    try:
        return IndexingService().index_video(Path(request.path), request.reindex, request.transcribe, request.category)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/videos/index/jobs")
def start_index_video_job(request: IndexVideoRequest) -> dict:
    job = jobs.create("video_index")

    def run() -> None:
        try:
            result = IndexingService().index_video(
                Path(request.path),
                request.reindex,
                request.transcribe,
                request.category,
                progress=lambda phase, percent, message, detail="": jobs.update(job.id, phase, percent, message, detail),
            )
            jobs.finish(job.id, result)
        except Exception as exc:  # noqa: BLE001 - expose clear job failure to local UI.
            jobs.fail(job.id, str(exc))

    Thread(target=run, daemon=True).start()
    return {"job_id": job.id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    return job


@router.get("/settings/secrets/deepseek")
def get_deepseek_secret_status() -> dict:
    return secret_status(PROVIDER_DEEPSEEK)


@router.post("/settings/secrets/deepseek")
def save_deepseek_secret(request: SaveSecretRequest) -> dict:
    try:
        return save_secret(PROVIDER_DEEPSEEK, request.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/settings/secrets/deepseek")
def delete_deepseek_secret() -> dict:
    return delete_secret(PROVIDER_DEEPSEEK)


@router.get("/documents")
def list_documents() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, source_path, transcript_path, web_video_path, file_name, duration_seconds, indexed_at,
                   saved_at, category, notes, embedding_provider, embedding_model, chunk_count
            FROM documents
            ORDER BY category, indexed_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


@router.get("/documents/{document_id}")
def get_document(document_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Documento nao encontrado")
        return dict(row)


@router.put("/documents/{document_id}/save")
def save_document(document_id: int, request: SaveDocumentRequest) -> dict:
    category = request.category.strip() or "Sem categoria"
    saved_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Documento nao encontrado")
        conn.execute(
            """
            UPDATE documents
            SET category = ?, notes = ?, saved_at = ?
            WHERE id = ?
            """,
            (category, request.notes.strip(), saved_at, document_id),
        )
        updated = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return dict(updated)


@router.get("/documents/{document_id}/transcript")
def get_transcript(document_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT cue_index, start_seconds, end_seconds, text
            FROM transcript_cues
            WHERE document_id = ?
            ORDER BY cue_index
            """,
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]


@router.get("/documents/{document_id}/srt", response_class=PlainTextResponse)
def get_srt(document_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT transcript_path FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Documento nao encontrado")
        return Path(row["transcript_path"]).read_text(encoding="utf-8")


@router.get("/documents/{document_id}/topics")
def get_topics(document_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, start_seconds, end_seconds, title, summary
            FROM topics
            WHERE document_id = ?
            ORDER BY start_seconds
            """,
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]


@router.post("/documents/{document_id}/topics/summarize")
def summarize_topics(document_id: int) -> list[dict]:
    try:
        return summarize_document_topics_local(document_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.post("/documents/{document_id}/media/jobs")
def start_web_media_job(document_id: int) -> dict:
    job = jobs.create("web_media")

    def run() -> None:
        try:
            result = build_web_video(
                document_id,
                progress=lambda phase, percent, message, detail="": jobs.update(job.id, phase, percent, message, detail),
            )
            jobs.finish(job.id, result)
        except Exception as exc:  # noqa: BLE001 - expose local conversion errors to UI.
            jobs.fail(job.id, str(exc))

    Thread(target=run, daemon=True).start()
    return {"job_id": job.id}


@router.get("/documents/{document_id}/media")
def document_media(document_id: int) -> FileResponse:
    try:
        video_path = get_playable_video_path(document_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(video_path)


@router.post("/search/semantic")
def semantic_search(request: SearchRequest) -> list[dict]:
    provider = get_embedding_provider()
    query_vector = provider.embed(request.query)
    with get_connection() as conn:
        hits = SqliteVectorStore(conn).search(query_vector, request.top_k, request.document_id)
        return [hit.__dict__ for hit in hits]


@router.post("/search/ask")
def ask(request: AskRequest) -> dict:
    provider = get_embedding_provider()
    query_vector = provider.embed(request.question)
    with get_connection() as conn:
        hits = SqliteVectorStore(conn).search(query_vector, request.top_k, request.document_id)
    history = [item.model_dump() for item in request.history[-8:]]
    answer = get_llm_provider(request.mode).answer(request.question, hits, history, request.cloud_api_key)
    return {"answer": answer, "sources": [hit.__dict__ for hit in hits], "mode": request.mode}


@router.get("/media")
def media(path: str = Query(...)) -> FileResponse:
    video_path = Path(path).expanduser().resolve()
    if not video_path.exists() or not video_path.is_file():
        raise HTTPException(status_code=404, detail=f"Arquivo nao encontrado: {video_path}")
    return FileResponse(video_path)


def parse_topic_seconds(value: str) -> float:
    cleaned = value.lower().replace("s", "").strip()
    if ":" not in cleaned:
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    parts = [float(part) for part in cleaned.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0.0
