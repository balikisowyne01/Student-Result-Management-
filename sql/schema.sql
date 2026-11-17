-- PostgreSQL Schema for Student Result Management System (SRMS)
-- Standard 5.0 GPA Scale

CREATE TABLE IF NOT EXISTS students (
    id              SERIAL PRIMARY KEY,
    matric_no       VARCHAR(32) UNIQUE NOT NULL,
    full_name       VARCHAR(120) NOT NULL,
    department      VARCHAR(80) NOT NULL,
    level           INTEGER NOT NULL DEFAULT 100 CHECK (level IN (100, 200, 300, 400, 500, 600)),
    email           VARCHAR(120),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_students_department ON students (department);

CREATE TABLE IF NOT EXISTS courses (
    id              SERIAL PRIMARY KEY,
    course_code     VARCHAR(20) UNIQUE NOT NULL,
    course_title    VARCHAR(150) NOT NULL,
    credit_units    INTEGER NOT NULL CHECK (credit_units > 0 AND credit_units <= 12),
    department      VARCHAR(80) NOT NULL,
    level           INTEGER NOT NULL DEFAULT 100 CHECK (level IN (100, 200, 300, 400, 500, 600))
);

CREATE INDEX IF NOT EXISTS idx_courses_department ON courses (department);

CREATE TABLE IF NOT EXISTS semesters (
    id              SERIAL PRIMARY KEY,
    session_name    VARCHAR(20) NOT NULL,
    semester_name   VARCHAR(20) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_session_semester UNIQUE (session_name, semester_name)
);

CREATE TABLE IF NOT EXISTS results (
    id              SERIAL PRIMARY KEY,
    student_id      INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id       INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    semester_id     INTEGER NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    ca_score        DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (ca_score >= 0 AND ca_score <= 40),
    exam_score      DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (exam_score >= 0 AND exam_score <= 100),
    total_score     DOUBLE PRECISION NOT NULL CHECK (total_score >= 0 AND total_score <= 100),
    grade_letter    VARCHAR(2) NOT NULL CHECK (grade_letter IN ('A', 'B', 'C', 'D', 'E', 'F')),
    grade_point     INTEGER NOT NULL CHECK (grade_point BETWEEN 0 AND 5),
    remark          VARCHAR(30) NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_student_course_semester UNIQUE (student_id, course_id, semester_id)
);

CREATE INDEX IF NOT EXISTS idx_results_student ON results (student_id);
CREATE INDEX IF NOT EXISTS idx_results_course ON results (course_id);
CREATE INDEX IF NOT EXISTS idx_results_semester ON results (semester_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id              SERIAL PRIMARY KEY,
    action          VARCHAR(50) NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,
    entity_ref      VARCHAR(120) NOT NULL,
    details         TEXT NOT NULL,
    actor           VARCHAR(80) NOT NULL DEFAULT 'Data Analyst',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
