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
DYNAMIC_DATA_PATH = DATA_DIR / "current_affairs_latest.json"
STATIC_YEAR_DATA_PATH = DATA_DIR / "current_affairs_static_year.json"
LEGACY_DATA_PATH = DATA_DIR / "current_affairs_2026_04_23.json"
DEFAULT_STATIC_SHARE = 18
DEFAULT_DYNAMIC_SHARE = 7
DEFAULT_MIX_TOTAL = DEFAULT_STATIC_SHARE + DEFAULT_DYNAMIC_SHARE


def resolve_dynamic_data_path() -> Path:
    configured = os.getenv("SSC_CURRENT_AFFAIRS_DYNAMIC_DATA_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    if DYNAMIC_DATA_PATH.exists():
        return DYNAMIC_DATA_PATH
    return LEGACY_DATA_PATH


def resolve_static_data_path() -> Path:
    configured = os.getenv("SSC_CURRENT_AFFAIRS_STATIC_DATA_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    if STATIC_YEAR_DATA_PATH.exists():
        return STATIC_YEAR_DATA_PATH
    return LEGACY_DATA_PATH


DYNAMIC_PATH = resolve_dynamic_data_path()
STATIC_PATH = resolve_static_data_path()


def _normalize(value: str) -> str:
    return value.strip().lower()


def _normalize_many(values: list[str]) -> set[str]:
    return {_normalize(value) for value in values if value.strip()}


def _make_rng(seed: int | None) -> random.Random:
    return random.Random(seed)


def _payload_from_path(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_dynamic_dataset_payload() -> dict:
    return _payload_from_path(DYNAMIC_PATH)


@lru_cache(maxsize=1)
def load_static_dataset_payload() -> dict:
    return _payload_from_path(STATIC_PATH)


def _tagged_questions(payload: dict, bank_tag: str) -> list[QuestionRecord]:
    tagged: list[QuestionRecord] = []
    for item in payload["questions"]:
        enriched = dict(item)
        tags = list(enriched.get("tags", []))
        if bank_tag not in tags:
            tags.append(bank_tag)
        enriched["tags"] = tags
        tagged.append(QuestionRecord.model_validate(enriched))
    return tagged


@lru_cache(maxsize=1)
def load_dynamic_questions() -> list[QuestionRecord]:
    return _tagged_questions(load_dynamic_dataset_payload(), "dynamic-bank")


@lru_cache(maxsize=1)
def load_static_questions() -> list[QuestionRecord]:
    return _tagged_questions(load_static_dataset_payload(), "static-year-bank")


@lru_cache(maxsize=1)
def load_questions() -> list[QuestionRecord]:
    return load_static_questions() + load_dynamic_questions()


def get_dataset_summary() -> DatasetSummary:
    questions = load_questions()
    static_payload = load_static_dataset_payload()
    dynamic_payload = load_dynamic_dataset_payload()
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
        dataset_name=dynamic_payload.get("dataset_name", static_payload.get("dataset_name", "SSC Current Affairs MCQs")),
        as_of_date=dynamic_payload.get("as_of_date", static_payload["as_of_date"]),
        coverage_start=min(static_payload["coverage_start"], dynamic_payload["coverage_start"]),
        coverage_end=max(static_payload["coverage_end"], dynamic_payload["coverage_end"]),
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
    bank: str = "combined",
) -> list[QuestionRecord]:
    if bank == "static":
        question_pool = load_static_questions()
    elif bank == "dynamic":
        question_pool = load_dynamic_questions()
    else:
        question_pool = load_questions()

    category_filter = _normalize(category) if category else None
    categories_filter = _normalize_many(categories or [])
    difficulty_filter = _normalize(difficulty) if difficulty else None
    tag_filter = _normalize_many(tags or [])
    search_filter = _normalize(search) if search else None

    filtered: list[QuestionRecord] = []
    for question in question_pool:
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


def calculate_mix_counts(
    *,
    total_needed: int,
    available_static: int,
    available_dynamic: int,
) -> tuple[int, int]:
    if total_needed <= 0:
        return 0, 0

    if total_needed == DEFAULT_MIX_TOTAL:
        static_target = min(DEFAULT_STATIC_SHARE, available_static)
        dynamic_target = min(DEFAULT_DYNAMIC_SHARE, available_dynamic)
    else:
        static_ratio = DEFAULT_STATIC_SHARE / DEFAULT_MIX_TOTAL
        static_target = min(available_static, round(total_needed * static_ratio))
        dynamic_target = min(available_dynamic, total_needed - static_target)

    remaining = total_needed - static_target - dynamic_target
    if remaining > 0:
        static_extra = min(available_static - static_target, remaining)
        static_target += static_extra
        remaining -= static_extra
    if remaining > 0:
        dynamic_extra = min(available_dynamic - dynamic_target, remaining)
        dynamic_target += dynamic_extra

    return static_target, dynamic_target


def build_mixed_question_records(
    static_questions: list[QuestionRecord],
    dynamic_questions: list[QuestionRecord],
    *,
    limit: int,
    offset: int,
    randomize: bool,
    seed: int | None,
) -> list[QuestionRecord]:
    rng = _make_rng(seed)
    available_static = list(static_questions)
    available_dynamic = list(dynamic_questions)
    if randomize:
        rng.shuffle(available_static)
        rng.shuffle(available_dynamic)

    total_needed = offset + limit
    static_count, dynamic_count = calculate_mix_counts(
        total_needed=total_needed,
        available_static=len(available_static),
        available_dynamic=len(available_dynamic),
    )
    combined = available_static[:static_count] + available_dynamic[:dynamic_count]
    if randomize:
        rng.shuffle(combined)
    return combined[offset : offset + limit]


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


def build_mixed_questions_response(
    static_questions: list[QuestionRecord],
    dynamic_questions: list[QuestionRecord],
    *,
    limit: int,
    offset: int = 0,
    randomize: bool,
    shuffle_options: bool,
    include_explanations: bool,
    include_sources: bool,
    seed: int | None,
) -> QuestionsResponse:
    mixed_records = build_mixed_question_records(
        static_questions,
        dynamic_questions,
        limit=limit,
        offset=offset,
        randomize=randomize,
        seed=seed,
    )
    rng = _make_rng(seed)
    rendered = [
        render_question(
            question,
            shuffle_options=shuffle_options,
            include_explanations=include_explanations,
            include_sources=include_sources,
            rng=rng,
        )
        for question in mixed_records
    ]
    summary = get_dataset_summary()
    return QuestionsResponse(
        total_available=len(static_questions) + len(dynamic_questions),
        returned=len(rendered),
        as_of_date=summary.as_of_date,
        questions=rendered,
    )


def get_question_or_none(question_id: str) -> QuestionRecord | None:
    for question in load_questions():
        if question.id == question_id:
            return question
    return None
