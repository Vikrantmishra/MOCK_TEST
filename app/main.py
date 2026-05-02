from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import GenerateRequest, GeneratedQuestion, QuestionsResponse
from .services import (
    build_mixed_questions_response,
    filter_questions,
    get_dataset_summary,
    get_question_or_none,
    list_sources,
    render_question,
)

app = FastAPI(
    title="SSC Current Affairs MCQ API",
    version="1.0.0",
    description=(
        "SSC-ready current affairs MCQ API seeded with verified official April 2026 releases. "
        "Use /docs for interactive testing."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    summary = get_dataset_summary()
    return {
        "name": summary.dataset_name,
        "version": app.version,
        "as_of_date": summary.as_of_date,
        "coverage_start": summary.coverage_start,
        "coverage_end": summary.coverage_end,
        "total_questions": summary.total_questions,
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "dataset": "/api/v1/dataset",
            "categories": "/api/v1/categories",
            "sources": "/api/v1/sources",
            "questions": "/api/v1/questions",
            "question_by_id": "/api/v1/questions/{question_id}",
            "generate": "/api/v1/questions/generate",
        },
    }


@app.get("/health")
def health() -> dict:
    summary = get_dataset_summary()
    return {"status": "ok", "question_bank": summary.total_questions, "as_of_date": summary.as_of_date}


@app.get("/api/v1/dataset")
def dataset() -> dict:
    return get_dataset_summary().model_dump()


@app.get("/api/v1/categories")
def categories() -> dict:
    summary = get_dataset_summary()
    return {"categories": [category.model_dump() for category in summary.categories]}


@app.get("/api/v1/sources")
def sources() -> dict:
    return {"sources": [source.model_dump() for source in list_sources()]}


@app.get("/api/v1/questions", response_model=QuestionsResponse)
def questions(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str | None = None,
    difficulty: str | None = None,
    tags: str | None = Query(default=None, description="Comma-separated tags"),
    search: str | None = None,
    randomize: bool = True,
    shuffle_options: bool = True,
    include_explanations: bool = True,
    include_sources: bool = True,
    seed: int | None = None,
) -> QuestionsResponse:
    tag_list = [tag.strip() for tag in tags.split(",")] if tags else []
    static_filtered = filter_questions(
        category=category,
        difficulty=difficulty,
        tags=tag_list,
        search=search,
        bank="static",
    )
    dynamic_filtered = filter_questions(
        category=category,
        difficulty=difficulty,
        tags=tag_list,
        search=search,
        bank="dynamic",
    )
    return build_mixed_questions_response(
        static_filtered,
        dynamic_filtered,
        limit=limit,
        offset=offset,
        randomize=randomize,
        shuffle_options=shuffle_options,
        include_explanations=include_explanations,
        include_sources=include_sources,
        seed=seed,
    )


@app.get("/api/v1/questions/generate", response_model=QuestionsResponse)
def generate_questions_get(
    count: int = Query(default=25, ge=1, le=100),
    categories: str | None = Query(default=None, description="Comma-separated categories"),
    difficulty: str | None = None,
    tags: str | None = Query(default=None, description="Comma-separated tags"),
    search: str | None = None,
    shuffle_questions: bool = True,
    shuffle_options: bool = True,
    include_explanations: bool = True,
    include_sources: bool = True,
    seed: int | None = None,
) -> QuestionsResponse:
    category_list = [category.strip() for category in categories.split(",")] if categories else []
    tag_list = [tag.strip() for tag in tags.split(",")] if tags else []
    static_filtered = filter_questions(
        difficulty=difficulty,
        tags=tag_list,
        search=search,
        categories=category_list,
        bank="static",
    )
    dynamic_filtered = filter_questions(
        difficulty=difficulty,
        tags=tag_list,
        search=search,
        categories=category_list,
        bank="dynamic",
    )
    return build_mixed_questions_response(
        static_filtered,
        dynamic_filtered,
        limit=count,
        offset=0,
        randomize=shuffle_questions,
        shuffle_options=shuffle_options,
        include_explanations=include_explanations,
        include_sources=include_sources,
        seed=seed,
    )


@app.get("/api/v1/questions/{question_id}", response_model=GeneratedQuestion)
def question_by_id(
    question_id: str,
    shuffle_options: bool = False,
    include_explanation: bool = True,
    include_source: bool = True,
    seed: int | None = None,
) -> GeneratedQuestion:
    question = get_question_or_none(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    from random import Random

    rng = Random(seed)
    return render_question(
        question,
        shuffle_options=shuffle_options,
        include_explanations=include_explanation,
        include_sources=include_source,
        rng=rng,
    )


@app.post("/api/v1/questions/generate", response_model=QuestionsResponse)
def generate_questions(payload: GenerateRequest) -> QuestionsResponse:
    static_filtered = filter_questions(
        difficulty=payload.difficulty,
        tags=payload.tags,
        search=payload.search,
        categories=payload.categories,
        bank="static",
    )
    dynamic_filtered = filter_questions(
        difficulty=payload.difficulty,
        tags=payload.tags,
        search=payload.search,
        categories=payload.categories,
        bank="dynamic",
    )
    return build_mixed_questions_response(
        static_filtered,
        dynamic_filtered,
        limit=payload.count,
        offset=0,
        randomize=payload.shuffle_questions,
        shuffle_options=payload.shuffle_options,
        include_explanations=payload.include_explanations,
        include_sources=payload.include_sources,
        seed=payload.seed,
    )
