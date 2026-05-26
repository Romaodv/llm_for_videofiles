import hashlib
import math
from abc import ABC, abstractmethod

import httpx

from backend.app.config import settings


class BaseEmbeddingProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class HashingEmbeddingProvider(BaseEmbeddingProvider):
    name = "hashing"
    model = "local-hashing-384"

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re_tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    name = "ollama"

    def __init__(self) -> None:
        self.model = settings.ollama_embedding_model

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            f"{settings.ollama_base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
            timeout=60,
        )
        response.raise_for_status()
        return [float(value) for value in response.json()["embedding"]]


def re_tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[\w.-]+", text.lower())


def get_embedding_provider() -> BaseEmbeddingProvider:
    if settings.embedding_provider == "ollama":
        return OllamaEmbeddingProvider()
    return HashingEmbeddingProvider()
