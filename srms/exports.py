"""Export utilities: formatted Excel broadsheets, Power BI datasets, and PDF transcripts."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from fpdf import FPDF

from srms.analytics import (
    compute_cgpa_table,
    compute_course_statistics,
    compute_semester_gpa_table,
)
from srms.grading import classify_standing


def export_broadsheet_excel(results_df: pd.DataFrame) -> bytes:
    """Generate a multi-sheet Excel workbook (Broadsheet, CGPA Summary, Course Stats, Raw Fact)."""
    cgpa_df = compute_cgpa_table(results_df)
    course_stats_df = compute_course_statistics(results_df)

    if not results_df.empty:
        display_cell = (
            results_df["total_score"].round(0).astype(int).astype(str)
            + " ("
            + results_df["grade_letter"]
            + ")"
        )
        pivot_prep = results_df.assign(score_grade=display_cell)
        broadsheet = pivot_prep.pivot_table(
            index=["matric_no", "full_name", "department", "level"],
            columns="course_code",
            values="score_grade",
            aggfunc="first",
            fill_value="-",
        ).reset_index()
        broadsheet = broadsheet.merge(
            cgpa_df[["matric_no", "total_units_attempted", "total_units_earned", "cgpa", "academic_standing"]],
            on="matric_no",
            how="left",
        )
    else:
        broadsheet = pd.DataFrame()

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        broadsheet.to_excel(writer, index=False, sheet_name="Broadsheet")
        cgpa_df.to_excel(writer, index=False, sheet_name="CGPA_Summary")
        course_stats_df.to_excel(writer, index=False, sheet_name="Course_Analytics")
        results_df.to_excel(writer, index=False, sheet_name="PowerBI_Fact_Results")
    return buf.getvalue()


def export_student_transcript_pdf(results_df: pd.DataFrame, matric_no: str) -> bytes:
    """Generate an official A4 PDF transcript for a single student."""
    student_rows = results_df[results_df["matric_no"] == matric_no].copy()
    if student_rows.empty:
        raise ValueError(f"No results found for student '{matric_no}'.")

    first = student_rows.iloc[0]
    sem_gpa_df = compute_semester_gpa_table(student_rows)
    cgpa_df = compute_cgpa_table(student_rows)
    overall = cgpa_df.iloc[0]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "OFFICIAL ACADEMIC TRANSCRIPT", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Student Result Management System (5.0 GPA Scale)", ln=True, align="C")
    pdf.ln(5)

    # Student metadata
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(35, 7, "Matric No:", border=0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(65, 7, str(first["matric_no"]), border=0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 7, "Department:", border=0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, str(first["department"]), ln=True)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(35, 7, "Full Name:", border=0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(65, 7, str(first["full_name"]), border=0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 7, "Level:", border=0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, str(first["level"]), ln=True)
    pdf.ln(4)

    # Semester sections
    for _, sem_row in sem_gpa_df.iterrows():
        sess = sem_row["session_name"]
        sem = sem_row["semester_name"]
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(235, 240, 248)
        pdf.cell(0, 8, f"Session: {sess} | Semester: {sem}", ln=True, fill=True)

        # Table header
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(25, 7, "Code", border=1)
        pdf.cell(75, 7, "Course Title", border=1)
        pdf.cell(15, 7, "Units", border=1, align="C")
        pdf.cell(18, 7, "Score", border=1, align="C")
        pdf.cell(15, 7, "Grade", border=1, align="C")
        pdf.cell(18, 7, "Points", border=1, align="C")
        pdf.cell(24, 7, "Remark", border=1, align="C", ln=True)

        sub = student_rows[
            (student_rows["session_name"] == sess) & (student_rows["semester_name"] == sem)
        ]
        pdf.set_font("Helvetica", "", 9)
        for _, r in sub.iterrows():
            title = str(r["course_title"])[:38]
            pdf.cell(25, 6.5, str(r["course_code"]), border=1)
            pdf.cell(75, 6.5, title, border=1)
            pdf.cell(15, 6.5, str(int(r["credit_units"])), border=1, align="C")
            pdf.cell(18, 6.5, f"{float(r['total_score']):.1f}", border=1, align="C")
            pdf.cell(15, 6.5, str(r["grade_letter"]), border=1, align="C")
            pdf.cell(18, 6.5, str(int(r["weighted_points"])), border=1, align="C")
            pdf.cell(24, 6.5, str(r["remark"]), border=1, align="C", ln=True)

        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(
            0,
            7,
            f"Semester Units: {int(sem_row['total_units'])} | Units Earned: {int(sem_row['units_earned'])} | Semester GPA: {sem_row['semester_gpa']:.2f}",
            ln=True,
        )
        pdf.ln(3)

    # Cumulative summary
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(220, 235, 225)
    cgpa_val = float(overall["cgpa"])
    standing = classify_standing(cgpa_val)
    pdf.cell(
        0,
        9,
        f"CUMULATIVE GPA (CGPA): {cgpa_val:.2f} / 5.00   |   STANDING: {standing}",
        ln=True,
        fill=True,
        align="C",
    )

    return bytes(pdf.output())
