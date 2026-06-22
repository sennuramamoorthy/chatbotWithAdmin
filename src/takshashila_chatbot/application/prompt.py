"""Prompt rendering for the grounded answer.

The real LLM adapter calls this; it is a pure function so the grounding and
partial-answer policy (FR-1, EC-2) is unit-tested and can't silently drift.
"""

from __future__ import annotations

from .ports import GenerationRequest

SYSTEM_RULES = (
    "You are the Takshashila University assistant. Answer ONLY using the provided "
    "Context and Facts. If part of the question is not covered, say you don't have "
    "that information and offer to connect the visitor with Admissions. Never invent "
    "details, and never discuss or compare other institutions. Reply grounded in the "
    "English source content."
)


def render_prompt(request: GenerationRequest) -> str:
    sections = [
        SYSTEM_RULES,
        f"Reply language: {request.language}.",
    ]
    if request.facts:
        sections.append("Facts (authoritative, already computed):\n" + "\n".join(request.facts))
    sections.append("Context:\n" + request.context)
    sections.append("Question: " + request.question)
    return "\n\n".join(sections)
