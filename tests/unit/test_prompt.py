"""Prompt rendering — encodes the grounding + partial-answer policy (FR-1, EC-2).

This is where the anti-fabrication and partial-answer rules (TC-003) are made
explicit to the model. Tested as a pure function so the policy can't silently drift.
"""

import pytest

from takshashila_chatbot.application.ports import GenerationRequest
from takshashila_chatbot.application.prompt import render_prompt

pytestmark = pytest.mark.unit


def _req(**overrides) -> GenerationRequest:
    base = dict(question="What is the fee?", language="en", context="The fee is X.", facts=())
    base.update(overrides)
    return GenerationRequest(**base)


def test_prompt_enforces_grounding_only():
    text = render_prompt(_req()).lower()
    assert "only" in text  # answer only from the provided context
    assert "invent" in text  # explicit no-fabrication instruction


def test_prompt_includes_partial_answer_and_handoff_policy():  # TC-003 / EC-2
    text = render_prompt(_req()).lower()
    assert "don't have" in text
    assert "admissions" in text


def test_prompt_includes_context_and_question():
    text = render_prompt(_req(context="UNIQUE_CONTEXT", question="UNIQUE_Q"))
    assert "UNIQUE_CONTEXT" in text
    assert "UNIQUE_Q" in text


def test_prompt_includes_facts_when_present():
    text = render_prompt(_req(facts=("FEE STATUS: overdue (due 2026-06-30)",)))
    assert "overdue" in text


def test_prompt_reflects_reply_language():
    assert "reply language: ta" in render_prompt(_req(language="ta")).lower()


def test_prompt_without_facts_omits_facts_section():
    # "Facts" still appears in the grounding rules; assert the *section* is omitted.
    assert "Facts (authoritative" not in render_prompt(_req(facts=()))
