from __future__ import annotations

import json
import os
import random
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .models import (
    CategorySummary,
    DatasetSummary,
    GeneratedQuestion,
    QuestionRecord,
    QuestionsResponse,
    SourceCatalogEntry,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DATA_PATH = DATA_DIR / "current_affairs_latest.json"
LEGACY_DATA_PATH = DATA_DIR / "current_affairs_2026_04_23.json"


def resolve_data_path() -> Path:
    configured = os.getenv("SSC_CURRENT_AFFAIRS_DATA_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    if DEFAULT_DATA_PATH.exists():
        return DEFAULT_DATA_PATH
    return LEGACY_DATA_PATH


DATA_PATH = resolve_data_path()


def _normalize(value: str) -> str:
    return value.strip().lower()


def _normalize_many(values: list[str]) -> set[str]:
    return {_normalize(value) for value in values if value.strip()}


def _make_rng(seed: int | None) -> random.Random:
    return random.Random(seed)


@lru_cache(maxsize=1)
def load_dataset_payload() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_questions() -> list[QuestionRecord]:
    payload = load_dataset_payload()
    return [QuestionRecord.model_validate(item) for item in payload["questions"]]


def get_dataset_summary() -> DatasetSummary:
    payload = load_dataset_payload()
    questions = load_questions()
    category_counts = Counter(question.category for question in questions)
    categories = [
        CategorySummary(name=name, question_count=count)
        for name, count in sorted(category_counts.items())
    ]
    unique_sources = {
        (question.source.title, str(question.source.url), question.source.published_on.isoformat())
        for question in questions
    }
    return DatasetSummary(
        dataset_name=payload["dataset_name"],
        as_of_date=payload["as_of_date"],
        coverage_start=payload["coverage_start"],
        coverage_end=payload["coverage_end"],
        total_questions=len(questions),
        categories=categories,
        sources=len(unique_sources),
    )


def list_sources() -> list[SourceCatalogEntry]:
    grouped: dict[tuple[str, str], dict] = {}
    for question in load_questions():
        key = (question.source.title, str(question.source.url))
        grouped.setdefault(
            key,
            {
                "title": question.source.title,
                "url": question.source.url,
                "publisher": question.source.publisher,
                "published_on": question.source.published_on,
                "question_ids": [],
            },
        )
        grouped[key]["question_ids"].append(question.id)

    sources = [
        SourceCatalogEntry(
            title=value["title"],
            url=value["url"],
            publisher=value["publisher"],
            published_on=value["published_on"],
            question_count=len(value["question_ids"]),
            question_ids=sorted(value["question_ids"]),
        )
        for value in grouped.values()
    ]
    return sorted(sources, key=lambda item: (item.published_on, item.title), reverse=True)


def filter_questions(
    *,
    category: str | None = None,
    difficulty: str | None = None,
    tags: list[str] | None = None,
    search: str | None = None,
    categories: list[str] | None = None,
) -> list[QuestionRecord]:
    category_filter = _normalize(category) if category else None
    categories_filter = _normalize_many(categories or [])
    difficulty_filter = _normalize(difficulty) if difficulty else None
    tag_filter = _normalize_many(tags or [])
    search_filter = _normalize(search) if search else None

    filtered: list[QuestionRecord] = []
    for question in load_questions():
        if category_filter and _normalize(question.category) != category_filter:
            continue
        if categories_filter and _normalize(question.category) not in categories_filter:
            continue
        if difficulty_filter and _normalize(question.difficulty) != difficulty_filter:
            continue
        if tag_filter:
            question_tags = _normalize_many(question.tags)
            if not tag_filter.issubset(question_tags):
                continue
        if search_filter:
            haystack = " ".join(
                [
                    question.fact,
                    question.question,
                    question.category,
                    question.correct_answer,
                    " ".join(question.options),
                    " ".join(question.tags),
                    question.source.title,
                ]
            ).lower()
            if search_filter not in haystack:
                continue
        filtered.append(question)
    return filtered


def render_question(
    question: QuestionRecord,
    *,
    shuffle_options: bool,
    include_explanations: bool,
    include_sources: bool,
    rng: random.Random,
) -> GeneratedQuestion:
    options = list(question.options)
    if shuffle_options:
        rng.shuffle(options)
    answer_index = options.index(question.correct_answer)
    return GeneratedQuestion(
        id=question.id,
        exam=question.exam,
        as_of_date=question.as_of_date,
        category=question.category,
        difficulty=question.difficulty,
        fact=question.fact,
        question=question.question,
        options=options,
        answer_index=answer_index,
        answer=question.correct_answer,
        explanation=question.explanation if include_explanations else None,
        tags=question.tags,
        source=question.source if include_sources else None,
    )


def build_questions_response(
    questions: list[QuestionRecord],
    *,
    limit: int,
    offset: int = 0,
    randomize: bool,
    shuffle_options: bool,
    include_explanations: bool,
    include_sources: bool,
    seed: int | None,
) -> QuestionsResponse:
    available = list(questions)
    rng = _make_rng(seed)
    if randomize:
        rng.shuffle(available)

    sliced = available[offset : offset + limit]
    rendered = [
        render_question(
            question,
            shuffle_options=shuffle_options,
            include_explanations=include_explanations,
            include_sources=include_sources,
            rng=rng,
        )
        for question in sliced
    ]
    summary = get_dataset_summary()
    return QuestionsResponse(
        total_available=len(questions),
        returned=len(rendered),
        as_of_date=summary.as_of_date,
        questions=rendered,
    )


def get_question_or_none(question_id: str) -> QuestionRecord | None:
    for question in load_questions():
        if question.id == question_id:
            return question
    return None
