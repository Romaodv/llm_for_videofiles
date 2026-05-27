from typing import Literal

from pydantic import BaseModel, Field

WhisperModelName = Literal["tiny", "base", "small", "medium", "large-v3"]
TranscriptionProvider = Literal["local", "groq"]
LLMProviderName = Literal["deepseek", "groq"]
GroqLLMModelName = Literal["meta-llama/llama-4-scout-17b-16e-instruct", "groq/compound-mini"]


class IndexVideoRequest(BaseModel):
    path: str
    reindex: bool = False
    transcribe: bool = True
    category: str = "Sem categoria"
    transcription_provider: TranscriptionProvider = "local"
    whisper_cpu_threads: int | None = Field(default=None, ge=0, le=64)
    whisper_model: WhisperModelName | None = None


class SaveDocumentRequest(BaseModel):
    category: str = "Sem categoria"
    notes: str = ""


class SaveSecretRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=300)


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class AskRequest(BaseModel):
    question: str
    document_id: int | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    mode: Literal["cloud"] = "cloud"
    llm_provider: LLMProviderName = "deepseek"
    groq_llm_model: GroqLLMModelName | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=8)
    cloud_api_key: str | None = Field(default=None, max_length=300)


class SearchRequest(BaseModel):
    query: str
    document_id: int | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class FileListResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[dict]
