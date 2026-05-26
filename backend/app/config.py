from pathlib import Path


class Settings:
    """Runtime settings read from environment variables.

    Purpose: keep providers replaceable without hiding configuration behind a
    framework. Flow: FastAPI services import this singleton and read explicit
    values. Responsibilities: paths, provider selection and external API knobs.
    """

    def __init__(self) -> None:
        import os

        self.data_dir = Path(os.getenv("LLM_FORFILES_DATA_DIR", ".local_data")).resolve()
        self.database_path = Path(os.getenv("LLM_FORFILES_DB", self.data_dir / "app.sqlite3")).resolve()
        self.transcript_dir = Path(os.getenv("LLM_FORFILES_TRANSCRIPT_DIR", self.data_dir / "transcripts")).resolve()
        self.web_video_dir = Path(os.getenv("LLM_FORFILES_WEB_VIDEO_DIR", self.data_dir / "web_videos")).resolve()
        self.secrets_path = Path(os.getenv("LLM_FORFILES_SECRETS", self.data_dir / "secrets.json")).resolve()
        self.secret_key_path = Path(os.getenv("LLM_FORFILES_SECRET_KEY_FILE", self.data_dir / "secret.key")).resolve()

        self.embedding_provider = os.getenv("EMBEDDING_PROVIDER", "hashing").lower()
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.ollama_embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        self.ollama_llm_model = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:3b")
        self.ollama_topic_model = os.getenv("OLLAMA_TOPIC_MODEL", "qwen2.5:3b")

        self.llm_provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

        self.whisper_model = os.getenv("WHISPER_MODEL", "small")
        self.whisper_device = os.getenv("WHISPER_DEVICE", "cpu")
        self.whisper_compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self.web_video_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
