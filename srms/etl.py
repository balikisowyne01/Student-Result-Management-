"""Pandas-based ETL pipeline for bulk CSV/Excel score sheet ingestion and validation."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from srms.database import Course, Semester, Student
from srms.repository import (
    get_or_create_semester,
    log_audit,
    upsert_course,
    upsert_result,
    upsert_student,
)

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


def validate_score_dataframe(
    df: pd.DataFrame, session: Session, auto_register: bool = False
) -> ValidationReport:
    """Validate uploaded score rows against schema rules and database references.

    When auto_register=True, unknown matric_no, course_code, and semesters are
    accepted in the preview and automatically created upon commit.
    """
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
        elif not auto_register and matric not in known_students:
            reasons.append(f"Unknown matric_no '{matric}'")

        if not course_code or course_code == "NAN":
            reasons.append("Missing course_code")
        elif not auto_register and course_code not in known_courses:
            reasons.append(f"Unknown course_code '{course_code}'")

        if not sess_name or sess_name == "NAN" or not sem_name or sem_name == "NAN":
            reasons.append("Missing session_name or semester_name")
        elif not auto_register and (sess_name, sem_name) not in known_semesters:
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
            full_name_val = row.get("full_name")
            dept_val = row.get("department")
            level_val = row.get("level")
            title_val = row.get("course_title")
            units_val = row.get("credit_units")

            valid_rows.append(
                {
                    "row_number": int(row["row_number"]),
                    "student_id": known_students.get(matric),
                    "matric_no": matric,
                    "full_name": str(full_name_val).strip() if pd.notna(full_name_val) and str(full_name_val).strip() else matric,
                    "department": str(dept_val).strip() if pd.notna(dept_val) and str(dept_val).strip() else "General",
                    "level": int(level_val) if pd.notna(level_val) else 100,
                    "course_id": known_courses.get(course_code),
                    "course_code": course_code,
                    "course_title": str(title_val).strip() if pd.notna(title_val) and str(title_val).strip() else course_code,
                    "credit_units": int(units_val) if pd.notna(units_val) else 3,
                    "semester_id": known_semesters.get((sess_name, sem_name)),
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
        sid = row.get("student_id")
        if pd.isna(sid) or sid is None:
            student = upsert_student(
                session=session,
                matric_no=str(row["matric_no"]),
                full_name=str(row.get("full_name") or row["matric_no"]),
                department=str(row.get("department") or "General"),
                level=int(row.get("level") or 100),
                actor=actor,
            )
            sid = student.id

        cid = row.get("course_id")
        if pd.isna(cid) or cid is None:
            course = upsert_course(
                session=session,
                course_code=str(row["course_code"]),
                course_title=str(row.get("course_title") or row["course_code"]),
                credit_units=int(row.get("credit_units") or 3),
                department=str(row.get("department") or "General"),
                level=int(row.get("level") or 100),
                actor=actor,
            )
            cid = course.id

        sem_id = row.get("semester_id")
        if pd.isna(sem_id) or sem_id is None:
            semester = get_or_create_semester(
                session=session,
                session_name=str(row["session_name"]),
                semester_name=str(row["semester_name"]),
                actor=actor,
            )
            sem_id = semester.id

        upsert_result(
            session=session,
            student_id=int(sid),
            course_id=int(cid),
            semester_id=int(sem_id),
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
