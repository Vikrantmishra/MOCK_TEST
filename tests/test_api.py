from pathlib import Path
import sys

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["question_bank"] > 0


def test_dataset() -> None:
    response = client.get("/api/v1/dataset")
    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_name"] == "SSC Current Affairs MCQs"
    assert payload["total_questions"] >= 50
    assert payload["as_of_date"]


def test_generate_questions() -> None:
    response = client.post(
        "/api/v1/questions/generate",
        json={
            "count": 3,
            "categories": ["governance", "digital-governance", "health", "international-relations"],
            "shuffle_questions": True,
            "shuffle_options": True,
            "seed": 11,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["returned"] == 3
    assert len(payload["questions"]) == 3


def test_generate_questions_get() -> None:
    response = client.get("/api/v1/questions/generate?count=25&shuffle_options=false&seed=7")
    assert response.status_code == 200
    payload = response.json()
    assert payload["returned"] == 25
    assert len(payload["questions"]) == 25
    static_count = sum("static-year-bank" in question["tags"] for question in payload["questions"])
    dynamic_count = sum("dynamic-bank" in question["tags"] for question in payload["questions"])
    assert static_count == 18
    assert dynamic_count == 7


def test_question_lookup() -> None:
    questions_response = client.get("/api/v1/questions?limit=1&randomize=false&shuffle_options=false")
    assert questions_response.status_code == 200
    question_id = questions_response.json()["questions"][0]["id"]

    response = client.get(f"/api/v1/questions/{question_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == question_id
