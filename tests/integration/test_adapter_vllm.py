"""VllmLanguageModel — OpenAI-compatible chat completions (generate + stream)."""

import json

import httpx
import pytest

from takshashila_chatbot.adapters.vllm_llm import VllmLanguageModel
from takshashila_chatbot.application.ports import GenerationRequest

pytestmark = pytest.mark.integration


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://infer")


def _req() -> GenerationRequest:
    return GenerationRequest(
        question="What is the fee?",
        language="en",
        context="The fee is 1,50,000.",
        facts=("FEE STATUS: upcoming (due 2026-12-31)",),
    )


def test_generate_sends_grounded_prompt_and_parses_content():
    captured = {}

    def handler(request):
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "The fee is INR 1,50,000."}}]}
        )

    llm = VllmLanguageModel(_client(handler), model="llama-instruct")
    out = llm.generate(_req())

    assert out == "The fee is INR 1,50,000."
    assert captured["path"] == "/v1/chat/completions"
    assert captured["body"]["model"] == "llama-instruct"
    assert captured["body"]["stream"] is False
    sent = captured["body"]["messages"][-1]["content"]
    assert "FEE STATUS: upcoming" in sent  # computed fact passed through
    assert "The fee is 1,50,000." in sent  # grounded context passed through
    assert "only" in sent.lower()  # grounding rule present


def test_stream_tokens_yields_content_deltas():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )

    llm = VllmLanguageModel(_client(handler), model="llama-instruct")
    assert list(llm.stream_tokens(_req())) == ["Hello", " world"]


def test_stream_tokens_skips_empty_deltas_and_ends_without_done():
    # First chunk carries a role delta (no content) and the stream ends with no
    # explicit [DONE] sentinel — both must be handled.
    sse = (
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
    )

    def handler(request):
        return httpx.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )

    llm = VllmLanguageModel(_client(handler), model="llama-instruct")
    assert list(llm.stream_tokens(_req())) == ["Hi"]
