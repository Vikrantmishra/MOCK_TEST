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
    assert payload["total_questions"] >= 20


def test_generate_questions() -> None:
    response = client.post(
        "/api/v1/questions/generate",
        json={
            "count": 3,
            "categories": ["space", "digital-governance"],
            "shuffle_questions": True,
            "shuffle_options": True,
            "seed": 11,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["returned"] == 3
    assert len(payload["questions"]) == 3


def test_question_lookup() -> None:
    response = client.get("/api/v1/questions/q001-poshan-mission")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "q001-poshan-mission"
