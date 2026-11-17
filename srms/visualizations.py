"""Matplotlib and Seaborn visualization generators for student result analytics."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set_theme(style="whitegrid", palette="muted")

GRADE_ORDER = ["A", "B", "C", "D", "E", "F"]
GRADE_PALETTE = {
    "A": "#1b9e77",
    "B": "#2b8cbe",
    "C": "#756bb1",
    "D": "#e6ab02",
    "E": "#d95f02",
    "F": "#e41a1c",
}


def plot_grade_distribution(results_df: pd.DataFrame) -> plt.Figure:
    """Bar chart of grade counts (A-F) using Seaborn."""
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=120)
    counts = results_df["grade_letter"].value_counts().reindex(GRADE_ORDER, fill_value=0)
    colors = [GRADE_PALETTE[g] for g in counts.index]
    bars = ax.bar(counts.index, counts.values, color=colors, edgecolor="#333333", linewidth=0.6)

    total = max(int(counts.sum()), 1)
    for bar, val in zip(bars, counts.values):
        pct = (val / total) * 100
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(counts.max() * 0.02, 0.2),
            f"{int(val)}\n({pct:.1f}%)",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )

    ax.set_title("Grade Distribution (5.0 Scale)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Grade Letter")
    ax.set_ylabel("Number of Results")
    ax.set_ylim(0, max(counts.max() * 1.18, 1))
    fig.tight_layout()
    return fig


def plot_score_histogram_kde(results_df: pd.DataFrame) -> plt.Figure:
    """Histogram with KDE curve and mean/median markers for total scores."""
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=120)
    sns.histplot(
        data=results_df,
        x="total_score",
        bins=15,
        kde=True,
        color="#2b8cbe",
        ax=ax,
    )
    mean_val = results_df["total_score"].mean()
    median_val = results_df["total_score"].median()
    ax.axvline(mean_val, color="#d95f02", linestyle="--", linewidth=1.6, label=f"Mean: {mean_val:.1f}")
    ax.axvline(median_val, color="#1b9e77", linestyle="-.", linewidth=1.6, label=f"Median: {median_val:.1f}")
    ax.axvline(40.0, color="#e41a1c", linestyle=":", linewidth=1.4, label="Pass Mark (40)")

    ax.set_title("Total Score Distribution", fontsize=12, fontweight="bold")
    ax.set_xlabel("Total Score (0-100)")
    ax.set_ylabel("Frequency")
    ax.set_xlim(0, 100)
    ax.legend(fontsize=8.5)
    fig.tight_layout()
    return fig


def plot_department_cgpa_boxplot(cgpa_df: pd.DataFrame) -> plt.Figure:
    """Boxplot of student CGPA grouped by department."""
    fig, ax = plt.subplots(figsize=(7.5, 4.4), dpi=120)
    sns.boxplot(data=cgpa_df, x="department", y="cgpa", palette="Set2", ax=ax)
    sns.stripplot(data=cgpa_df, x="department", y="cgpa", color="#222222", alpha=0.55, size=4, ax=ax)

    ax.set_title("CGPA Distribution by Department", fontsize=12, fontweight="bold")
    ax.set_xlabel("Department")
    ax.set_ylabel("CGPA (5.0 Scale)")
    ax.set_ylim(0, 5.2)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    return fig


def plot_course_pass_rates(course_stats_df: pd.DataFrame) -> plt.Figure:
    """Horizontal bar chart of course pass rates (%)."""
    sorted_df = course_stats_df.sort_values("pass_rate_pct", ascending=True)
    fig, ax = plt.subplots(figsize=(7.5, max(3.8, len(sorted_df) * 0.45)), dpi=120)
    bars = ax.barh(sorted_df["course_code"], sorted_df["pass_rate_pct"], color="#2b8cbe", edgecolor="#333333")
    for bar, val in zip(bars, sorted_df["pass_rate_pct"]):
        ax.text(
            min(val + 1.5, 98),
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%",
            va="center",
            fontsize=8.5,
        )

    ax.set_title("Course Pass Rate (%)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Pass Rate (%)")
    ax.set_ylabel("Course Code")
    ax.set_xlim(0, 108)
    fig.tight_layout()
    return fig


def plot_ca_vs_exam_scatter(results_df: pd.DataFrame) -> plt.Figure:
    """Scatter + linear regression trend of CA Score vs Exam Score."""
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=120)
    sns.regplot(
        data=results_df,
        x="ca_score",
        y="exam_score",
        scatter_kws={"alpha": 0.65, "color": "#2b8cbe"},
        line_kws={"color": "#d95f02", "linewidth": 1.8},
        ax=ax,
    )
    ax.set_title("CA Score vs. Exam Score Correlation", fontsize=12, fontweight="bold")
    ax.set_xlabel("Continuous Assessment (CA)")
    ax.set_ylabel("Exam Score")
    fig.tight_layout()
    return fig
