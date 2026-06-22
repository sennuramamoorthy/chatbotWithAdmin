"""Ingest the admissions SQLite database into retrieval chunks.

Each source row becomes one self-contained, topic-tagged ``RetrievedChunk`` of
readable "Label: value" text, mapped onto the bot's in-scope topics (courses,
fees, facilities, placements, transport, admissions). The demo seeds an in-memory
chunk store with these; production embeds the same chunks into pgvector.

The mapping is a single data table (``_SOURCES``) + one row formatter, so it stays
small and fully testable against a temporary SQLite database.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence

from ..domain.retrieval import RetrievedChunk

# (table, topic, [(label, column), ...]) — columns are read from each row in order.
_SOURCES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("admission_info", "admissions", [
        ("Fee", "description"), ("Amount", "amount"), ("Currency", "currency"),
    ]),
    ("courses", "courses", [
        ("Programme", "program"), ("School", "school"),
        ("Duration (years)", "duration_years"), ("Course fee (INR)", "course_fees"),
        ("Eligibility", "eligibility"),
        ("Industry-collaborated", "industry_collaborated_programmes"),
        ("Industry-integrated", "industry_integrated_programmes"),
    ]),
    ("new_courses", "courses", [
        ("New programme", "program"), ("School", "school"),
        ("Academic year", "academic_year"), ("Industry partner", "industry_partner"),
        ("Type", "programme_type"), ("Notes", "notes"),
    ]),
    ("industry_integrated_programme_fees", "courses", [
        ("Programme", "programme_name"), ("Company", "company"), ("Location", "location"),
        ("Intake", "intake"), ("Annual fee (INR)", "annual_fee"),
        ("TU term fee (INR)", "tu_annual_term_fee"), ("Total fee (INR)", "total_fee"),
        ("Academic year", "academic_year"), ("Notes", "notes"),
    ]),
    ("hostel_fees", "facilities", [
        ("Hostel", "hostel_name"), ("Campus", "campus"), ("AC", "ac_type"),
        ("Sharing", "sharing_type"), ("Washroom", "washroom_type"),
        ("Annual hostel fee (INR)", "annual_fees"), ("Category", "hostel_category"),
        ("Notes", "notes"),
    ]),
    ("placements", "placements", [
        ("Company", "company_name"), ("Role", "job_role"),
        ("Package (INR)", "salary_package"), ("Drive date", "campus_drive_date"),
    ]),
    ("scholarships", "fees", [
        ("Scholarship", "scheme_type"), ("Category", "category"),
        ("Sub-category", "sub_category"), ("Eligibility", "eligibility_criteria"),
        ("Concession", "concession_percentage"),
        ("Applicable programmes", "applicable_programmes"), ("Remarks", "remarks"),
    ]),
    ("transport_routes", "transport", [
        ("Bus no", "bus_no"), ("Route", "route_name"), ("Stops", "bus_stops"),
    ]),
]


def row_to_text(row: Mapping[str, object], fields: Sequence[tuple[str, str]]) -> str:
    """Render selected columns as ``Label: value`` text, skipping blanks."""
    parts: list[str] = []
    for label, column in fields:
        value = row[column]
        if value is None:
            continue
        text = str(value).strip()
        if text:
            parts.append(f"{label}: {text}")
    return ". ".join(parts)


def read_admissions_db(path: str) -> list[RetrievedChunk]:
    """Read every source table and return topic-tagged retrieval chunks."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        chunks: list[RetrievedChunk] = []
        for table, topic, fields in _SOURCES:
            for index, row in enumerate(connection.execute(f"SELECT * FROM {table}")):
                text = row_to_text(row, fields)
                if text:
                    chunks.append(
                        RetrievedChunk(
                            chunk_id=f"{table}-{index}",
                            document_id=table,
                            text=text,
                            topic=topic,
                            score=0.0,
                            metadata={},
                        )
                    )
        return chunks
    finally:
        connection.close()
