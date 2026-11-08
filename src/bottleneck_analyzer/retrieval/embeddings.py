"""Optional real embedding adapter, validated vectors, explicit enrichment only."""

import json
import math
from typing import Protocol
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bottleneck_analyzer.core.config import AppSettings


class EmbeddingUnavailable(ValueError):
    """Safe public error with no provider response, credential or URL details."""


class EmbeddingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str = Field(min_length=1, max_length=25)
    model: str = Field(min_length=1, max_length=50)
    dimensions: int = Field(gt=0, le=16000)

    @property
    def identity(self) -> str:
        return f"{self.provider}:{self.model}:{self.dimensions}:source-v1"

    @model_validator(mode="after")
    def identity_fits(self) -> "EmbeddingSpec":
        if len(self.identity) > 100:
            raise ValueError("Embedding identity exceeds stored metadata capacity")
        return self


def validate_vector(vector: list[float], spec: EmbeddingSpec) -> list[float]:
    if len(vector) != spec.dimensions:
        raise EmbeddingUnavailable("Embedding dimension mismatch")
    if any(not math.isfinite(v) for v in vector) or not any(v != 0 for v in vector):
        raise EmbeddingUnavailable("Embedding must be finite and nonzero")
    return [float(v) for v in vector]


class Embedder(Protocol):
    spec: EmbeddingSpec

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """Standard-library HTTP client; no SDK or additional dependency required."""

    def __init__(self, settings: AppSettings):
        if settings.embedding_provider != "openai" or not settings.embedding_model:
            raise EmbeddingUnavailable("Embedding provider/model is not configured")
        if not settings.embedding_api_key or not settings.embedding_api_key.get_secret_value():
            raise EmbeddingUnavailable("Embedding API key is not configured")
        url = urlparse(settings.embedding_base_url)
        if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
            raise EmbeddingUnavailable("Embedding endpoint must be an HTTPS base URL")
        self.spec = EmbeddingSpec(
            provider=settings.embedding_provider,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        self.settings = settings

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or len(texts) > 64 or any(not t.strip() or len(t) > 6000 for t in texts):
            raise EmbeddingUnavailable("Embedding input must contain 1–64 nonempty bounded texts")
        body = json.dumps(
            {
                "input": texts,
                "model": self.spec.model,
                "dimensions": self.spec.dimensions,
                "encoding_format": "float",
            }
        ).encode()
        request = Request(
            self.settings.embedding_base_url.rstrip("/") + "/embeddings",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.settings.embedding_api_key.get_secret_value(),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.embedding_timeout_seconds) as response:
                payload = json.loads(response.read(8_000_000))
            data = sorted(payload["data"], key=lambda item: item["index"])
            if payload["model"] != self.spec.model or [r["index"] for r in data] != list(
                range(len(texts))
            ):
                raise EmbeddingUnavailable("Embedding response model or item count mismatch")
            return [validate_vector(r["embedding"], self.spec) for r in data]
        except (URLError, TimeoutError, OSError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, EmbeddingUnavailable):
                raise
            raise EmbeddingUnavailable(
                "Embedding provider failed or returned an invalid response"
            ) from None


def embed_texts(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    vectors = embedder.embed(texts)
    if len(vectors) != len(texts):
        raise EmbeddingUnavailable("Embedding response count mismatch")
    return [validate_vector(v, embedder.spec) for v in vectors]


class CachedEmbedder:
    """Operation-local reuse of real vectors for identical text and one fixed model."""

    def __init__(self, provider: Embedder, seed: dict[str, list[float]] | None = None):
        self.provider = provider
        self.spec = provider.spec
        self.cache = {
            text: validate_vector(vector, self.spec) for text, vector in (seed or {}).items()
        }
        self.requests = 0
        self.generated_texts = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        missing = list(dict.fromkeys(t for t in texts if t not in self.cache))
        for offset in range(0, len(missing), 64):
            batch = missing[offset : offset + 64]
            vectors = embed_texts(self.provider, batch)
            self.cache.update(zip(batch, vectors, strict=True))
            self.requests += 1
            self.generated_texts += len(batch)
        return [list(self.cache[t]) for t in texts]


def pool(vectors: list[list[float]], spec: EmbeddingSpec) -> list[float]:
    """Source-level fallback-document representation from real chunk embeddings."""
    for vector in vectors:
        validate_vector(vector, spec)
    if not vectors:
        raise EmbeddingUnavailable("No vectors to combine")
    mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(spec.dimensions)]
    norm = math.sqrt(sum(v * v for v in mean))
    if norm == 0:
        raise EmbeddingUnavailable("Pooled embedding is zero")
    return validate_vector([v / norm for v in mean], spec)
