-- Power BI & Analytics SQL Views (PostgreSQL)
-- Connect Power BI Desktop directly to PostgreSQL and select these views.

CREATE OR REPLACE VIEW vw_result_fact AS
SELECT
    r.id                    AS result_id,
    s.matric_no,
    s.full_name,
    s.department            AS student_department,
    s.level                 AS student_level,
    sem.session_name,
    sem.semester_name,
    c.course_code,
    c.course_title,
    c.credit_units,
    c.department            AS course_department,
    r.ca_score,
    r.exam_score,
    r.total_score,
    r.grade_letter,
    r.grade_point,
    (c.credit_units * r.grade_point) AS weighted_points,
    CASE WHEN r.grade_letter = 'F' THEN 0 ELSE 1 END AS is_passed,
    r.remark,
    r.updated_at
FROM results r
JOIN students s   ON s.id = r.student_id
JOIN courses c    ON c.id = r.course_id
JOIN semesters sem ON sem.id = r.semester_id;

CREATE OR REPLACE VIEW vw_student_semester_gpa AS
SELECT
    s.id                    AS student_id,
    s.matric_no,
    s.full_name,
    s.department,
    s.level,
    sem.id                  AS semester_id,
    sem.session_name,
    sem.semester_name,
    COUNT(r.id)             AS courses_taken,
    SUM(c.credit_units)     AS total_units,
    SUM(CASE WHEN r.grade_letter <> 'F' THEN c.credit_units ELSE 0 END) AS units_earned,
    SUM(c.credit_units * r.grade_point) AS total_weighted_points,
    ROUND(
        (SUM(c.credit_units * r.grade_point)::NUMERIC / NULLIF(SUM(c.credit_units), 0)),
        2
    ) AS semester_gpa
FROM results r
JOIN students s    ON s.id = r.student_id
JOIN courses c     ON c.id = r.course_id
JOIN semesters sem ON sem.id = r.semester_id
GROUP BY s.id, s.matric_no, s.full_name, s.department, s.level, sem.id, sem.session_name, sem.semester_name;

CREATE OR REPLACE VIEW vw_student_cgpa_standing AS
WITH agg AS (
    SELECT
        s.id                AS student_id,
        s.matric_no,
        s.full_name,
        s.department,
        s.level,
        COUNT(r.id)         AS total_courses,
        SUM(c.credit_units) AS total_units_attempted,
        SUM(CASE WHEN r.grade_letter <> 'F' THEN c.credit_units ELSE 0 END) AS total_units_earned,
        SUM(CASE WHEN r.grade_letter = 'F' THEN 1 ELSE 0 END) AS carryover_count,
        ROUND(
            (SUM(c.credit_units * r.grade_point)::NUMERIC / NULLIF(SUM(c.credit_units), 0)),
            2
        ) AS cgpa
    FROM students s
    LEFT JOIN results r ON r.student_id = s.id
    LEFT JOIN courses c ON c.id = r.course_id
    GROUP BY s.id, s.matric_no, s.full_name, s.department, s.level
)
SELECT
    *,
    CASE
        WHEN cgpa IS NULL THEN 'No Results'
        WHEN cgpa >= 4.50 THEN 'First Class'
        WHEN cgpa >= 3.50 THEN 'Second Class Upper'
        WHEN cgpa >= 2.50 THEN 'Second Class Lower'
        WHEN cgpa >= 1.50 THEN 'Third Class'
        WHEN cgpa >= 1.00 THEN 'Pass'
        ELSE 'Probation / Fail'
    END AS academic_standing
FROM agg;

CREATE OR REPLACE VIEW vw_course_performance AS
SELECT
    c.course_code,
    c.course_title,
    c.credit_units,
    c.department,
    c.level,
    sem.session_name,
    sem.semester_name,
    COUNT(r.id) AS enrollment_count,
    ROUND(AVG(r.total_score)::NUMERIC, 2) AS avg_score,
    ROUND(MIN(r.total_score)::NUMERIC, 2) AS min_score,
    ROUND(MAX(r.total_score)::NUMERIC, 2) AS max_score,
    ROUND(STDDEV_POP(r.total_score)::NUMERIC, 2) AS std_dev_score,
    ROUND(
        100.0 * SUM(CASE WHEN r.grade_letter <> 'F' THEN 1 ELSE 0 END) / NULLIF(COUNT(r.id), 0),
        2
    ) AS pass_rate_pct
FROM results r
JOIN courses c     ON c.id = r.course_id
JOIN semesters sem ON sem.id = r.semester_id
GROUP BY c.course_code, c.course_title, c.credit_units, c.department, c.level, sem.session_name, sem.semester_name;
