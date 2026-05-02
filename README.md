# SSC Current Affairs MCQ API

This is a small FastAPI service for serving SSC-style current affairs MCQs.

The API now serves a mixed bank:

- `18` questions from `app/data/current_affairs_static_year.json`
- `7` questions from `app/data/current_affairs_latest.json`

This keeps the response fresh while still preserving a broader static preparation base.

## Features

- FastAPI service with Swagger docs at `/docs`
- Seeded SSC current affairs MCQ bank
- Filters by category, difficulty, tags and search term
- Random question generation
- Optional option shuffling
- Source links and explanations included in every MCQ
- Scheduled GitHub Actions refresh pipeline for new question sets
- Mixed response mode: `18 static-year + 7 dynamic` for the default 25-question pack

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

- The live API combines [current_affairs_static_year.json](C:\Users\Vikrant Mishra\Downloads\Telegram Desktop\ssc_current_affairs_api\app\data\current_affairs_static_year.json) with [current_affairs_latest.json](C:\Users\Vikrant Mishra\Downloads\Telegram Desktop\ssc_current_affairs_api\app\data\current_affairs_latest.json).
- Fresh question banks can be generated locally with:

```bash
python scripts/update_current_affairs.py
```

- The scheduled workflow lives at [update_current_affairs.yml](C:\Users\Vikrant Mishra\Downloads\Telegram Desktop\ssc_current_affairs_api\.github\workflows\update_current_affairs.yml) and runs daily. It only commits a new dataset when the current one is at least 3 days old or has reached the 5-day force-refresh window.
- Archived snapshots are written to [app/data/archive](C:\Users\Vikrant Mishra\Downloads\Telegram Desktop\ssc_current_affairs_api\app\data\archive).
- The default 25-question API pack uses an `18:7` static-to-dynamic split. Other counts use the same ratio as closely as possible.
- Every question stores source metadata so you can trace the fact used to build it.
