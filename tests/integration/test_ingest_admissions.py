"""Ingestion of the admissions SQLite DB into topic-tagged retrieval chunks."""

import sqlite3

import pytest

from takshashila_chatbot.ingest.admissions_db import read_admissions_db, row_to_text

pytestmark = pytest.mark.integration


def _make_db(path: str) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE admission_info (description TEXT, amount TEXT, currency TEXT);
        CREATE TABLE courses (program TEXT, school TEXT, duration_years TEXT, course_fees TEXT,
            eligibility TEXT, industry_collaborated_programmes TEXT, industry_integrated_programmes TEXT);
        CREATE TABLE new_courses (program TEXT, school TEXT, academic_year TEXT,
            industry_partner TEXT, programme_type TEXT, notes TEXT);
        CREATE TABLE industry_integrated_programme_fees (programme_name TEXT, company TEXT,
            location TEXT, intake TEXT, annual_fee TEXT, tu_annual_term_fee TEXT, total_fee TEXT,
            academic_year TEXT, notes TEXT);
        CREATE TABLE hostel_fees (hostel_name TEXT, campus TEXT, ac_type TEXT, sharing_type TEXT,
            washroom_type TEXT, annual_fees TEXT, hostel_category TEXT, notes TEXT);
        CREATE TABLE placements (company_name TEXT, job_role TEXT, salary_package TEXT, campus_drive_date TEXT);
        CREATE TABLE scholarships (scheme_type TEXT, category TEXT, sub_category TEXT,
            eligibility_criteria TEXT, concession_percentage TEXT, applicable_programmes TEXT, remarks TEXT);
        CREATE TABLE transport_routes (bus_no TEXT, route_name TEXT, bus_stops TEXT);
        """
    )
    con.execute("INSERT INTO admission_info VALUES (?,?,?)",
                ("Application and registration fee", "3000", "INR"))
    con.execute("INSERT INTO courses VALUES (?,?,?,?,?,?,?)",
                ("BSc Hons Agriculture", "School of Agricultural Sciences", "4.0", "100000", "Pass in 10+2", None, None))
    con.execute("INSERT INTO courses VALUES (?,?,?,?,?,?,?)",
                (None, None, None, None, None, None, None))  # all-blank -> skipped
    con.execute("INSERT INTO new_courses VALUES (?,?,?,?,?,?)",
                ("MSc Medical Biochemistry", "Medical College", "2026-2027", None, "regular", ""))
    con.execute("INSERT INTO industry_integrated_programme_fees VALUES (?,?,?,?,?,?,?,?,?)",
                ("B.Tech CSE (Data Science)", "Nxtwave", "Hyderabad", "300", "200000", "15000", "215000", "2026-27", "Industry programme"))
    con.execute("INSERT INTO hostel_fees VALUES (?,?,?,?,?,?,?,?)",
                ("Mailam Hostel", "Mailam Campus", "Non AC", "3 Sharing", "Common", "75000", "Regular", "Includes mess"))
    con.execute("INSERT INTO placements VALUES (?,?,?,?)",
                ("INCRUITER", "Finance Intern", "700000", "2024-09-24"))
    con.execute("INSERT INTO scholarships VALUES (?,?,?,?,?,?,?)",
                ("Academic Scholarship", "Merit Based", "75-89", "Academic", "0.25", "All Programmes", "Tuition concession"))
    con.execute("INSERT INTO transport_routes VALUES (?,?,?)",
                ("2", "VILLIANOOR", "VILLIYANUR BYEBASS,PERAMBAI ROAD"))
    con.commit()
    con.close()


def test_row_to_text_skips_none_and_blank():
    text = row_to_text(
        {"a": "x", "b": None, "c": "   ", "d": "y"},
        [("A", "a"), ("B", "b"), ("C", "c"), ("D", "d")],
    )
    assert text == "A: x. D: y"


def test_reads_all_tables_into_topic_tagged_chunks(tmp_path):
    db = tmp_path / "admissions.db"
    _make_db(str(db))

    chunks = read_admissions_db(str(db))
    by_doc: dict[str, list] = {}
    for c in chunks:
        by_doc.setdefault(c.document_id, []).append(c)

    assert {"admissions", "courses", "facilities", "placements", "fees", "transport"} <= {
        c.topic for c in chunks
    }
    assert len(by_doc["courses"]) == 1  # the all-blank courses row was skipped

    text = {doc: rows[0].text for doc, rows in by_doc.items()}
    assert "3000" in text["admission_info"]
    assert "BSc Hons Agriculture" in text["courses"]
    assert "75000" in text["hostel_fees"]
    assert "VILLIANOOR" in text["transport_routes"]
    assert "Notes:" not in text["new_courses"]  # the empty-string note was skipped
