from abc import ABC, abstractmethod

import httpx

from backend.app.config import settings
from backend.app.services.secrets import PROVIDER_DEEPSEEK, PROVIDER_GROQ, get_secret
from backend.app.vectorstore.sqlite_vector import SearchHit


class BaseLLMProvider(ABC):
    name: str
    model: str

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

    @abstractmethod
    def summarize_presentation(self, topic_text: str) -> str:
        raise NotImplementedError


class DeepSeekProvider(BaseLLMProvider):
    name = "deepseek"
    model = settings.deepseek_model

    def answer(
        self,
        question: str,
        hits: list[SearchHit],
        history: list[dict] | None = None,
        api_key: str | None = None,
    ) -> str:
        effective_api_key = self._api_key(api_key)
        if not effective_api_key:
            return answer_fallback(question, hits, "DeepSeek API key nao informada")

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
        return self._chat(messages, effective_api_key, temperature=0.2)

    def summarize_topics(self, transcript_text: str) -> str:
        effective_api_key = self._require_api_key()
        messages = [
            {
                "role": "system",
                "content": (
                    "Extraia topicos de um trecho de transcript com timestamps. "
                    "Responda somente linhas no formato: timestamp inicial | titulo curto | resumo objetivo. "
                    "Use timestamps existentes do transcript e cubra as mudancas reais de assunto."
                ),
            },
            {"role": "user", "content": transcript_text},
        ]
        return self._chat(messages, effective_api_key, temperature=0.2)

    def summarize_presentation(self, topic_text: str) -> str:
        effective_api_key = self._require_api_key()
        messages = [
            {
                "role": "system",
                "content": (
                    "Voce escreve uma resenha tecnica em Markdown limpo, nao um indice de topicos. "
                    "Explique a apresentacao em portugues como se estivesse contando o raciocinio do processo para outro desenvolvedor SAP. "
                    "Use o formato: '## Resenha IA', depois 3 a 5 paragrafos discursivos com detalhe medio. "
                    "Cada paragrafo deve explicar o que o processo faz, por que existe, como flui e quais decisoes tecnicas/funcionais aparecem. "
                    "Obrigatorio: todo paragrafo depois do titulo deve comecar com um timestamp navegavel no formato [mm:ss](#t=segundos). "
                    "Use os segundos exatos fornecidos entre parenteses nos topicos. Exemplo: [12:34](#t=754). "
                    "Evite uma lista longa granular. Se precisar, termine com no maximo 4 bullets em '### Pontos-chave'. "
                    "Nao coloque varios bullets na mesma linha e nao invente informacoes alem dos topicos fornecidos."
                ),
            },
            {"role": "user", "content": topic_text},
        ]
        return self._chat(messages, effective_api_key, temperature=0.25)

    def _api_key(self, api_key: str | None = None) -> str:
        return (api_key or settings.deepseek_api_key or get_secret(PROVIDER_DEEPSEEK) or "").strip()

    def _require_api_key(self) -> str:
        api_key = self._api_key()
        if not api_key:
            raise RuntimeError("DeepSeek API key nao configurada. Salve a chave na UI antes de gerar topicos ou resumo.")
        return api_key

    def _chat(self, messages: list[dict], api_key: str, temperature: float) -> str:
        try:
            response = httpx.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "temperature": temperature,
                },
                timeout=90,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise RuntimeError(f"DeepSeek falhou ({exc.response.status_code}): {detail or exc}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"DeepSeek falhou: {exc}") from exc


class GroqProvider(BaseLLMProvider):
    name = "groq"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.groq_llm_model

    def answer(
        self,
        question: str,
        hits: list[SearchHit],
        history: list[dict] | None = None,
        api_key: str | None = None,
    ) -> str:
        effective_api_key = self._api_key(api_key)
        if not effective_api_key:
            return answer_fallback(question, hits, "Groq API key nao informada")

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
        return self._chat(messages, effective_api_key, temperature=0.2)

    def summarize_topics(self, transcript_text: str) -> str:
        effective_api_key = self._require_api_key()
        messages = [
            {
                "role": "system",
                "content": (
                    "Voce recebe o transcript completo de uma reuniao com timestamps compactos. "
                    "Entenda a reuniao inteira antes de dividir em topicos. "
                    "Responda somente linhas no formato: timestamp inicial | titulo curto | resumo objetivo. "
                    "Use timestamps existentes do transcript, cubra as mudancas reais de assunto e nao invente fatos."
                ),
            },
            {"role": "user", "content": transcript_text},
        ]
        return self._chat(messages, effective_api_key, temperature=0.2, timeout=180)

    def summarize_presentation(self, topic_text: str) -> str:
        effective_api_key = self._require_api_key()
        messages = [
            {
                "role": "system",
                "content": (
                    "Voce escreve uma resenha tecnica em Markdown limpo, nao um indice de topicos. "
                    "Explique a reuniao em portugues com entendimento global do conteudo. "
                    "Use o formato: '## Resenha IA', depois 3 a 5 paragrafos discursivos com detalhe medio. "
                    "Cada paragrafo deve explicar o que foi discutido, por que importa, decisoes, pendencias e fluxo geral. "
                    "Obrigatorio: todo paragrafo depois do titulo deve comecar com um timestamp navegavel no formato [mm:ss](#t=segundos). "
                    "Use os segundos exatos fornecidos entre parenteses nos topicos. Exemplo: [12:34](#t=754). "
                    "Evite uma lista longa granular. Se precisar, termine com no maximo 4 bullets em '### Pontos-chave'. "
                    "Nao coloque varios bullets na mesma linha e nao invente informacoes alem do transcript/topicos fornecidos."
                ),
            },
            {"role": "user", "content": topic_text},
        ]
        return self._chat(messages, effective_api_key, temperature=0.25, timeout=180)

    def _api_key(self, api_key: str | None = None) -> str:
        return (api_key or settings.groq_api_key or get_secret(PROVIDER_GROQ) or "").strip()

    def _require_api_key(self) -> str:
        api_key = self._api_key()
        if not api_key:
            raise RuntimeError("Groq API key nao configurada. Salve a chave na UI antes de gerar topicos, resumo ou chat.")
        return api_key

    def _chat(self, messages: list[dict], api_key: str, temperature: float, timeout: int = 90) -> str:
        try:
            response = httpx.post(
                f"{settings.groq_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise RuntimeError(f"Groq falhou ({exc.response.status_code}): {detail or exc}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Groq falhou: {exc}") from exc


def get_llm_provider(provider_name: str | None = None, provider_model: str | None = None) -> BaseLLMProvider:
    if provider_name == "groq":
        return GroqProvider(provider_model)
    return DeepSeekProvider()


def get_topic_provider(provider_name: str | None = None, provider_model: str | None = None) -> BaseLLMProvider:
    return get_llm_provider(provider_name, provider_model)


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


def answer_fallback(question: str, hits: list[SearchHit], reason: str) -> str:
    lines = [
        f"Resposta limitada: {reason}.",
        f"Pergunta: {question}",
        "Trechos mais relevantes encontrados no indice local:",
    ]
    for index, hit in enumerate(hits, start=1):
        lines.append(
            f"{index}. {hit.file_name} [{hit.start_seconds:.1f}s-{hit.end_seconds:.1f}s] "
            f"score={hit.score:.3f}: {hit.text[:500]}"
        )
    return "\n\n".join(lines)
