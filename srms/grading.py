"""5.0 GPA scale grading engine, GPA/CGPA calculations, and academic standing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GradeBand:
    min_score: float
    max_score: float
    letter: str
    points: int
    remark: str


FIVE_POINT_SCALE: tuple[GradeBand, ...] = (
    GradeBand(70.0, 100.0, "A", 5, "Excellent"),
    GradeBand(60.0, 69.9999, "B", 4, "Very Good"),
    GradeBand(50.0, 59.9999, "C", 3, "Good"),
    GradeBand(45.0, 49.9999, "D", 2, "Fair"),
    GradeBand(40.0, 44.9999, "E", 1, "Pass"),
    GradeBand(0.0, 39.9999, "F", 0, "Fail"),
)


def score_to_grade(score: float) -> GradeBand:
    """Map a numeric score (0-100) to its 5.0 scale GradeBand."""
    if score < 0 or score > 100:
        raise ValueError(f"Score must be between 0 and 100, got {score}.")
    for band in FIVE_POINT_SCALE:
        if band.min_score <= score <= band.max_score:
            return band
    # Fallback for boundary precision at 100.0
    return FIVE_POINT_SCALE[0]


def calculate_gpa(records: Iterable[tuple[int, int]]) -> float:
    """Compute weighted GPA from an iterable of (credit_units, grade_points).

    Returns 0.00 if total credit units is 0.
    """
    total_units = 0
    total_weighted_points = 0
    for units, points in records:
        if units < 0:
            raise ValueError(f"Credit units cannot be negative, got {units}.")
        total_units += units
        total_weighted_points += units * points

    if total_units == 0:
        return 0.0
    return round(total_weighted_points / total_units, 2)


def classify_standing(cgpa: float) -> str:
    """Classify academic standing on the standard 5.0 GPA scale."""
    if cgpa >= 4.50:
        return "First Class"
    if cgpa >= 3.50:
        return "Second Class Upper"
    if cgpa >= 2.50:
        return "Second Class Lower"
    if cgpa >= 1.50:
        return "Third Class"
    if cgpa >= 1.00:
        return "Pass"
    return "Probation / Fail"
