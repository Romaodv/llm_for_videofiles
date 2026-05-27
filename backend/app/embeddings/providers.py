import hashlib
import math
from abc import ABC, abstractmethod


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


def re_tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[\w.-]+", text.lower())


def get_embedding_provider() -> BaseEmbeddingProvider:
    return HashingEmbeddingProvider()
