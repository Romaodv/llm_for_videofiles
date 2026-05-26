from abc import ABC, abstractmethod

import httpx

from backend.app.config import settings
from backend.app.services.secrets import PROVIDER_DEEPSEEK, get_secret
from backend.app.vectorstore.sqlite_vector import SearchHit


class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    def answer(
        self,
        question: str,
        hits: list[SearchHit],
        history: list[dict] | None = None,
        api_key: str | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def summarize_topics(self, transcript_text: str) -> str:
        raise NotImplementedError


class DeepSeekProvider(BaseLLMProvider):
    name = "deepseek"

    def answer(
        self,
        question: str,
        hits: list[SearchHit],
        history: list[dict] | None = None,
        api_key: str | None = None,
    ) -> str:
        effective_api_key = (api_key or settings.deepseek_api_key or get_secret(PROVIDER_DEEPSEEK) or "").strip()
        if not effective_api_key:
            return local_answer_fallback(question, hits, "DeepSeek API key nao informada")

        context = "\n\n".join(format_hit_for_prompt(index + 1, hit) for index, hit in enumerate(hits))
        messages = [
            {
                "role": "system",
                "content": (
                    "Voce e um assistente tecnico de RAG para videos. Responda em portugues, "
                    "use apenas o contexto recuperado e cite arquivo/timestamp. "
                    "Use o historico curto apenas para entender referencias como 'isso' ou 'aquele ponto'. "
                    "Se o contexto nao contiver a resposta, diga que nao encontrou no video."
                ),
            },
            *format_history(history),
            {"role": "user", "content": f"Pergunta atual: {question}\n\nContexto recuperado:\n{context}"},
        ]
        response = httpx.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {effective_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": messages,
                "temperature": 0.2,
            },
            timeout=90,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def summarize_topics(self, transcript_text: str) -> str:
        if not settings.deepseek_api_key:
            return ""
        response = httpx.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Extraia topicos de um SRT. Responda em linhas: timestamp inicial | titulo | resumo curto.",
                    },
                    {"role": "user", "content": transcript_text[:24_000]},
                ],
                "temperature": 0.2,
            },
            timeout=90,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def answer(
        self,
        question: str,
        hits: list[SearchHit],
        history: list[dict] | None = None,
        api_key: str | None = None,
    ) -> str:
        context = "\n\n".join(format_hit_for_prompt(index + 1, hit) for index, hit in enumerate(hits))
        messages = [
            {
                "role": "system",
                "content": (
                    "Voce e um assistente local simples de RAG para videos. Responda curto, em portugues. "
                    "Use somente o contexto recuperado. Sempre cite timestamps. "
                    "Se nao encontrar evidencia nos trechos, diga 'Nao encontrei isso nos trechos recuperados'."
                ),
            },
            *format_history(history),
            {"role": "user", "content": f"Pergunta atual: {question}\n\nContexto recuperado:\n{context}"},
        ]
        response = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_llm_model,
                "stream": False,
                "messages": messages,
                "options": {"temperature": 0.1, "num_ctx": 4096},
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def summarize_topics(self, transcript_text: str) -> str:
        response = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_topic_model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": "Extraia topicos do trecho de transcript. Responda somente linhas no formato: timestamp inicial | titulo curto | resumo curto."},
                    {"role": "user", "content": transcript_text[:12_000]},
                ],
                "options": {"temperature": 0.1, "num_ctx": 4096},
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


def get_llm_provider(mode: str | None = None) -> BaseLLMProvider:
    if mode == "local":
        return OllamaProvider()
    if mode == "cloud":
        return DeepSeekProvider()
    if settings.llm_provider == "ollama":
        return OllamaProvider()
    return DeepSeekProvider()


def get_topic_provider() -> BaseLLMProvider:
    return OllamaProvider()


def format_history(history: list[dict] | None) -> list[dict]:
    if not history:
        return []
    formatted = []
    for item in history[-8:]:
        role = item.get("role")
        text = str(item.get("text", "")).strip()[:1200]
        if role in {"user", "assistant"} and text:
            formatted.append({"role": role, "content": text})
    return formatted


def format_hit_for_prompt(index: int, hit: SearchHit) -> str:
    return (
        f"[{index}] arquivo={hit.file_name} tempo={hit.start_seconds:.1f}s-{hit.end_seconds:.1f}s "
        f"score={hit.score:.3f}\n{hit.text}"
    )


def local_answer_fallback(question: str, hits: list[SearchHit], reason: str) -> str:
    lines = [
        f"Resposta local limitada: {reason}.",
        f"Pergunta: {question}",
        "Trechos mais relevantes encontrados localmente:",
    ]
    for index, hit in enumerate(hits, start=1):
        lines.append(
            f"{index}. {hit.file_name} [{hit.start_seconds:.1f}s-{hit.end_seconds:.1f}s] "
            f"score={hit.score:.3f}: {hit.text[:500]}"
        )
    return "\n\n".join(lines)
