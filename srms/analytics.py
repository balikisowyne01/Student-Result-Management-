"""Pandas and NumPy analytics engine for GPA/CGPA, course statistics, and cohort insights."""

from __future__ import annotations

import numpy as np
import pandas as pd

from srms.grading import classify_standing


def compute_semester_gpa_table(results_df: pd.DataFrame) -> pd.DataFrame:
    """Compute weighted GPA per student per semester."""
    if results_df.empty:
        return pd.DataFrame(
            columns=[
                "matric_no",
                "full_name",
                "department",
                "level",
                "session_name",
                "semester_name",
                "courses_taken",
                "total_units",
                "units_earned",
                "weighted_points",
                "semester_gpa",
            ]
        )

    work = results_df.copy()
    work["units_earned_row"] = np.where(work["grade_letter"] != "F", work["credit_units"], 0)

    grouped = (
        work.groupby(
            ["matric_no", "full_name", "department", "level", "session_name", "semester_name"],
            as_index=False,
        )
        .agg(
            courses_taken=("course_code", "count"),
            total_units=("credit_units", "sum"),
            units_earned=("units_earned_row", "sum"),
            weighted_points=("weighted_points", "sum"),
        )
    )
    grouped["semester_gpa"] = np.where(
        grouped["total_units"] > 0,
        (grouped["weighted_points"] / grouped["total_units"]).round(2),
        0.0,
    )
    return grouped.sort_values(["session_name", "semester_name", "matric_no"]).reset_index(drop=True)


def compute_cgpa_table(results_df: pd.DataFrame) -> pd.DataFrame:
    """Compute cumulative CGPA, carry-over count, and academic standing per student."""
    if results_df.empty:
        return pd.DataFrame(
            columns=[
                "matric_no",
                "full_name",
                "department",
                "level",
                "total_courses",
                "total_units_attempted",
                "total_units_earned",
                "carryover_count",
                "cgpa",
                "academic_standing",
            ]
        )

    work = results_df.copy()
    work["units_earned_row"] = np.where(work["grade_letter"] != "F", work["credit_units"], 0)
    work["is_fail"] = (work["grade_letter"] == "F").astype(int)

    grouped = (
        work.groupby(["matric_no", "full_name", "department", "level"], as_index=False)
        .agg(
            total_courses=("course_code", "count"),
            total_units_attempted=("credit_units", "sum"),
            total_units_earned=("units_earned_row", "sum"),
            weighted_points=("weighted_points", "sum"),
            carryover_count=("is_fail", "sum"),
        )
    )
    grouped["cgpa"] = np.where(
        grouped["total_units_attempted"] > 0,
        (grouped["weighted_points"] / grouped["total_units_attempted"]).round(2),
        0.0,
    )
    grouped["academic_standing"] = grouped["cgpa"].apply(classify_standing)
    return grouped.drop(columns=["weighted_points"]).sort_values(
        ["cgpa", "matric_no"], ascending=[False, True]
    ).reset_index(drop=True)


def compute_course_statistics(results_df: pd.DataFrame) -> pd.DataFrame:
    """Compute descriptive statistics and pass rates per course."""
    if results_df.empty:
        return pd.DataFrame(
            columns=[
                "course_code",
                "course_title",
                "credit_units",
                "enrolled",
                "mean_score",
                "median_score",
                "std_dev",
                "min_score",
                "max_score",
                "pass_rate_pct",
            ]
        )

    work = results_df.copy()
    work["passed"] = (work["grade_letter"] != "F").astype(int)

    stats = (
        work.groupby(["course_code", "course_title", "credit_units"], as_index=False)
        .agg(
            enrolled=("total_score", "count"),
            mean_score=("total_score", "mean"),
            median_score=("total_score", "median"),
            std_dev=("total_score", lambda s: float(np.std(s, ddof=0))),
            min_score=("total_score", "min"),
            max_score=("total_score", "max"),
            pass_count=("passed", "sum"),
        )
    )
    stats["pass_rate_pct"] = ((stats["pass_count"] / stats["enrolled"]) * 100.0).round(2)
    for col in ("mean_score", "median_score", "std_dev", "min_score", "max_score"):
        stats[col] = stats[col].round(2)
    return stats.drop(columns=["pass_count"]).sort_values("course_code").reset_index(drop=True)


def identify_at_risk_students(
    cgpa_df: pd.DataFrame, cgpa_threshold: float = 1.50, min_carryovers: int = 2
) -> pd.DataFrame:
    """Flag students whose CGPA falls below threshold or who have multiple carry-overs."""
    if cgpa_df.empty:
        return cgpa_df.copy()

    mask = (cgpa_df["cgpa"] < cgpa_threshold) | (cgpa_df["carryover_count"] >= min_carryovers)
    return cgpa_df.loc[mask].sort_values(["cgpa", "carryover_count"], ascending=[True, False]).reset_index(drop=True)
