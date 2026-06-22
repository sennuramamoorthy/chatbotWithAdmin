"""HttpEmbedder — OpenAI-compatible /v1/embeddings, tested with a mock transport."""

import json

import httpx
import pytest

from takshashila_chatbot.adapters.embeddings import HttpEmbedder

pytestmark = pytest.mark.integration


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://infer")


def test_embed_posts_openai_shape_and_parses_vector():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    embedder = HttpEmbedder(_client(handler), model="bge-m3")
    vector = embedder.embed("hello")

    assert vector == [0.1, 0.2, 0.3]
    assert captured["path"] == "/v1/embeddings"
    assert captured["body"]["model"] == "bge-m3"
    assert captured["body"]["input"] == "hello"


def test_embed_raises_on_http_error():
    embedder = HttpEmbedder(
        _client(lambda request: httpx.Response(500, json={"error": "boom"})), model="bge-m3"
    )
    with pytest.raises(httpx.HTTPStatusError):
        embedder.embed("hello")
