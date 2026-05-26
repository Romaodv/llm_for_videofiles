from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import uuid4


@dataclass
class JobState:
    id: str
    kind: str
    status: str = "queued"
    phase: str = "queued"
    percent: float = 0.0
    message: str = "Aguardando processamento"
    detail: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    logs: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: now_iso())
    updated_at: str = field(default_factory=lambda: now_iso())


ProgressCallback = Callable[[str, float, str, str], None]


class JobRegistry:
    """Small in-memory progress registry for local MVP jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = Lock()

    def create(self, kind: str) -> JobState:
        job = JobState(id=str(uuid4()), kind=kind)
        with self._lock:
            self._jobs[job.id] = job
        self.update(job.id, "queued", 0, "Job criado", "Aguardando worker iniciar")
        return job

    def update(self, job_id: str, phase: str, percent: float, message: str, detail: str = "") -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running" if job.status in {"queued", "running"} else job.status
            job.phase = phase
            job.percent = max(0.0, min(100.0, round(percent, 2)))
            job.message = message
            job.detail = detail
            job.updated_at = now_iso()
            job.logs.append(
                {
                    "time": job.updated_at,
                    "phase": phase,
                    "percent": job.percent,
                    "message": message,
                    "detail": detail,
                }
            )
            job.logs = job.logs[-120:]

    def finish(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "completed"
            job.phase = "completed"
            job.percent = 100.0
            job.message = "Processamento concluido"
            job.detail = "Dados salvos no SQLite local"
            job.result = result
            job.updated_at = now_iso()
            job.logs.append(
                {
                    "time": job.updated_at,
                    "phase": job.phase,
                    "percent": job.percent,
                    "message": job.message,
                    "detail": job.detail,
                }
            )

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.phase = "failed"
            job.message = "Falha no processamento"
            job.detail = error
            job.error = error
            job.updated_at = now_iso()
            job.logs.append(
                {
                    "time": job.updated_at,
                    "phase": job.phase,
                    "percent": job.percent,
                    "message": job.message,
                    "detail": error,
                }
            )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return {
                "id": job.id,
                "kind": job.kind,
                "status": job.status,
                "phase": job.phase,
                "percent": job.percent,
                "message": job.message,
                "detail": job.detail,
                "result": job.result,
                "error": job.error,
                "logs": list(job.logs),
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


jobs = JobRegistry()
