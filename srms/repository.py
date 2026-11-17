"""Repository layer for managing students, courses, semesters, results, and audit logs."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from srms.database import AuditLog, Course, Result, Semester, Student
from srms.grading import score_to_grade


def log_audit(
    session: Session,
    action: str,
    entity_type: str,
    entity_ref: str,
    details: str,
    actor: str = "Data Analyst",
) -> None:
    session.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_ref=entity_ref,
            details=details,
            actor=actor,
        )
    )


def upsert_student(
    session: Session,
    matric_no: str,
    full_name: str,
    department: str,
    level: int,
    email: str | None = None,
    actor: str = "Data Analyst",
) -> Student:
    matric_clean = matric_no.strip().upper()
    existing = session.scalar(select(Student).where(Student.matric_no == matric_clean))
    if existing:
        existing.full_name = full_name.strip()
        existing.department = department.strip()
        existing.level = int(level)
        existing.email = email.strip() if email else None
        log_audit(session, "UPDATE", "Student", matric_clean, f"Updated {existing.full_name}", actor)
        session.commit()
        return existing

    student = Student(
        matric_no=matric_clean,
        full_name=full_name.strip(),
        department=department.strip(),
        level=int(level),
        email=email.strip() if email else None,
    )
    session.add(student)
    log_audit(session, "CREATE", "Student", matric_clean, f"Added {student.full_name}", actor)
    session.commit()
    return student


def upsert_course(
    session: Session,
    course_code: str,
    course_title: str,
    credit_units: int,
    department: str,
    level: int,
    actor: str = "Data Analyst",
) -> Course:
    code_clean = course_code.strip().upper()
    existing = session.scalar(select(Course).where(Course.course_code == code_clean))
    if existing:
        existing.course_title = course_title.strip()
        existing.credit_units = int(credit_units)
        existing.department = department.strip()
        existing.level = int(level)
        log_audit(session, "UPDATE", "Course", code_clean, f"Updated {existing.course_title}", actor)
        session.commit()
        return existing

    course = Course(
        course_code=code_clean,
        course_title=course_title.strip(),
        credit_units=int(credit_units),
        department=department.strip(),
        level=int(level),
    )
    session.add(course)
    log_audit(session, "CREATE", "Course", code_clean, f"Added {course.course_title}", actor)
    session.commit()
    return course


def get_or_create_semester(
    session: Session,
    session_name: str,
    semester_name: str,
    actor: str = "Data Analyst",
) -> Semester:
    sess_clean = session_name.strip()
    sem_clean = semester_name.strip()
    existing = session.scalar(
        select(Semester).where(
            Semester.session_name == sess_clean, Semester.semester_name == sem_clean
        )
    )
    if existing:
        return existing

    semester = Semester(session_name=sess_clean, semester_name=sem_clean, is_active=True)
    session.add(semester)
    log_audit(session, "CREATE", "Semester", f"{sess_clean} {sem_clean}", "Created semester", actor)
    session.commit()
    return semester


def upsert_result(
    session: Session,
    student_id: int,
    course_id: int,
    semester_id: int,
    ca_score: float,
    exam_score: float,
    actor: str = "Data Analyst",
) -> Result:
    total = round(float(ca_score) + float(exam_score), 2)
    if total > 100.0 or total < 0.0:
        raise ValueError(f"Total score (CA + Exam) must be 0..100, got {total}.")

    band = score_to_grade(total)
    existing = session.scalar(
        select(Result).where(
            Result.student_id == student_id,
            Result.course_id == course_id,
            Result.semester_id == semester_id,
        )
    )
    if existing:
        old_total = existing.total_score
        existing.ca_score = float(ca_score)
        existing.exam_score = float(exam_score)
        existing.total_score = total
        existing.grade_letter = band.letter
        existing.grade_point = band.points
        existing.remark = band.remark
        log_audit(
            session,
            "UPDATE",
            "Result",
            f"student={student_id},course={course_id},sem={semester_id}",
            f"Score {old_total} -> {total} ({band.letter})",
            actor,
        )
        session.commit()
        return existing

    result = Result(
        student_id=student_id,
        course_id=course_id,
        semester_id=semester_id,
        ca_score=float(ca_score),
        exam_score=float(exam_score),
        total_score=total,
        grade_letter=band.letter,
        grade_point=band.points,
        remark=band.remark,
    )
    session.add(result)
    log_audit(
        session,
        "CREATE",
        "Result",
        f"student={student_id},course={course_id},sem={semester_id}",
        f"Score {total} ({band.letter})",
        actor,
    )
    session.commit()
    return result


def fetch_results_dataframe(session: Session) -> pd.DataFrame:
    """Return a denormalized Pandas DataFrame of all results joined with student, course, semester."""
    query = text(
        """
        SELECT
            r.id AS result_id,
            s.id AS student_id,
            s.matric_no,
            s.full_name,
            s.department,
            s.level,
            sem.id AS semester_id,
            sem.session_name,
            sem.semester_name,
            c.id AS course_id,
            c.course_code,
            c.course_title,
            c.credit_units,
            r.ca_score,
            r.exam_score,
            r.total_score,
            r.grade_letter,
            r.grade_point,
            (c.credit_units * r.grade_point) AS weighted_points,
            r.remark,
            r.updated_at
        FROM results r
        JOIN students s ON s.id = r.student_id
        JOIN courses c ON c.id = r.course_id
        JOIN semesters sem ON sem.id = r.semester_id
        ORDER BY sem.session_name, sem.semester_name, s.matric_no, c.course_code
        """
    )
    return pd.read_sql(query, session.bind)


def fetch_students_dataframe(session: Session) -> pd.DataFrame:
    return pd.read_sql(
        text("SELECT id, matric_no, full_name, department, level, email, created_at FROM students ORDER BY matric_no"),
        session.bind,
    )


def fetch_courses_dataframe(session: Session) -> pd.DataFrame:
    return pd.read_sql(
        text("SELECT id, course_code, course_title, credit_units, department, level FROM courses ORDER BY course_code"),
        session.bind,
    )


def fetch_audit_logs_dataframe(session: Session, limit: int = 200) -> pd.DataFrame:
    return pd.read_sql(
        text(
            "SELECT id, action, entity_type, entity_ref, details, actor, created_at "
            "FROM audit_logs ORDER BY id DESC LIMIT :limit"
        ),
        session.bind,
        params={"limit": limit},
    )
