"""The grounded answer pipeline (FR-1..FR-9 orchestration).

Cheap, deterministic stages run first; the LLM is reached only when the question
is well-formed, in-bounds, and backed by grounded content:

    input guard -> boundary -> language -> retrieve -> grounding gate
                -> date enrichment -> generate -> log outcome

Rate limiting and session memory belong to the transport layer and are not part
of this service.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from ..domain.boundary import screen
from ..domain.clock import Clock
from ..domain.enrichment import compute_facts
from ..domain.input_guards import validate_question
from ..domain.language import detect_language
from ..domain.retrieval import DEFAULT_GROUNDING_THRESHOLD, RetrievedChunk, select_grounded
from .ports import GenerationRequest, LanguageModel, OutcomeSink, QuestionOutcome, Retriever

# Static fallback (FR-3). Real Admissions contact is wired in later (OQ-4).
DEFAULT_FALLBACK = (
    "I'm sorry — I don't have that information yet. You can reach the Admissions "
    "team directly, or share your details and they'll follow up with you."
)


class Outcome(str, Enum):
    ANSWERED = "answered"
    DEAD_END = "dead_end"
    BLOCKED = "blocked"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class AnswerResult:
    outcome: Outcome
    text: str
    language: str | None = None
    citations: tuple[str, ...] = ()
    offer_lead: bool = False


class AnswerService:
    def __init__(
        self,
        retriever: Retriever,
        llm: LanguageModel,
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

    def answer(self, question: str) -> AnswerResult:
        check = validate_question(question)
        if not check.ok:
            return AnswerResult(Outcome.INVALID_INPUT, check.message or "")
        text = check.normalized

        verdict = screen(text)
        if not verdict.allowed:
            return AnswerResult(Outcome.BLOCKED, verdict.response or "")

        language = detect_language(text).value

        chunks: Sequence[RetrievedChunk] = self._retriever.retrieve(text, top_k=self._top_k)
        grounded = select_grounded(chunks, self._threshold)
        if not grounded:
            self._record(text, "dead_end", None, language)
            return AnswerResult(
                Outcome.DEAD_END, self._fallback, language=language, offer_lead=True
            )

        facts = compute_facts(grounded, self._clock.today())
        context = "\n\n".join(c.text for c in grounded)
        request = GenerationRequest(
            question=text, language=language, context=context, facts=tuple(facts)
        )
        answer_text = self._llm.generate(request)

        self._record(text, "answered", grounded[0].topic, language)
        citations = tuple(dict.fromkeys(c.document_id for c in grounded))
        return AnswerResult(
            Outcome.ANSWERED, answer_text, language=language, citations=citations
        )

    def _record(self, question: str, outcome: str, topic: str | None, language: str) -> None:
        if self._sink is not None:
            self._sink.record(
                QuestionOutcome(
                    question=question, outcome=outcome, topic=topic, language=language
                )
            )
