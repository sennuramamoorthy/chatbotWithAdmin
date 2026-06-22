"""Date-fact enrichment (FR-4, FR-5).

For retrieved fee/admission chunks that carry structured dates, compute the
current status with the deterministic date functions and emit a short fact string.
These facts are injected into the LLM context as ground truth, so the model never
compares dates itself — guaranteeing correctness on the day asked (EC-3..EC-5).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from .admissions import admission_status
from .fees import fee_status
from .retrieval import RetrievedChunk


def compute_facts(chunks: Sequence[RetrievedChunk], today: dt.date) -> list[str]:
    facts: list[str] = []

    for chunk in chunks:
        meta = chunk.metadata

        if chunk.topic == "fees" and "due_date" in meta:
            status = fee_status(dt.date.fromisoformat(meta["due_date"]), today)
            facts.append(
                f"FEE STATUS: {status.state.value} (due {status.due_date.isoformat()})"
            )

        elif (
            chunk.topic == "admissions"
            and "open_date" in meta
            and "close_date" in meta
        ):
            status = admission_status(
                dt.date.fromisoformat(meta["open_date"]),
                dt.date.fromisoformat(meta["close_date"]),
                today,
            )
            facts.append(
                f"ADMISSION STATUS: {status.state.value} "
                f"(closes {status.close_date.isoformat()})"
            )

    return facts
