from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any

import cv2

from act_scoring import ACT_RUBRIC, ACT_SCORING_CONFIG

SECTION_PROMPT_ORDER = [
    ("EN", "english", "English", 50),
    ("M", "math", "Mathematics", 45),
    ("R", "reading", "Reading", 36),
    ("S", "science", "Science", 40),
]

ALLOWED_ANSWER_VALUES = {"A", "B", "C", "D", "F", "G", "H", "J", "blank", "multiple", "unclear"}


def ai_scoring_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def should_use_ai(strategy: str = "") -> bool:
    requested = (strategy or "").strip().lower()
    if requested in {"ai", "hybrid"}:
        return ai_scoring_enabled()

    default_mode = os.getenv("OMR_SCORING_MODE", "").strip().lower()
    if default_mode in {"ai", "hybrid", "auto"}:
        return ai_scoring_enabled()

    return False


def score_sections_with_ai(*, section_images: dict[str, Any], strategy: str = "") -> dict[str, Any] | None:
    if not should_use_ai(strategy):
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    all_answers: dict[str, str] = {}
    section_confidence: dict[str, float] = {}
    section_notes: list[str] = []

    for prefix, slug, title, question_count in SECTION_PROMPT_ORDER:
        image = section_images.get(prefix)
        if image is None:
            continue

        payload = build_section_payload(
            image=image,
            model=model,
            prefix=prefix,
            slug=slug,
            title=title,
            question_count=question_count,
        )
        raw_response = create_response(payload, api_key=api_key)
        response_text = extract_response_text(raw_response)
        if not response_text:
            raise RuntimeError(f"OpenAI response for {slug} did not contain text output")

        parsed = json.loads(response_text)
        normalized_answers = normalize_section_answers(
            parsed.get("answers", {}),
            prefix=prefix,
            question_count=question_count,
        )
        all_answers.update(normalized_answers)

        confidence = parsed.get("sectionConfidence")
        if isinstance(confidence, (int, float)):
            section_confidence[slug] = float(confidence)

        note = str(parsed.get("notes", "")).strip()
        if note:
            section_notes.append(f"{slug}:{note}")

    return {
        "answers": all_answers,
        "notes": "; ".join(section_notes),
        "sectionConfidence": section_confidence,
        "model": model,
    }


def build_section_payload(*, image: Any, model: str, prefix: str, slug: str, title: str, question_count: int) -> dict[str, Any]:
    rubric_payload = build_section_rubric_payload(slug)
    system_prompt = (
        "You are reading a single cropped ACT answer-sheet section. "
        "The image is already black-and-white inverted. "
        "Only report what is visibly marked. "
        "Most rows may be blank. "
        "If no dark mark is clearly present, return blank. "
        "If more than one bubble is marked, return multiple. "
        "If the image quality makes the row unreadable, return unclear. "
        "Do not infer patterns. Do not guess. Do not assume every row has an answer. "
        "Return JSON only."
    )
    user_prompt = (
        f"Read only the {title} section. "
        f"Question labels are {prefix}1 through {prefix}{question_count}. "
        "Allowed values are A,B,C,D,F,G,H,J,blank,multiple,unclear. "
        "Use the rubric metadata only to know the question labels and legal choices, not to guess the student's answers.\n"
        + json.dumps(rubric_payload, separators=(",", ":"))
    )

    return {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_prompt},
                    {
                        "type": "input_image",
                        "image_url": encode_image_as_data_url(image),
                        "detail": "high",
                    },
                    {
                        "type": "input_text",
                        "text": (
                            "Return exactly this JSON shape: "
                            "{\"answers\": {\""
                            + prefix
                            + "1\": \"blank\"}, "
                            "\"sectionConfidence\": 0.0, "
                            "\"notes\": \"short factual note\"}"
                        ),
                    },
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_object",
            }
        },
    }


def build_section_rubric_payload(slug: str) -> dict[str, Any]:
    rubric = ACT_RUBRIC[slug]
    return {
        "test_name": ACT_SCORING_CONFIG["test_name"],
        "version": ACT_SCORING_CONFIG["version"],
        "section": {
            "slug": slug,
            "title": rubric["title"],
            "prefix": rubric["prefix"],
            "choices": rubric["choices"],
            "question_count_on_sheet": len(rubric["questions"]),
            "scored_count": rubric["scored_count"],
            "not_scored": sorted(rubric["not_scored"]),
        },
    }


def encode_image_as_data_url(image: Any) -> str:
    success, buffer = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("Failed to encode section image for AI scoring")
    encoded = base64.b64encode(buffer.tobytes()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def create_response(payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc


def extract_response_text(response_json: dict[str, Any]) -> str:
    output = response_json.get("output", [])
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def normalize_section_answers(answers: dict[str, Any], *, prefix: str, question_count: int) -> dict[str, str]:
    normalized = {}
    for question_number in range(1, question_count + 1):
        label = f"{prefix}{question_number}"
        value = answers.get(label, "blank")
        normalized[label] = normalize_answer_value(value)
    return normalized


def normalize_answer_value(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return "blank"

    upper = text.upper()
    if upper in {"A", "B", "C", "D", "F", "G", "H", "J"}:
        return upper

    lower = text.lower()
    if lower in ALLOWED_ANSWER_VALUES:
        return lower

    return "unclear"
