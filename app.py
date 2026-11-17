"""Student Result Management System (SRMS) - Data Analyst Workbench."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import select

from srms.analytics import (
    compute_cgpa_table,
    compute_course_statistics,
    compute_semester_gpa_table,
    identify_at_risk_students,
)
from srms.database import DATABASE_URL, Course, Semester, SessionLocal, Student, init_db
from srms.etl import (
    commit_validated_scores,
    generate_score_template_csv,
    generate_score_template_excel,
    load_tabular_file,
    validate_score_dataframe,
)
from srms.exports import export_broadsheet_excel, export_student_transcript_pdf
from srms.repository import (
    fetch_audit_logs_dataframe,
    fetch_courses_dataframe,
    fetch_results_dataframe,
    fetch_students_dataframe,
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

st.set_page_config(
    page_title="SRMS | Data Analyst Workbench",
    page_icon="📊",
    layout="wide",
)

init_db()


def _db_backend_label() -> str:
    return "PostgreSQL" if DATABASE_URL.startswith("postgresql") else "SQLite (Local)"


st.sidebar.title("SRMS Analytics")
st.sidebar.caption(f"Database: **{_db_backend_label()}** | Scale: **5.0 GPA**")

page = st.sidebar.radio(
    "Navigation",
    [
        "Analytics Dashboard",
        "Manage Records (SQL)",
        "Bulk Score ETL (Pandas)",
        "Broadsheet & Transcripts",
        "Power BI & PostgreSQL",
        "Audit Log",
    ],
)

with SessionLocal() as session:
    results_df = fetch_results_dataframe(session)
    students_df = fetch_students_dataframe(session)
    courses_df = fetch_courses_dataframe(session)

    if page == "Analytics Dashboard":
        st.title("Student Performance & Analytics Dashboard")
        if results_df.empty:
            st.info(
                "No result records found yet. Add students, courses, and scores in "
                "**Manage Records (SQL)** or upload a score sheet in **Bulk Score ETL (Pandas)**."
            )
        else:
            cgpa_df = compute_cgpa_table(results_df)
            course_stats_df = compute_course_statistics(results_df)

            pass_rate = (results_df["grade_letter"] != "F").mean() * 100.0
            avg_cgpa = cgpa_df["cgpa"].mean()
            at_risk_df = identify_at_risk_students(cgpa_df)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Students Evaluated", len(cgpa_df))
            c2.metric("Result Records", len(results_df))
            c3.metric("Mean CGPA (5.0)", f"{avg_cgpa:.2f}")
            c4.metric("Overall Pass Rate", f"{pass_rate:.1f}%")

            col_a, col_b = st.columns(2)
            with col_a:
                st.pyplot(plot_grade_distribution(results_df))
            with col_b:
                st.pyplot(plot_score_histogram_kde(results_df))

            col_c, col_d = st.columns(2)
            with col_c:
                st.pyplot(plot_department_cgpa_boxplot(cgpa_df))
            with col_d:
                st.pyplot(plot_course_pass_rates(course_stats_df))

            st.subheader("CA vs. Exam Score Correlation")
            st.pyplot(plot_ca_vs_exam_scatter(results_df))

            st.subheader("Course Statistical Summary")
            st.dataframe(course_stats_df, use_container_width=True, hide_index=True)

            st.subheader("At-Risk Students (CGPA < 1.50 or >= 2 Carry-Overs)")
            if at_risk_df.empty:
                st.success("No students currently flagged as at-risk.")
            else:
                st.dataframe(at_risk_df, use_container_width=True, hide_index=True)

    elif page == "Manage Records (SQL)":
        st.title("Manage Academic Records")
        tab_stu, tab_crs, tab_sem, tab_res = st.tabs(
            ["Students", "Courses", "Semesters", "Single Result Entry"]
        )

        with tab_stu:
            with st.form("student_form", clear_on_submit=True):
                st.subheader("Add or Update Student")
                col1, col2 = st.columns(2)
                matric_no = col1.text_input("Matric Number", placeholder="e.g. CSC/2023/001")
                full_name = col2.text_input("Full Name")
                department = col1.text_input("Department", placeholder="e.g. Computer Science")
                level = col2.selectbox("Level", [100, 200, 300, 400, 500, 600])
                email = st.text_input("Email (optional)")
                if st.form_submit_button("Save Student"):
                    if not matric_no.strip() or not full_name.strip() or not department.strip():
                        st.error("Matric Number, Full Name, and Department are required.")
                    else:
                        upsert_student(session, matric_no, full_name, department, level, email or None)
                        st.success(f"Saved student {matric_no.strip().upper()}.")
                        st.rerun()

            if students_df.empty:
                st.info("No students registered yet.")
            else:
                st.dataframe(students_df, use_container_width=True, hide_index=True)

        with tab_crs:
            with st.form("course_form", clear_on_submit=True):
                st.subheader("Add or Update Course")
                col1, col2 = st.columns(2)
                course_code = col1.text_input("Course Code", placeholder="e.g. CSC201")
                course_title = col2.text_input("Course Title", placeholder="e.g. Data Structures")
                credit_units = col1.number_input("Credit Units", min_value=1, max_value=12, value=3)
                department = col2.text_input("Department", placeholder="e.g. Computer Science")
                level = st.selectbox("Course Level", [100, 200, 300, 400, 500, 600])
                if st.form_submit_button("Save Course"):
                    if not course_code.strip() or not course_title.strip() or not department.strip():
                        st.error("Course Code, Title, and Department are required.")
                    else:
                        upsert_course(
                            session, course_code, course_title, int(credit_units), department, int(level)
                        )
                        st.success(f"Saved course {course_code.strip().upper()}.")
                        st.rerun()

            if courses_df.empty:
                st.info("No courses registered yet.")
            else:
                st.dataframe(courses_df, use_container_width=True, hide_index=True)

        with tab_sem:
            with st.form("semester_form", clear_on_submit=True):
                st.subheader("Create Academic Semester")
                col1, col2 = st.columns(2)
                session_name = col1.text_input("Session", placeholder="e.g. 2025/2026")
                semester_name = col2.selectbox("Semester", ["First", "Second", "Summer"])
                if st.form_submit_button("Create Semester"):
                    if not session_name.strip():
                        st.error("Session name is required.")
                    else:
                        get_or_create_semester(session, session_name, semester_name)
                        st.success(f"Semester '{session_name.strip()} - {semester_name}' ready.")
                        st.rerun()

            semesters = session.scalars(select(Semester).order_by(Semester.session_name)).all()
            if not semesters:
                st.info("No semesters created yet.")
            else:
                st.table(
                    [{"ID": s.id, "Session": s.session_name, "Semester": s.semester_name} for s in semesters]
                )

        with tab_res:
            students = session.scalars(select(Student).order_by(Student.matric_no)).all()
            courses = session.scalars(select(Course).order_by(Course.course_code)).all()
            semesters = session.scalars(select(Semester).order_by(Semester.session_name)).all()

            if not students or not courses or not semesters:
                st.info("Create at least one Student, Course, and Semester before entering scores.")
            else:
                with st.form("result_form"):
                    st.subheader("Enter or Update Score")
                    s_map = {f"{s.matric_no} - {s.full_name}": s.id for s in students}
                    c_map = {f"{c.course_code} - {c.course_title} ({c.credit_units}u)": c.id for c in courses}
                    sem_map = {s.label: s.id for s in semesters}

                    sel_stu = st.selectbox("Student", list(s_map.keys()))
                    sel_crs = st.selectbox("Course", list(c_map.keys()))
                    sel_sem = st.selectbox("Semester", list(sem_map.keys()))
                    col1, col2 = st.columns(2)
                    ca_score = col1.number_input("CA Score (0-40)", min_value=0.0, max_value=40.0, value=0.0, step=0.5)
                    exam_score = col2.number_input("Exam Score (0-100)", min_value=0.0, max_value=100.0, value=0.0, step=0.5)

                    if st.form_submit_button("Save Result"):
                        try:
                            res = upsert_result(
                                session,
                                s_map[sel_stu],
                                c_map[sel_crs],
                                sem_map[sel_sem],
                                ca_score,
                                exam_score,
                            )
                            st.success(f"Saved result: Total {res.total_score:.1f} -> Grade {res.grade_letter} ({res.grade_point} pts)")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

    elif page == "Bulk Score ETL (Pandas)":
        st.title("Bulk Score Upload & Pandas Validation")
        st.write("Download a standardized template, populate scores, and run automated validation before committing.")

        d1, d2 = st.columns(2)
        d1.download_button(
            "Download Excel Template (.xlsx)",
            data=generate_score_template_excel(),
            file_name="srms_score_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        d2.download_button(
            "Download CSV Template (.csv)",
            data=generate_score_template_csv(),
            file_name="srms_score_template.csv",
            mime="text/csv",
        )

        auto_register = st.checkbox(
            "Auto-register missing Students, Courses & Semesters found in this file",
            value=True,
            help="Uncheck to strictly require Students, Courses, and Semesters to be pre-registered.",
        )

        uploaded = st.file_uploader("Upload Score Sheet (.csv or .xlsx)", type=["csv", "xlsx", "xls"])
        if uploaded is not None:
            try:
                raw_df = load_tabular_file(uploaded, uploaded.name)
                report = validate_score_dataframe(raw_df, session, auto_register=auto_register)

                m1, m2, m3 = st.columns(3)
                m1.metric("Total Rows", report.total_rows)
                m2.metric("Valid Rows", len(report.valid_df))
                m3.metric("Error Rows", len(report.errors_df))

                if not report.errors_df.empty:
                    st.error("Validation errors detected. Fix these rows or commit only valid rows.")
                    st.dataframe(report.errors_df, use_container_width=True, hide_index=True)

                if not report.valid_df.empty:
                    st.subheader("Validated Preview")
                    st.dataframe(report.valid_df, use_container_width=True, hide_index=True)
                    if st.button("Commit Validated Scores to Database", type="primary"):
                        committed = commit_validated_scores(report.valid_df, session)
                        st.success(f"Committed {committed} score records successfully.")
                        st.rerun()
            except ValueError as exc:
                st.error(f"ETL Error: {exc}")

    elif page == "Broadsheet & Transcripts":
        st.title("Result Broadsheet & Official PDF Transcripts")
        if results_df.empty:
            st.info("No results available yet to generate broadsheets or transcripts.")
        else:
            depts = ["All"] + sorted(results_df["department"].unique().tolist())
            sel_dept = st.selectbox("Filter by Department", depts)
            filtered_df = (
                results_df if sel_dept == "All" else results_df[results_df["department"] == sel_dept]
            )

            cgpa_df = compute_cgpa_table(filtered_df)
            sem_gpa_df = compute_semester_gpa_table(filtered_df)

            st.download_button(
                "Export Excel Broadsheet & Power BI Workbook (.xlsx)",
                data=export_broadsheet_excel(filtered_df),
                file_name="srms_broadsheet_and_analytics.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            st.subheader("Cumulative GPA & Academic Standing")
            st.dataframe(cgpa_df, use_container_width=True, hide_index=True)

            st.subheader("Semester-by-Semester GPA")
            st.dataframe(sem_gpa_df, use_container_width=True, hide_index=True)

            st.subheader("Generate Individual PDF Transcript")
            matric_options = sorted(filtered_df["matric_no"].unique().tolist())
            sel_matric = st.selectbox("Select Student Matric No", matric_options)
            if sel_matric:
                pdf_bytes = export_student_transcript_pdf(results_df, sel_matric)
                st.download_button(
                    f"Download Official Transcript ({sel_matric}.pdf)",
                    data=pdf_bytes,
                    file_name=f"transcript_{sel_matric.replace('/', '_')}.pdf",
                    mime="application/pdf",
                )

    elif page == "Power BI & PostgreSQL":
        st.title("Power BI & PostgreSQL Integration")
        st.markdown(
            f"""
            **Active Database Backend:** `{_db_backend_label()}`

            ### Connecting to PostgreSQL
            1. Create your database in PostgreSQL (e.g., `CREATE DATABASE srms_db;`).
            2. Run [sql/schema.sql](sql/schema.sql) and [sql/views.sql](sql/views.sql) against `srms_db`.
            3. Set the environment variable before launching the app:
               ```powershell
               $env:SRMS_DATABASE_URL="postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/srms_db"
               ```

            ### Connecting Power BI Desktop
            * **Direct Database Connection (Recommended):** In Power BI Desktop, choose **Get Data -> PostgreSQL database**, connect to `srms_db`, and import these analytical views:
              * `vw_result_fact` (Granular course-level fact table)
              * `vw_student_semester_gpa` (Semester GPA trends)
              * `vw_student_cgpa_standing` (Cumulative CGPA, carry-overs & class standing)
              * `vw_course_performance` (Course pass rates, averages & std dev)
            * **File Export:** Alternatively, download the **Power BI Fact Dataset (.csv)** below.
            """
        )
        if not results_df.empty:
            st.download_button(
                "Download Power BI Fact Dataset (.csv)",
                data=results_df.to_csv(index=False).encode("utf-8"),
                file_name="powerbi_srms_fact_results.csv",
                mime="text/csv",
            )

    elif page == "Audit Log":
        st.title("Immutable Audit Trail")
        audit_df = fetch_audit_logs_dataframe(session)
        if audit_df.empty:
            st.info("No audit events recorded yet.")
        else:
            st.dataframe(audit_df, use_container_width=True, hide_index=True)
