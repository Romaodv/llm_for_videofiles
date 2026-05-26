from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router
from backend.app.db.sqlite import init_db

app = FastAPI(title="LLM Forfiles Video RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


app.include_router(router)


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
assets_dir = frontend_dist / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")


@app.get("/")
@app.get("/app")
def frontend_index() -> FileResponse:
    index_path = frontend_dist / "index.html"
    if not index_path.exists():
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="Frontend build nao encontrado. Rode npm run build em frontend/ ou use scripts/build_portable.py.",
        )
    return FileResponse(index_path)
