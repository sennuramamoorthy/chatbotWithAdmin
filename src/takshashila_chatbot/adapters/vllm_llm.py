"""Self-hosted LLM adapter (OpenAI-compatible chat completions).

Targets a self-hosted open-weight instruct model served by vLLM. Implements the
``LanguageModel`` port (``generate``) and adds ``stream_tokens`` for true
token-level streaming, which the transport layer will adopt in a later increment.
The grounded prompt is built by the pure ``render_prompt`` so the policy is shared
and tested in one place.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from ..application.ports import GenerationRequest
from ..application.prompt import render_prompt


class VllmLanguageModel:
    def __init__(
        self,
        client: httpx.Client,
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _payload(self, request: GenerationRequest, *, stream: bool) -> dict:
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": render_prompt(request)}],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": stream,
        }

    def generate(self, request: GenerationRequest) -> str:
        response = self._client.post(
            "/v1/chat/completions", json=self._payload(request, stream=False)
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def stream_tokens(self, request: GenerationRequest) -> Iterator[str]:
        with self._client.stream(
            "POST", "/v1/chat/completions", json=self._payload(request, stream=True)
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                delta = json.loads(data)["choices"][0]["delta"].get("content")
                if delta:
                    yield delta
