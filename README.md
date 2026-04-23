# SSC Current Affairs MCQ API

This is a small FastAPI service for serving SSC-style current affairs MCQs with a seed bank updated as of `2026-04-23`.

The initial dataset focuses on recent official releases from sources such as PIB, IMD, ISRO, UIDAI and RBI, so you can call the API directly from your app to fetch or generate question sets.

## Features

- FastAPI service with Swagger docs at `/docs`
- Seeded SSC current affairs MCQ bank
- Filters by category, difficulty, tags and search term
- Random question generation
- Optional option shuffling
- Source links and explanations included in every MCQ

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API will start on:

```text
http://127.0.0.1:8000
```

## Main endpoints

- `GET /health`
- `GET /api/v1/dataset`
- `GET /api/v1/categories`
- `GET /api/v1/sources`
- `GET /api/v1/questions`
- `GET /api/v1/questions/{question_id}`
- `POST /api/v1/questions/generate`

## Example calls

Fetch 5 random questions:

```bash
curl "http://127.0.0.1:8000/api/v1/questions?limit=5&seed=42"
```

Fetch only space questions:

```bash
curl "http://127.0.0.1:8000/api/v1/questions?category=space&limit=5"
```

Generate a filtered pack:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/questions/generate" ^
  -H "Content-Type: application/json" ^
  -d "{\"count\": 10, \"categories\": [\"space\", \"digital-governance\"], \"shuffle_questions\": true, \"shuffle_options\": true, \"seed\": 7}"
```

## Notes

- The current seed data is verified against recent official releases available up to `2026-04-23`.
- You can expand the bank by appending more entries to [current_affairs_2026_04_23.json](C:\Users\Vikrant Mishra\Downloads\Telegram Desktop\ssc_current_affairs_api\app\data\current_affairs_2026_04_23.json).
- Every question stores source metadata so you can trace the fact used to build it.
