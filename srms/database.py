"""SQLAlchemy database configuration and normalized relational models."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "srms.db"
DATABASE_URL = os.getenv("SRMS_DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    matric_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    department: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    results: Mapped[list["Result"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    course_title: Mapped[str] = mapped_column(String(150), nullable=False)
    credit_units: Mapped[int] = mapped_column(Integer, nullable=False)
    department: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    results: Mapped[list["Result"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Semester(Base):
    __tablename__ = "semesters"
    __table_args__ = (UniqueConstraint("session_name", "semester_name", name="uq_session_semester"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_name: Mapped[str] = mapped_column(String(20), nullable=False)
    semester_name: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    results: Mapped[list["Result"]] = relationship(
        back_populates="semester", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        return f"{self.session_name} - {self.semester_name}"


class Result(Base):
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "semester_id", name="uq_student_course_semester"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False)

    ca_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    exam_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    grade_letter: Mapped[str] = mapped_column(String(2), nullable=False)
    grade_point: Mapped[int] = mapped_column(Integer, nullable=False)
    remark: Mapped[str] = mapped_column(String(30), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    student: Mapped["Student"] = relationship(back_populates="results")
    course: Mapped["Course"] = relationship(back_populates="results")
    semester: Mapped["Semester"] = relationship(back_populates="results")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False, default="Data Analyst")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


def init_db(target_engine=engine) -> None:
    """Create all database tables if they do not exist."""
    Base.metadata.create_all(bind=target_engine)


def get_session() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
