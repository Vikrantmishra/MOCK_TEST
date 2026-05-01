from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from random import Random
from typing import Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "app" / "data"
LATEST_PATH = DATA_DIR / "current_affairs_latest.json"
ARCHIVE_DIR = DATA_DIR / "archive"

PIB_ALL_RELEASES_URL = "https://www.pib.gov.in/AllRelease.aspx?MenuId=4&lang=1&reg=3"
RBI_PRESS_RELEASE_RSS_URL = "https://rbi.org.in/pressreleases_rss.xml"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LOOKBACK_DAYS = int(os.getenv("SSC_LOOKBACK_DAYS", "10"))
MIN_REFRESH_DAYS = int(os.getenv("SSC_MIN_REFRESH_DAYS", "3"))
FORCE_REFRESH_DAYS = int(os.getenv("SSC_FORCE_REFRESH_DAYS", "5"))
TARGET_QUESTION_COUNT = int(os.getenv("SSC_TARGET_QUESTION_COUNT", "25"))
MIN_NEW_QUESTION_COUNT = int(os.getenv("SSC_MIN_NEW_QUESTION_COUNT", "10"))

BLACKLIST_KEYWORDS = (
    "money market operations",
    "auction of",
    "government stock",
    "treasury bills",
    "weekly statistical supplement",
    "condoles",
    "greetings on the eve",
    "tributes to",
    "special screening",
    "capsizing of a boat",
)

ORG_DISTRACTORS = [
    "Reserve Bank of India",
    "ISRO",
    "UIDAI",
    "India Meteorological Department",
    "National Health Authority",
    "NITI Aayog",
    "Ministry of Finance",
    "Ministry of Commerce and Industry",
    "Ministry of MSME",
    "Ministry of Labour and Employment",
    "Ministry of Education",
    "Ministry of Health and Family Welfare",
    "Ministry of Electronics and Information Technology",
    "Department for Promotion of Industry and Internal Trade",
    "Prime Minister's Office",
]

PERSON_TITLE_DISTRACTORS = [
    "Prime Minister Narendra Modi",
    "Union Home Minister Amit Shah",
    "Union Health Minister J. P. Nadda",
    "Union Education Minister Dharmendra Pradhan",
    "DPIIT Secretary Amardeep Singh Bhatia",
    "RBI Governor",
]

COUNTRY_DISTRACTORS = [
    "Republic of Korea",
    "Bhutan",
    "France",
    "Japan",
    "Nepal",
    "Bangladesh",
    "Vietnam",
    "Indonesia",
    "Sri Lanka",
    "Singapore",
    "Germany",
    "Australia",
    "United Kingdom",
    "United States",
]

LOCATION_DISTRACTORS = [
    "New Delhi",
    "Mumbai",
    "Bengaluru",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Jaipur",
    "Bhopal",
    "Mohali",
    "Leh",
    "Munnar, Kerala",
    "Raipur, Chhattisgarh",
    "Bordeaux, France",
]

VERB_PATTERN = re.compile(
    r"^(?P<subject>.+?)\s+"
    r"(?:sign(?:s|ed)?|launch(?:es|ed)?|conduct(?:s|ed)?|hold(?:s|ing)?|held|announce(?:s|d)?|"
    r"constitute(?:s|d)?|release(?:s|d)?|invite(?:s|d)?|tie(?:s)? up|unveil(?:s|ed)?|"
    r"notif(?:y|ies|ied)|begin(?:s|an)?|start(?:s|ed)?|host(?:s|ed)?|achieve(?:s|d)?|record(?:s|ed)?|"
    r"approve(?:s|d)?|organi[sz](?:es|ed)?|review(?:s|ed)|join(?:s|ed)?|launch(?:es|ed)?|"
    r"visit(?:s|ed)?|call(?:s|ed)?|highlight(?:s|ed)?|share(?:s|d)?)\b",
    re.IGNORECASE,
)
NUMERIC_PATTERN = re.compile(
    r"(?P<prefix>₹|Rs\.?\s*)?(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|crore|lakh|million|billion|kg|kilograms?)\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b")


@dataclass(frozen=True)
class SourceItem:
    title: str
    url: str
    publisher: str
    published_on: date


def fetch_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.pib.gov.in/",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read()


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8", errors="ignore")


def load_existing_dataset() -> dict | None:
    if not LATEST_PATH.exists():
        return None
    return json.loads(LATEST_PATH.read_text(encoding="utf-8"))


def save_dataset(payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    archive_path = ARCHIVE_DIR / f"current_affairs_{payload['as_of_date'].replace('-', '_')}.json"
    archive_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_display_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%d %B %Y").date()


def parse_rfc822_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for pattern in ("%a, %d %b %Y %H:%M:%S", "%a, %d %b %Y %H:%M"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def slugify(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return lowered.strip("-")[:60] or "question"


def clean_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(value.replace("\xa0", " ").split())


def should_skip_title(title: str) -> bool:
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in BLACKLIST_KEYWORDS)


def fetch_pib_items() -> list[SourceItem]:
    html = fetch_text(PIB_ALL_RELEASES_URL)
    token_pattern = re.compile(
        r"<h3>(?P<section>.*?)</h3>|"
        r"<a title='(?P<title>.*?)' href='(?P<href>/[^']*PRID=\d+)'[^>]*>.*?</a>"
        r"<span class='publishdatesmall'>Posted on:\s*(?P<date>\d{2} [A-Za-z]+ \d{4})",
        re.IGNORECASE | re.DOTALL,
    )
    items: list[SourceItem] = []
    seen_urls: set[str] = set()
    current_section = "PIB"
    for match in token_pattern.finditer(html):
        if match.group("section"):
            current_section = clean_text(match.group("section")) or "PIB"
            continue
        title = clean_text(match.group("title") or "")
        href = match.group("href")
        date_value = match.group("date")
        if not title or not href or not date_value or should_skip_title(title):
            continue
        url = urljoin("https://www.pib.gov.in", href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(
            SourceItem(
                title=title,
                url=url,
                publisher=current_section,
                published_on=parse_display_date(date_value),
            )
        )
    return items


def fetch_rbi_items() -> list[SourceItem]:
    xml_bytes = fetch_bytes(RBI_PRESS_RELEASE_RSS_URL)
    root = ET.fromstring(xml_bytes)
    items: list[SourceItem] = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title") or "")
        if not title or should_skip_title(title):
            continue
        published_on = parse_rfc822_date(item.findtext("pubDate"))
        if published_on is None:
            continue
        link = (item.findtext("link") or "").replace("http://", "https://")
        items.append(
            SourceItem(
                title=title,
                url=link,
                publisher="RBI",
                published_on=published_on,
            )
        )
    return items


def filter_recent_items(items: Iterable[SourceItem], today: date) -> list[SourceItem]:
    lower_bound = today - timedelta(days=LOOKBACK_DAYS)
    filtered = [item for item in items if item.published_on >= lower_bound]
    deduped: list[SourceItem] = []
    seen: set[tuple[str, str]] = set()
    for item in sorted(filtered, key=lambda value: (value.published_on, value.title), reverse=True):
        key = (item.title.lower(), item.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def infer_category(title: str) -> str:
    lowered = title.lower()
    if any(keyword in lowered for keyword in ("rbi", "treasury", "bank", "repo", "inflation", "securities")):
        return "banking"
    if any(keyword in lowered for keyword in ("isro", "space", "satellite", "gaganyaan", "launch vehicle")):
        return "space"
    if any(keyword in lowered for keyword in ("health", "medical", "pharma", "pm-jay", "niper", "hospital")):
        return "health"
    if any(keyword in lowered for keyword in ("education", "olympiad", "student", "university")):
        return "education"
    if any(keyword in lowered for keyword in ("cyber", "ai ", "aigeg", "digital", "uidai", "aadhaar", "app", "portal")):
        return "digital-governance"
    if any(keyword in lowered for keyword in ("startup", "fund of funds", "dpiit", "innovation")):
        return "startup"
    if any(keyword in lowered for keyword in ("game", "games", "sports", "archery", "khelo")):
        return "sports"
    if any(keyword in lowered for keyword in ("mou", "cooperation", "joint group", "india and")):
        return "international-relations"
    if any(keyword in lowered for keyword in ("monsoon", "rainfall", "weather", "imd")):
        return "climate"
    if any(keyword in lowered for keyword in ("scheme", "yojana", "nutrition", "women", "child")):
        return "social-welfare"
    if any(keyword in lowered for keyword in ("employment", "career service", "labour")):
        return "employment"
    return "governance"


def infer_tags(title: str, category: str, publisher: str) -> list[str]:
    lowered = title.lower()
    tags = {category, publisher.lower()}
    keyword_map = {
        "ai": "ai",
        "cyber": "cyber-security",
        "aadhaar": "aadhaar",
        "mou": "mou",
        "fund": "funding",
        "monsoon": "monsoon",
        "startup": "startup",
        "rbi": "rbi",
        "isro": "isro",
        "uidai": "uidai",
        "mission": "mission",
        "scheme": "scheme",
        "report": "report",
        "app": "app",
        "portal": "portal",
        "olympiad": "olympiad",
        "health": "health",
        "census": "census",
    }
    for keyword, tag in keyword_map.items():
        if keyword in lowered:
            tags.add(tag)
    return sorted(tags)


def infer_subject(title: str, publisher: str) -> str:
    match = VERB_PATTERN.search(title)
    if match:
        subject = match.group("subject").strip(" -:,;")
        if 2 <= len(subject) <= 90:
            return subject
    if publisher == "RBI":
        return "Reserve Bank of India"
    if publisher and publisher != "PIB":
        return publisher
    return "Government of India"


def detect_entity_kind(answer: str) -> str:
    lowered = answer.lower()
    if NUMERIC_PATTERN.fullmatch(answer.strip()):
        return "numeric"
    if "%" in answer or "crore" in lowered or "lakh" in lowered or "kg" in lowered or "million" in lowered:
        return "numeric"
    if any(country.lower() == lowered for country in COUNTRY_DISTRACTORS):
        return "country"
    if any(country.lower() in lowered for country in COUNTRY_DISTRACTORS):
        return "country"
    if any(location.lower() == lowered for location in LOCATION_DISTRACTORS):
        return "location"
    if any(token in lowered for token in ("minister", "secretary", "president", "prime minister", "governor")):
        return "person-title"
    return "organisation"


def numeric_options(answer: str) -> list[str]:
    match = NUMERIC_PATTERN.search(answer)
    if not match:
        return [answer, "5%", "10%", "15%"]
    prefix = (match.group("prefix") or "").strip()
    value_text = match.group("value").replace(",", "")
    unit = match.group("unit")
    value = float(value_text)
    if "%" in unit:
        deltas = [2, 4, 6]
    elif unit.lower() in {"crore", "lakh"}:
        step = max(int(value * 0.1), 1)
        deltas = [step, step * 2, step * 3]
    else:
        step = max(int(value * 0.08), 1)
        deltas = [step, step * 2, step * 3]

    options = {format_numeric(value, prefix, unit)}
    for delta in deltas:
        options.add(format_numeric(max(value - delta, 1), prefix, unit))
        if len(options) >= 4:
            break
    for delta in deltas:
        options.add(format_numeric(value + delta, prefix, unit))
        if len(options) >= 4:
            break
    rendered = list(options)[:4]
    while len(rendered) < 4:
        rendered.append(format_numeric(value + len(rendered) + 1, prefix, unit))
    return rendered


def format_numeric(value: float, prefix: str, unit: str) -> str:
    if float(value).is_integer():
        core = f"{int(value):,}"
    else:
        core = f"{value:.1f}".rstrip("0").rstrip(".")
    if prefix:
        return f"{prefix} {core} {unit}".replace("  ", " ").strip()
    return f"{core}{unit}" if unit == "%" else f"{core} {unit}"


def pick_distractors(answer: str, candidates: list[str], seed_key: str) -> list[str]:
    unique_candidates = []
    lowered_answer = answer.lower()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate.lower() == lowered_answer:
            continue
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    rng = Random(seed_key)
    rng.shuffle(unique_candidates)
    chosen = unique_candidates[:3]
    while len(chosen) < 3:
        filler = f"Option {len(chosen) + 1}"
        if filler.lower() != lowered_answer:
            chosen.append(filler)
    return chosen


def extract_country_answer(title: str) -> str | None:
    patterns = [
        r"between India and\s+(?P<answer>[A-Z][A-Za-z .&-]+)",
        r"India and\s+(?P<answer>[A-Z][A-Za-z .&-]+?)\s+(?:sign|hold|launch|begin|deepen)",
        r"cooperation with\s+(?P<answer>[A-Z][A-Za-z .&-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            answer = match.group("answer").strip(" ,.-")
            if len(answer) > 2:
                return answer
    return None


def extract_location_answer(title: str) -> str | None:
    patterns = [
        r"\b(?:held|hosted|conducted|launched|launches|begins|began|scheduled to be held)\s+(?:in|at)\s+(?P<answer>[A-Z][A-Za-z .&-]+(?:,\s*[A-Z][A-Za-z .&-]+)?)",
        r"\bin\s+(?P<answer>Bordeaux, France|Munnar, Kerala|Raipur, Chhattisgarh|Leh|Mohali|Bengaluru|Mumbai|New Delhi)",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            answer = match.group("answer").strip(" ,.-")
            if answer:
                return answer
    return None


def build_question(item: SourceItem, dynamic_subject_pool: list[str], index: int, today: date) -> dict | None:
    title = clean_text(item.title)
    category = infer_category(title)
    tags = infer_tags(title, category, item.publisher)
    subject = infer_subject(title, item.publisher)
    title_for_question = title.rstrip(".")

    numeric_match = NUMERIC_PATTERN.search(title)
    country_answer = extract_country_answer(title)
    location_answer = extract_location_answer(title)

    answer = subject
    question = f"Which organisation or authority is most directly associated with this update: '{title_for_question}'?"
    options = [answer] + pick_distractors(answer, dynamic_subject_pool + ORG_DISTRACTORS, f"{index}-{answer}")
    difficulty = "easy"

    if numeric_match:
        answer = clean_text(numeric_match.group(0))
        question = f"According to the official update '{title_for_question}', what key numerical figure was highlighted?"
        options = numeric_options(answer)
        difficulty = "medium"
    elif country_answer:
        answer = country_answer
        question = f"According to the official update '{title_for_question}', which country or partner was involved?"
        options = [answer] + pick_distractors(answer, COUNTRY_DISTRACTORS, f"{index}-{answer}")
        difficulty = "medium"
    elif location_answer:
        answer = location_answer
        question = f"According to the official update '{title_for_question}', where did this event take place?"
        options = [answer] + pick_distractors(answer, LOCATION_DISTRACTORS, f"{index}-{answer}")
        difficulty = "easy"
    else:
        kind = detect_entity_kind(subject)
        if kind == "person-title":
            options = [subject] + pick_distractors(subject, dynamic_subject_pool + PERSON_TITLE_DISTRACTORS, f"{index}-{subject}")
        else:
            options = [subject] + pick_distractors(subject, dynamic_subject_pool + ORG_DISTRACTORS, f"{index}-{subject}")

    unique_options = []
    for option in options:
        if option not in unique_options:
            unique_options.append(option)
    if answer not in unique_options:
        unique_options.insert(0, answer)
    if len(unique_options) < 4:
        filler_pool = ORG_DISTRACTORS + PERSON_TITLE_DISTRACTORS + COUNTRY_DISTRACTORS + LOCATION_DISTRACTORS
        for filler in filler_pool:
            if filler != answer and filler not in unique_options:
                unique_options.append(filler)
            if len(unique_options) == 4:
                break
    unique_options = unique_options[:4]
    if len(unique_options) != 4 or answer not in unique_options:
        return None

    return {
        "id": f"auto-{today.isoformat().replace('-', '')}-{index:03d}-{slugify(title)}",
        "exam": "ssc",
        "as_of_date": today.isoformat(),
        "category": category,
        "difficulty": difficulty,
        "fact": title,
        "question": question,
        "options": unique_options,
        "correct_answer": answer,
        "explanation": f"{item.publisher} reported '{title}' on {item.published_on.isoformat()}.",
        "tags": tags,
        "source": {
            "title": title,
            "url": item.url,
            "publisher": item.publisher,
            "published_on": item.published_on.isoformat(),
        },
    }


def build_dynamic_subject_pool(items: list[SourceItem]) -> list[str]:
    pool: list[str] = []
    for item in items:
        subject = infer_subject(item.title, item.publisher)
        if subject not in pool:
            pool.append(subject)
    return pool


def build_payload(new_questions: list[dict], fallback_questions: list[dict], today: date) -> dict:
    selected_questions = new_questions[:TARGET_QUESTION_COUNT]
    seen_ids = {question["id"] for question in selected_questions}
    for question in fallback_questions:
        if len(selected_questions) >= TARGET_QUESTION_COUNT:
            break
        if question["id"] in seen_ids:
            continue
        selected_questions.append(question)
        seen_ids.add(question["id"])

    coverage_dates = [datetime.fromisoformat(question["source"]["published_on"]).date() for question in selected_questions]
    return {
        "dataset_name": "SSC Current Affairs MCQs",
        "as_of_date": today.isoformat(),
        "coverage_start": min(coverage_dates).isoformat(),
        "coverage_end": max(coverage_dates).isoformat(),
        "questions": selected_questions,
    }


def main() -> int:
    today = date.today()
    existing_payload = load_existing_dataset()
    existing_questions = existing_payload.get("questions", []) if existing_payload else []
    existing_as_of_date = (
        datetime.fromisoformat(existing_payload["as_of_date"]).date() if existing_payload else date.min
    )
    existing_age = (today - existing_as_of_date).days if existing_payload else FORCE_REFRESH_DAYS

    recent_items = filter_recent_items(fetch_pib_items() + fetch_rbi_items(), today)
    dynamic_subject_pool = build_dynamic_subject_pool(recent_items)

    new_questions: list[dict] = []
    for index, item in enumerate(recent_items, start=1):
        question = build_question(item, dynamic_subject_pool, index, today)
        if question is not None:
            new_questions.append(question)

    if existing_age < MIN_REFRESH_DAYS:
        print(f"Skip: dataset age is {existing_age} days, below minimum refresh window of {MIN_REFRESH_DAYS} days.")
        return 0

    if existing_age < FORCE_REFRESH_DAYS and len(new_questions) < MIN_NEW_QUESTION_COUNT:
        print(
            f"Skip: generated only {len(new_questions)} fresh questions; waiting until age reaches {FORCE_REFRESH_DAYS} days."
        )
        return 0

    if not new_questions and not existing_questions:
        raise RuntimeError("No fresh questions were generated and no fallback dataset is available.")

    payload = build_payload(new_questions, existing_questions, today)
    save_dataset(payload)
    print(
        f"Updated dataset to {payload['as_of_date']} with {len(payload['questions'])} questions "
        f"(fresh: {len(new_questions)}, fallback: {max(len(payload['questions']) - len(new_questions), 0)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
