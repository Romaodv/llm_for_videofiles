from __future__ import annotations

from datetime import datetime, timezone

from backend.app.db.sqlite import get_connection
from backend.app.llm.providers import get_topic_provider


def summarize_document_topics(
    document_id: int,
    window_seconds: int = 900,
    provider_name: str | None = None,
    provider_model: str | None = None,
    summary_strategy: str = "auto",
) -> list[dict]:
    cues = load_cues(document_id)
    provider = get_topic_provider(provider_name, provider_model)
    if summary_strategy == "chunked":
        topic_lines = summarize_topics_by_windows(provider, cues, window_seconds)
    elif summary_strategy == "full":
        topic_lines = summarize_topics_full_transcript(provider, cues)
    else:
        try:
            topic_lines = summarize_topics_full_transcript(provider, cues)
        except RuntimeError:
            topic_lines = summarize_topics_by_windows(provider, cues, window_seconds)

    with get_connection() as conn:
        conn.execute("DELETE FROM topics WHERE document_id = ?", (document_id,))
        for line in topic_lines:
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 3:
                continue
            start = parse_topic_seconds(parts[0])
            title = clean_text(parts[1], 120)
            summary = clean_text(parts[2], 500)
            if not title or not summary:
                continue
            conn.execute(
                """
                INSERT INTO topics (document_id, start_seconds, end_seconds, title, summary)
                VALUES (?, ?, ?, ?, ?)
                """,
                (document_id, start, start + 90, title, summary),
            )
        return load_topics(conn, document_id)


def summarize_document_presentation(
    document_id: int,
    provider_name: str | None = None,
    provider_model: str | None = None,
    summary_strategy: str = "auto",
) -> dict:
    with get_connection() as conn:
        topics = load_topics(conn, document_id)
    if not topics:
        topics = summarize_document_topics(
            document_id,
            provider_name=provider_name,
            provider_model=provider_model,
            summary_strategy=summary_strategy,
        )

    topic_text = "\n".join(
        f"{format_seconds(topic['start_seconds'])} ({topic['start_seconds']:.1f}s) | {topic['title']} | {topic['summary']}"
        for topic in topics
    )
    provider = get_topic_provider(provider_name, provider_model)
    markdown = provider.summarize_presentation(topic_text).strip()
    if not markdown:
        raise RuntimeError(f"{provider.name} nao retornou resumo da apresentacao.")
    markdown = ensure_summary_time_links(markdown, topics)
    saved = save_document_summary(document_id, markdown, provider.name, provider.model)
    return {"markdown": markdown, "topics": topics, **saved}


def get_document_summary(document_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT markdown, provider, model, generated_at
            FROM document_summaries
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()
    if not row:
        return {"markdown": "", "provider": "", "model": "", "generated_at": ""}
    return dict(row)


def save_document_summary(document_id: int, markdown: str, provider: str, model: str) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO document_summaries (document_id, markdown, provider, model, generated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                markdown = excluded.markdown,
                provider = excluded.provider,
                model = excluded.model,
                generated_at = excluded.generated_at
            """,
            (document_id, markdown, provider, model, generated_at),
        )
    return {"provider": provider, "model": model, "generated_at": generated_at}


def load_cues(document_id: int) -> list:
    with get_connection() as conn:
        cues = conn.execute(
            """
            SELECT start_seconds, end_seconds, text
            FROM transcript_cues
            WHERE document_id = ?
            ORDER BY cue_index
            """,
            (document_id,),
        ).fetchall()
        if not cues:
            raise FileNotFoundError("Transcript nao encontrado")
        return list(cues)


def load_topics(conn, document_id: int) -> list[dict]:
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


def summarize_topics_full_transcript(provider, cues) -> list[str]:
    raw = summarize_topics_with_compaction(provider, cues)
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"{provider.name} nao retornou topicos.")
    return lines


def summarize_topics_with_compaction(provider, cues) -> str:
    attempts = [
        compact_cues(cues, block_seconds=45),
        compact_cues(cues, block_seconds=120),
        compact_cues(cues, block_seconds=240),
    ]
    last_error: RuntimeError | None = None
    for transcript_text in attempts:
        try:
            return provider.summarize_topics(transcript_text)
        except RuntimeError as exc:
            last_error = exc
            if "413" not in str(exc) and "Payload Too Large" not in str(exc):
                raise
    raise RuntimeError(
        "Groq recusou o transcript inteiro por tamanho de payload mesmo em formato compacto. "
        "Para manter 100% do SRT em uma unica chamada, sera necessario usar um provider com limite de payload maior."
    ) from last_error


def summarize_topics_by_windows(provider, cues, window_seconds: int) -> list[str]:
    topic_lines: list[str] = []
    for window in split_cues_by_time(cues, window_seconds):
        raw = provider.summarize_topics(compact_cues(window, block_seconds=45))
        topic_lines.extend(line.strip() for line in raw.splitlines() if line.strip())
    if not topic_lines:
        raise RuntimeError(f"{provider.name} nao retornou topicos.")
    return topic_lines


def compact_cues(cues, block_seconds: int = 45) -> str:
    blocks: list[str] = []
    block_start = float(cues[0]["start_seconds"])
    block_end = float(cues[0]["end_seconds"])
    parts: list[str] = []

    for row in cues:
        start = float(row["start_seconds"])
        end = float(row["end_seconds"])
        if parts and start - block_start >= block_seconds:
            blocks.append(format_compact_block(block_start, block_end, parts))
            block_start = start
            parts = []
        block_end = end
        text = clean_text(row["text"], 1000)
        if text:
            parts.append(text)

    if parts:
        blocks.append(format_compact_block(block_start, block_end, parts))

    return "\n".join(blocks)


def format_compact_block(start: float, end: float, parts: list[str]) -> str:
    return f"[{format_seconds(start)}-{format_seconds(end)}] {' '.join(parts)}"


def ensure_summary_time_links(markdown: str, topics: list[dict]) -> str:
    if "#t=" in markdown or not topics:
        return markdown

    lines = markdown.splitlines()
    result: list[str] = []
    paragraph_index = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-") or stripped.startswith("*"):
            result.append(line)
            continue
        topic = topics[min(paragraph_index, len(topics) - 1)]
        seconds = float(topic["start_seconds"])
        result.append(f"[{format_seconds(seconds)}](#t={int(seconds)}) {line}")
        paragraph_index += 1
    return "\n".join(result)


def split_cues_by_time(cues, window_seconds: int) -> list[list]:
    windows: list[list] = []
    current: list = []
    start = float(cues[0]["start_seconds"])
    for cue in cues:
        if current and float(cue["start_seconds"]) - start >= window_seconds:
            windows.append(current)
            current = []
            start = float(cue["start_seconds"])
        current.append(cue)
    if current:
        windows.append(current)
    return windows


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


def clean_text(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit].strip(" -")


def format_seconds(value: float) -> str:
    total = int(value)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"
