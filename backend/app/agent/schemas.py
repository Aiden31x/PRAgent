"""Pydantic models for parsing the agent's REVIEW_COMPLETE JSON output.

These schemas validate the structured output from the ReAct loop and provide
a clean bridge to the SQLAlchemy ORM models in app.models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import ReviewCategory, Severity

SEVERITY_VALUES = Literal["critical", "warning", "info"]

CATEGORY_VALUES = Literal[
    "Security",
    "Bug",
    "Performance",
    "Error Handling",
    "Code Quality",
    "Test Coverage",
]

CATEGORY_TO_ENUM: dict[str, ReviewCategory] = {
    "Security": ReviewCategory.SECURITY,
    "Bug": ReviewCategory.BUG,
    "Performance": ReviewCategory.PERFORMANCE,
    "Error Handling": ReviewCategory.ERROR_HANDLING,
    "Code Quality": ReviewCategory.CODE_QUALITY,
    "Test Coverage": ReviewCategory.TEST_COVERAGE,
}

SEVERITY_TO_ENUM: dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "warning": Severity.WARNING,
    "info": Severity.INFO,
}


class ReviewStats(BaseModel):
    critical: int = 0
    warning: int = 0
    info: int = 0


class ReviewCommentSchema(BaseModel):
    file: str
    line: int
    severity: SEVERITY_VALUES
    category: CATEGORY_VALUES
    comment: str
    suggestion: str = ""
    open_issue: bool = False

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        mapping = {
            "security": "Security",
            "bug": "Bug",
            "performance": "Performance",
            "error handling": "Error Handling",
            "error_handling": "Error Handling",
            "code quality": "Code Quality",
            "code_quality": "Code Quality",
            "test coverage": "Test Coverage",
            "test_coverage": "Test Coverage",
        }
        return mapping.get(v.lower().strip(), v)

    @property
    def severity_enum(self) -> Severity:
        return SEVERITY_TO_ENUM[self.severity]

    @property
    def category_enum(self) -> ReviewCategory:
        return CATEGORY_TO_ENUM[self.category]


class IssueToOpen(BaseModel):
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)


class ReviewOutput(BaseModel):
    summary: str
    pr_type: str = "mixed"
    stats: ReviewStats = Field(default_factory=ReviewStats)
    comments: list[ReviewCommentSchema] = Field(default_factory=list)
    issues_to_open: list[IssueToOpen] = Field(default_factory=list)

    @field_validator("pr_type", mode="before")
    @classmethod
    def normalize_pr_type(cls, v: str) -> str:
        allowed = {
            "feature", "bugfix", "refactor",
            "dependency_update", "config_change", "docs", "mixed",
        }
        normalized = v.lower().strip().replace(" ", "_").replace("-", "_")
        return normalized if normalized in allowed else "mixed"

    def recompute_stats(self) -> ReviewStats:
        """Recount stats from actual comments, overriding whatever the LLM said."""
        counts = {"critical": 0, "warning": 0, "info": 0}
        for c in self.comments:
            counts[c.severity] += 1
        self.stats = ReviewStats(**counts)
        return self.stats
