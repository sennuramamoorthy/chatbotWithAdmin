"""The streaming counterpart of the grounded answer pipeline (US-1, AC-1.3).

This mirrors :class:`~takshashila_chatbot.application.answer_service.AnswerService`
stage-for-stage and outcome-for-outcome — input guard -> boundary -> language ->
retrieve -> grounding gate -> date enrichment -> generate -> log outcome — but
instead of returning a finished answer it *yields* events as work happens, so the
transport layer can flush tokens to the visitor the moment the model emits them.

The cheap, deterministic gates (guard, boundary, grounding) still run before the
LLM is ever reached: a blocked, invalid, or ungrounded turn never opens a token
stream. Each call to :meth:`AnswerStreamService.stream` yields zero or more
``{"type": "token", "text": ...}`` events followed by exactly one terminal
``{"type": "done", ...}`` event carrying the outcome, language, citations, and the
lead offer flag.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol

from ..domain.boundary import screen
from ..domain.clock import Clock
from ..domain.enrichment import compute_facts
from ..domain.input_guards import validate_question
from ..domain.language import detect_language
from ..domain.retrieval import DEFAULT_GROUNDING_THRESHOLD, RetrievedChunk, select_grounded
from .answer_service import DEFAULT_FALLBACK, Outcome
from .ports import GenerationRequest, OutcomeSink, QuestionOutcome, Retriever


class StreamingLanguageModel(Protocol):
    """A model that emits a grounded answer as a stream of token strings."""

    def stream_tokens(self, request: GenerationRequest) -> Iterator[str]: ...


class AnswerStreamService:
    def __init__(
        self,
        retriever: Retriever,
        llm: StreamingLanguageModel,
        clock: Clock,
        *,
        outcome_sink: OutcomeSink | None = None,
        grounding_threshold: float = DEFAULT_GROUNDING_THRESHOLD,
        top_k: int = 5,
        fallback_message: str = DEFAULT_FALLBACK,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._clock = clock
        self._sink = outcome_sink
        self._threshold = grounding_threshold
        self._top_k = top_k
        self._fallback = fallback_message

    def stream(self, question: str) -> Iterator[dict]:
        check = validate_question(question)
        if not check.ok:
            yield {"type": "token", "text": check.message or ""}
            yield self._done(Outcome.INVALID_INPUT, None)
            return
        text = check.normalized

        verdict = screen(text)
        if not verdict.allowed:
            yield {"type": "token", "text": verdict.response or ""}
            yield self._done(Outcome.BLOCKED, None)
            return

        language = detect_language(text).value

        chunks: Sequence[RetrievedChunk] = self._retriever.retrieve(text, top_k=self._top_k)
        grounded = select_grounded(chunks, self._threshold)
        if not grounded:
            self._record(text, "dead_end", None, language)
            yield {"type": "token", "text": self._fallback}
            yield self._done(Outcome.DEAD_END, language, offer_lead=True)
            return

        facts = compute_facts(grounded, self._clock.today())
        context = "\n\n".join(c.text for c in grounded)
        request = GenerationRequest(
            question=text, language=language, context=context, facts=tuple(facts)
        )
        for token in self._llm.stream_tokens(request):
            yield {"type": "token", "text": token}

        self._record(text, "answered", grounded[0].topic, language)
        citations = list(dict.fromkeys(c.document_id for c in grounded))
        yield self._done(Outcome.ANSWERED, language, citations=citations)

    def _done(
        self,
        outcome: Outcome,
        language: str | None,
        *,
        citations: list[str] | None = None,
        offer_lead: bool = False,
    ) -> dict:
        return {
            "type": "done",
            "outcome": outcome.value,
            "language": language,
            "citations": citations or [],
            "offer_lead": offer_lead,
        }

    def _record(self, question: str, outcome: str, topic: str | None, language: str) -> None:
        if self._sink is not None:
            self._sink.record(
                QuestionOutcome(
                    question=question, outcome=outcome, topic=topic, language=language
                )
            )
