"""Unit and integration tests for the Student Result Management System."""

from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from srms.analytics import (
    compute_cgpa_table,
    compute_course_statistics,
    compute_semester_gpa_table,
    identify_at_risk_students,
)
from srms.database import Base
from srms.etl import commit_validated_scores, validate_score_dataframe
from srms.exports import export_broadsheet_excel, export_student_transcript_pdf
from srms.grading import calculate_gpa, classify_standing, score_to_grade
from srms.repository import (
    fetch_audit_logs_dataframe,
    fetch_results_dataframe,
    get_or_create_semester,
    upsert_course,
    upsert_result,
    upsert_student,
)
from srms.visualizations import (
    plot_ca_vs_exam_scatter,
    plot_course_pass_rates,
    plot_department_cgpa_boxplot,
    plot_grade_distribution,
    plot_score_histogram_kde,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_five_point_grading_boundaries():
    assert score_to_grade(70).letter == "A"
    assert score_to_grade(70).points == 5
    assert score_to_grade(65).letter == "B"
    assert score_to_grade(55).letter == "C"
    assert score_to_grade(47).letter == "D"
    assert score_to_grade(40).letter == "E"
    assert score_to_grade(39.5).letter == "F"
    assert score_to_grade(39.5).points == 0

    with pytest.raises(ValueError):
        score_to_grade(101)
    with pytest.raises(ValueError):
        score_to_grade(-1)


def test_gpa_and_standing():
    # (3 units * 5 pts + 2 units * 4 pts) / 5 units = 23 / 5 = 4.60
    assert calculate_gpa([(3, 5), (2, 4)]) == 4.60
    assert calculate_gpa([]) == 0.0
    assert classify_standing(4.60) == "First Class"
    assert classify_standing(3.80) == "Second Class Upper"
    assert classify_standing(2.90) == "Second Class Lower"
    assert classify_standing(1.90) == "Third Class"
    assert classify_standing(1.20) == "Pass"
    assert classify_standing(0.80) == "Probation / Fail"


def test_end_to_end_etl_analytics_visuals_and_exports(db_session):
    s1 = upsert_student(db_session, "CSC/2023/001", "Ada Lovelace", "Computer Science", 200)
    s2 = upsert_student(db_session, "CSC/2023/002", "Alan Turing", "Computer Science", 200)
    c1 = upsert_course(db_session, "CSC201", "Data Structures", 3, "Computer Science", 200)
    c2 = upsert_course(db_session, "MTH201", "Linear Algebra", 2, "Mathematics", 200)
    sem = get_or_create_semester(db_session, "2025/2026", "First")

    # Direct result upsert
    upsert_result(db_session, s1.id, c1.id, sem.id, 30, 50)  # 80 -> A (5)

    # Bulk ETL with 2 valid rows and 2 invalid rows
    upload_df = pd.DataFrame(
        [
            {
                "matric_no": "CSC/2023/001",
                "course_code": "MTH201",
                "session_name": "2025/2026",
                "semester_name": "First",
                "ca_score": 25,
                "exam_score": 40,
            },
            {
                "matric_no": "CSC/2023/002",
                "course_code": "CSC201",
                "session_name": "2025/2026",
                "semester_name": "First",
                "ca_score": 10,
                "exam_score": 20,
            },
            {
                "matric_no": "UNKNOWN/999",
                "course_code": "CSC201",
                "session_name": "2025/2026",
                "semester_name": "First",
                "ca_score": 20,
                "exam_score": 50,
            },
            {
                "matric_no": "CSC/2023/002",
                "course_code": "MTH201",
                "session_name": "2025/2026",
                "semester_name": "First",
                "ca_score": 35,
                "exam_score": 80,  # > 100 total
            },
        ]
    )

    report = validate_score_dataframe(upload_df, db_session)
    assert report.total_rows == 4
    assert len(report.valid_df) == 2
    assert len(report.errors_df) == 2

    committed = commit_validated_scores(report.valid_df, db_session)
    assert committed == 2

    results_df = fetch_results_dataframe(db_session)
    assert len(results_df) == 3

    sem_gpa_df = compute_semester_gpa_table(results_df)
    cgpa_df = compute_cgpa_table(results_df)
    course_stats_df = compute_course_statistics(results_df)
    at_risk_df = identify_at_risk_students(cgpa_df)

    # Ada: (3*5 + 2*4) / 5 = 4.60
    ada_cgpa = cgpa_df.loc[cgpa_df["matric_no"] == "CSC/2023/001", "cgpa"].iloc[0]
    assert ada_cgpa == 4.60
    assert len(sem_gpa_df) == 2
    assert len(course_stats_df) == 2
    assert list(at_risk_df["matric_no"]) == ["CSC/2023/002"]

    # Visualizations render cleanly
    for fig in (
        plot_grade_distribution(results_df),
        plot_score_histogram_kde(results_df),
        plot_department_cgpa_boxplot(cgpa_df),
        plot_course_pass_rates(course_stats_df),
        plot_ca_vs_exam_scatter(results_df),
    ):
        assert fig is not None

    # Exports
    xlsx_bytes = export_broadsheet_excel(results_df)
    assert xlsx_bytes[:2] == b"PK"

    pdf_bytes = export_student_transcript_pdf(results_df, "CSC/2023/001")
    assert pdf_bytes[:4] == b"%PDF"

    # Audit logs recorded
    audit_df = fetch_audit_logs_dataframe(db_session)
    assert not audit_df.empty
