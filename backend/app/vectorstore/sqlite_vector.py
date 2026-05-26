import json
import math
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchHit:
    chunk_id: int
    document_id: int
    file_name: str
    source_path: str
    start_seconds: float
    end_seconds: float
    text: str
    score: float


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SqliteVectorStore:
    """Tiny local vector store backed by SQLite rows.

    Purpose: keep the MVP dependency-light and inspectable. Flow: query vector
    is compared locally against stored JSON vectors. Responsibilities: top-k
    retrieval only; no LLM behavior belongs here.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def search(self, query_vector: list[float], top_k: int, document_id: int | None = None) -> list[SearchHit]:
        params: list[object] = []
        where = ""
        if document_id is not None:
            where = "WHERE c.document_id = ?"
            params.append(document_id)

        rows = self.conn.execute(
            f"""
            SELECT c.id, c.document_id, c.start_seconds, c.end_seconds, c.text, c.embedding,
                   d.file_name, d.source_path
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            {where}
            """,
            params,
        ).fetchall()

        hits: list[SearchHit] = []
        for row in rows:
            score = cosine_similarity(query_vector, json.loads(row["embedding"]))
            hits.append(
                SearchHit(
                    chunk_id=row["id"],
                    document_id=row["document_id"],
                    file_name=row["file_name"],
                    source_path=row["source_path"],
                    start_seconds=row["start_seconds"],
                    end_seconds=row["end_seconds"],
                    text=row["text"],
                    score=score,
                )
            )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]
