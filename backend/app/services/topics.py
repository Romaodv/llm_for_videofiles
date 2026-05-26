from __future__ import annotations

from backend.app.db.sqlite import get_connection
from backend.app.llm.providers import get_topic_provider


def summarize_document_topics_local(document_id: int, window_seconds: int = 600) -> list[dict]:
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

    provider = get_topic_provider()
    topic_lines: list[str] = []
    for window in split_cues_by_time(cues, window_seconds):
        transcript_text = "\n".join(
            f"{row['start_seconds']:.1f}s | {row['text']}"
            for row in window
        )
        try:
            raw = provider.summarize_topics(transcript_text)
        except Exception:
            raw = ""
        if raw.strip():
            topic_lines.extend(line.strip() for line in raw.splitlines() if line.strip())
        else:
            first = window[0]
            topic_lines.append(f"{first['start_seconds']:.1f}s | Trecho {format_seconds(first['start_seconds'])} | {first['text'][:180]}")

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
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02}"
