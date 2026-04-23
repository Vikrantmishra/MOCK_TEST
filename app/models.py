from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

Difficulty = Literal["easy", "medium", "hard"]


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: HttpUrl
    publisher: str
    published_on: date


class QuestionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    exam: Literal["ssc"] = "ssc"
    as_of_date: date
    category: str
    difficulty: Difficulty
    fact: str
    question: str
    options: list[str]
    correct_answer: str
    explanation: str
    tags: list[str] = Field(default_factory=list)
    source: SourceInfo

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: list[str]) -> list[str]:
        if len(value) != 4:
            raise ValueError("Each question must have exactly four options.")
        if len(set(value)) != 4:
            raise ValueError("Question options must be unique.")
        return value

    @model_validator(mode="after")
    def validate_correct_answer(self) -> "QuestionRecord":
        if self.correct_answer not in self.options:
            raise ValueError("correct_answer must be present in options.")
        return self


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    exam: Literal["ssc"]
    as_of_date: date
    category: str
    difficulty: Difficulty
    fact: str
    question: str
    options: list[str]
    answer_index: int
    answer: str
    explanation: str | None = None
    tags: list[str]
    source: SourceInfo | None = None


class QuestionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_available: int
    returned: int
    as_of_date: date
    questions: list[GeneratedQuestion]


class CategorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    question_count: int


class SourceCatalogEntry(SourceInfo):
    model_config = ConfigDict(extra="forbid")

    question_count: int
    question_ids: list[str]


class DatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    as_of_date: date
    coverage_start: date
    coverage_end: date
    total_questions: int
    categories: list[CategorySummary]
    sources: int


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=10, ge=1, le=100)
    categories: list[str] = Field(default_factory=list)
    difficulty: Difficulty | None = None
    tags: list[str] = Field(default_factory=list)
    search: str | None = None
    shuffle_questions: bool = True
    shuffle_options: bool = True
    include_explanations: bool = True
    include_sources: bool = True
    seed: int | None = None
