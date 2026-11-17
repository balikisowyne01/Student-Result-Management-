"""Pandas-based ETL pipeline for bulk CSV/Excel score sheet ingestion and validation."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from srms.database import Course, Semester, Student
from srms.repository import log_audit, upsert_result

REQUIRED_SCORE_COLUMNS = {
    "matric_no",
    "course_code",
    "session_name",
    "semester_name",
    "ca_score",
    "exam_score",
}


@dataclass
class ValidationReport:
    valid_df: pd.DataFrame
    errors_df: pd.DataFrame
    total_rows: int

    @property
    def is_clean(self) -> bool:
        return self.errors_df.empty and not self.valid_df.empty


def generate_score_template_excel() -> bytes:
    """Return an empty, formatted Excel template for bulk score ingestion."""
    columns = [
        "matric_no",
        "course_code",
        "session_name",
        "semester_name",
        "ca_score",
        "exam_score",
    ]
    df = pd.DataFrame(columns=columns)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Scores_Template")
    return buf.getvalue()


def generate_score_template_csv() -> bytes:
    """Return an empty CSV template for bulk score ingestion."""
    columns = [
        "matric_no",
        "course_code",
        "session_name",
        "semester_name",
        "ca_score",
        "exam_score",
    ]
    return (",".join(columns) + "\n").encode("utf-8")


def load_tabular_file(file_obj: BinaryIO, filename: str) -> pd.DataFrame:
    """Read CSV or Excel upload into a Pandas DataFrame with normalized column names."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(file_obj)
    elif lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_obj)
    else:
        raise ValueError("Unsupported file format. Please upload .csv or .xlsx.")

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def validate_score_dataframe(df: pd.DataFrame, session: Session) -> ValidationReport:
    """Validate uploaded score rows against schema rules and database references."""
    missing_cols = REQUIRED_SCORE_COLUMNS - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_cols))}")

    if df.empty:
        return ValidationReport(valid_df=df.copy(), errors_df=pd.DataFrame(), total_rows=0)

    work = df.copy()
    work["row_number"] = work.index + 2  # 1-based + header row

    known_students = {
        m.upper(): sid for m, sid in session.execute(select(Student.matric_no, Student.id)).all()
    }
    known_courses = {
        c.upper(): cid for c, cid in session.execute(select(Course.course_code, Course.id)).all()
    }
    known_semesters = {
        (s.strip(), sem.strip()): sid
        for s, sem, sid in session.execute(
            select(Semester.session_name, Semester.semester_name, Semester.id)
        ).all()
    }

    valid_rows: list[dict] = []
    error_rows: list[dict] = []

    seen_keys: set[tuple[str, str, str, str]] = set()

    for _, row in work.iterrows():
        reasons: list[str] = []
        matric = str(row.get("matric_no", "")).strip().upper()
        course_code = str(row.get("course_code", "")).strip().upper()
        sess_name = str(row.get("session_name", "")).strip()
        sem_name = str(row.get("semester_name", "")).strip()

        if not matric or matric == "NAN":
            reasons.append("Missing matric_no")
        elif matric not in known_students:
            reasons.append(f"Unknown matric_no '{matric}'")

        if not course_code or course_code == "NAN":
            reasons.append("Missing course_code")
        elif course_code not in known_courses:
            reasons.append(f"Unknown course_code '{course_code}'")

        if (sess_name, sem_name) not in known_semesters:
            reasons.append(f"Unknown semester '{sess_name} - {sem_name}'")

        key = (matric, course_code, sess_name, sem_name)
        if key in seen_keys:
            reasons.append("Duplicate row in uploaded file")
        seen_keys.add(key)

        try:
            ca = float(row.get("ca_score"))
            if pd.isna(ca) or ca < 0 or ca > 40:
                reasons.append("ca_score must be between 0 and 40")
        except (TypeError, ValueError):
            ca = None
            reasons.append("Invalid numeric ca_score")

        try:
            exam = float(row.get("exam_score"))
            if pd.isna(exam) or exam < 0 or exam > 100:
                reasons.append("exam_score must be between 0 and 100")
        except (TypeError, ValueError):
            exam = None
            reasons.append("Invalid numeric exam_score")

        if ca is not None and exam is not None and (ca + exam) > 100:
            reasons.append(f"Total score ({ca + exam}) exceeds 100")

        if reasons:
            err = row.to_dict()
            err["validation_error"] = "; ".join(reasons)
            error_rows.append(err)
        else:
            valid_rows.append(
                {
                    "row_number": int(row["row_number"]),
                    "student_id": known_students[matric],
                    "matric_no": matric,
                    "course_id": known_courses[course_code],
                    "course_code": course_code,
                    "semester_id": known_semesters[(sess_name, sem_name)],
                    "session_name": sess_name,
                    "semester_name": sem_name,
                    "ca_score": round(ca, 2),
                    "exam_score": round(exam, 2),
                    "total_score": round(ca + exam, 2),
                }
            )

    return ValidationReport(
        valid_df=pd.DataFrame(valid_rows),
        errors_df=pd.DataFrame(error_rows),
        total_rows=len(work),
    )


def commit_validated_scores(
    valid_df: pd.DataFrame, session: Session, actor: str = "Data Analyst"
) -> int:
    """Persist validated score rows into the database and record a batch audit entry."""
    if valid_df.empty:
        return 0

    count = 0
    for _, row in valid_df.iterrows():
        upsert_result(
            session=session,
            student_id=int(row["student_id"]),
            course_id=int(row["course_id"]),
            semester_id=int(row["semester_id"]),
            ca_score=float(row["ca_score"]),
            exam_score=float(row["exam_score"]),
            actor=actor,
        )
        count += 1

    log_audit(
        session,
        "BULK_UPLOAD",
        "Result",
        f"{count} rows",
        f"Committed {count} validated score records via ETL pipeline",
        actor=actor,
    )
    session.commit()
    return count
