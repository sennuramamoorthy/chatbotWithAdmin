"""Self-hosted embeddings adapter (OpenAI-compatible /v1/embeddings).

Works with a self-hosted multilingual embedding server (e.g. BGE-M3 / multilingual-e5
served via TEI or vLLM). Implements the ``Embedder`` port.
"""

from __future__ import annotations

import httpx


class HttpEmbedder:
    def __init__(self, client: httpx.Client, *, model: str) -> None:
        self._client = client
        self._model = model

    def embed(self, text: str) -> list[float]:
        response = self._client.post(
            "/v1/embeddings", json={"model": self._model, "input": text}
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
