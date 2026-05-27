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

        self.embedding_provider = "hashing"

        self.llm_provider = "deepseek"
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        self.groq_whisper_model = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
        self.groq_llm_model = os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        self.groq_transcription_language = os.getenv("GROQ_TRANSCRIPTION_LANGUAGE", "")
        self.groq_max_upload_bytes = int(os.getenv("GROQ_MAX_UPLOAD_BYTES", str(24 * 1024 * 1024)))

        self.whisper_model = os.getenv("WHISPER_MODEL", "small")
        self.whisper_device = os.getenv("WHISPER_DEVICE", "cpu")
        self.whisper_compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        self.whisper_cpu_threads = int(os.getenv("WHISPER_CPU_THREADS", "2"))

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self.web_video_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
