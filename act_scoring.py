from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

ACT_SCORING_CONFIG = {
    "test_name": "Prepmedians ACT PT 1",
    "version": "Enhanced ACT",
    "composite_rule": {
        "include_sections": ["english", "math", "reading"],
        "rounding": "nearest_whole_half_up",
        "exclude_if_blank_section": True,
    },
}

ACT_RUBRIC = {
    "english": {
        "title": "English",
        "prefix": "EN",
        "choices": ["A", "B", "C", "D", "F", "G", "H", "J"],
        "scored_count": 40,
        "not_scored": {41, 42, 43, 44, 45, 46, 47, 48, 49, 50},
        "questions": {
            1: {"answer": "C", "category": "CSE", "scored": True},
            2: {"answer": "G", "category": "CSE", "scored": True},
            3: {"answer": "A", "category": "POW", "scored": True},
            4: {"answer": "F", "category": "POW", "scored": True},
            5: {"answer": "A", "category": "CSE", "scored": True},
            6: {"answer": "F", "category": "KLA", "scored": True},
            7: {"answer": "D", "category": "KLA", "scored": True},
            8: {"answer": "J", "category": "CSE", "scored": True},
            9: {"answer": "B", "category": "CSE", "scored": True},
            10: {"answer": "G", "category": "KLA", "scored": True},
            11: {"answer": "B", "category": "CSE", "scored": True},
            12: {"answer": "J", "category": "CSE", "scored": True},
            13: {"answer": "C", "category": "KLA", "scored": True},
            14: {"answer": "H", "category": "POW", "scored": True},
            15: {"answer": "D", "category": "POW", "scored": True},
            16: {"answer": "J", "category": "CSE", "scored": True},
            17: {"answer": "D", "category": "KLA", "scored": True},
            18: {"answer": "H", "category": "POW", "scored": True},
            19: {"answer": "A", "category": "KLA", "scored": True},
            20: {"answer": "J", "category": "POW", "scored": True},
            21: {"answer": "A", "category": "CSE", "scored": True},
            22: {"answer": "F", "category": "CSE", "scored": True},
            23: {"answer": "C", "category": "POW", "scored": True},
            24: {"answer": "H", "category": "POW", "scored": True},
            25: {"answer": "D", "category": "POW", "scored": True},
            26: {"answer": "G", "category": "POW", "scored": True},
            27: {"answer": "D", "category": "CSE", "scored": True},
            28: {"answer": "F", "category": "CSE", "scored": True},
            29: {"answer": "A", "category": "CSE", "scored": True},
            30: {"answer": "G", "category": "POW", "scored": True},
            31: {"answer": "C", "category": "CSE", "scored": True},
            32: {"answer": "F", "category": "POW", "scored": True},
            33: {"answer": "A", "category": "CSE", "scored": True},
            34: {"answer": "H", "category": "KLA", "scored": True},
            35: {"answer": "A", "category": "POW", "scored": True},
            36: {"answer": "G", "category": "POW", "scored": True},
            37: {"answer": "B", "category": "POW", "scored": True},
            38: {"answer": "H", "category": "CSE", "scored": True},
            39: {"answer": "D", "category": "KLA", "scored": True},
            40: {"answer": "J", "category": "CSE", "scored": True},
            41: {"answer": "A", "category": None, "scored": False},
            42: {"answer": "G", "category": None, "scored": False},
            43: {"answer": "D", "category": None, "scored": False},
            44: {"answer": "H", "category": None, "scored": False},
            45: {"answer": "D", "category": None, "scored": False},
            46: {"answer": "F", "category": None, "scored": False},
            47: {"answer": "B", "category": None, "scored": False},
            48: {"answer": "F", "category": None, "scored": False},
            49: {"answer": "D", "category": None, "scored": False},
            50: {"answer": "H", "category": None, "scored": False},
        },
        "scale": {40: 36, 39: 35, 38: 35, 37: 33, 36: 31, 35: 29, 34: 28, 33: 27, 32: 26, 31: 25, 30: 24, 29: 23, 28: 22, 27: 22, 26: 21, 25: 20, 24: 20, 23: 19, 22: 18, 21: 17, 20: 16, 19: 15, 18: 15, 17: 14, 16: 13, 15: 13, 14: 12, 13: 11, 12: 11, 11: 10, 10: 10, 9: 10, 8: 9, 7: 8, 6: 7, 5: 7, 4: 6, 3: 5, 2: 3, 1: 2, 0: 1},
    },
    "math": {
        "title": "Mathematics",
        "prefix": "M",
        "choices": ["A", "B", "C", "D", "F", "G", "H", "J"],
        "scored_count": 41,
        "not_scored": {7, 16, 29, 40},
        "questions": {
            1: {"answer": "D", "category": "IES", "scored": True}, 2: {"answer": "J", "category": "S", "scored": True}, 3: {"answer": "B", "category": "IES", "scored": True}, 4: {"answer": "F", "category": "IES", "scored": True}, 5: {"answer": "C", "category": "A", "scored": True},
            6: {"answer": "J", "category": "N", "scored": True}, 7: {"answer": "B", "category": None, "scored": False}, 8: {"answer": "H", "category": "N", "scored": True}, 9: {"answer": "D", "category": "A", "scored": True}, 10: {"answer": "H", "category": "IES", "scored": True},
            11: {"answer": "B", "category": "IES", "scored": True}, 12: {"answer": "J", "category": "S", "scored": True}, 13: {"answer": "A", "category": "G", "scored": True}, 14: {"answer": "J", "category": "IES", "scored": True}, 15: {"answer": "A", "category": "A", "scored": True},
            16: {"answer": "G", "category": None, "scored": False}, 17: {"answer": "A", "category": "A", "scored": True}, 18: {"answer": "J", "category": "N", "scored": True}, 19: {"answer": "B", "category": "F", "scored": True}, 20: {"answer": "H", "category": "G", "scored": True},
            21: {"answer": "C", "category": "IES", "scored": True}, 22: {"answer": "G", "category": "IES", "scored": True}, 23: {"answer": "C", "category": "F", "scored": True}, 24: {"answer": "G", "category": "F", "scored": True}, 25: {"answer": "A", "category": "F", "scored": True},
            26: {"answer": "G", "category": "A", "scored": True}, 27: {"answer": "B", "category": "S", "scored": True}, 28: {"answer": "F", "category": "G", "scored": True}, 29: {"answer": "C", "category": None, "scored": False}, 30: {"answer": "J", "category": "G", "scored": True},
            31: {"answer": "C", "category": "G", "scored": True}, 32: {"answer": "J", "category": "IES", "scored": True}, 33: {"answer": "C", "category": "IES", "scored": True}, 34: {"answer": "G", "category": "IES", "scored": True}, 35: {"answer": "C", "category": "IES", "scored": True},
            36: {"answer": "J", "category": "S", "scored": True}, 37: {"answer": "C", "category": "A", "scored": True}, 38: {"answer": "J", "category": "IES", "scored": True}, 39: {"answer": "C", "category": "S", "scored": True}, 40: {"answer": "J", "category": None, "scored": False},
            41: {"answer": "D", "category": "IES", "scored": True}, 42: {"answer": "F", "category": "IES", "scored": True}, 43: {"answer": "C", "category": "IES", "scored": True}, 44: {"answer": "J", "category": "F", "scored": True}, 45: {"answer": "A", "category": "S", "scored": True},
        },
        "scale": {41: 36, 40: 36, 39: 35, 38: 34, 37: 34, 36: 33, 35: 32, 34: 31, 33: 30, 32: 29, 31: 29, 30: 28, 29: 27, 28: 27, 27: 26, 26: 25, 25: 24, 24: 23, 23: 22, 22: 21, 21: 20, 20: 19, 19: 19, 18: 18, 17: 17, 16: 17, 15: 17, 14: 16, 13: 16, 12: 15, 11: 15, 10: 15, 9: 14, 8: 14, 7: 13, 6: 13, 5: 12, 4: 11, 3: 9, 2: 7, 1: 5, 0: 1},
    },
    "reading": {
        "title": "Reading",
        "prefix": "R",
        "choices": ["A", "B", "C", "D", "F", "G", "H", "J"],
        "scored_count": 27,
        "not_scored": {1, 2, 3, 4, 5, 6, 7, 8, 9},
        "questions": {
            1: {"answer": "D", "category": None, "scored": False}, 2: {"answer": "H", "category": None, "scored": False}, 3: {"answer": "A", "category": None, "scored": False}, 4: {"answer": "J", "category": None, "scored": False}, 5: {"answer": "C", "category": None, "scored": False},
            6: {"answer": "G", "category": None, "scored": False}, 7: {"answer": "A", "category": None, "scored": False}, 8: {"answer": "F", "category": None, "scored": False}, 9: {"answer": "A", "category": None, "scored": False}, 10: {"answer": "J", "category": "CS", "scored": True},
            11: {"answer": "B", "category": "KID", "scored": True}, 12: {"answer": "H", "category": "KID", "scored": True}, 13: {"answer": "B", "category": "CS", "scored": True}, 14: {"answer": "J", "category": "CS", "scored": True}, 15: {"answer": "C", "category": "KID", "scored": True},
            16: {"answer": "J", "category": "KID", "scored": True}, 17: {"answer": "C", "category": "CS", "scored": True}, 18: {"answer": "F", "category": "CS", "scored": True}, 19: {"answer": "B", "category": "KID", "scored": True}, 20: {"answer": "H", "category": "CS", "scored": True},
            21: {"answer": "D", "category": "KID", "scored": True}, 22: {"answer": "H", "category": "KID", "scored": True}, 23: {"answer": "A", "category": "KID", "scored": True}, 24: {"answer": "H", "category": "KID", "scored": True}, 25: {"answer": "D", "category": "IKI", "scored": True},
            26: {"answer": "F", "category": "IKI", "scored": True}, 27: {"answer": "B", "category": "IKI", "scored": True}, 28: {"answer": "J", "category": "IKI", "scored": True}, 29: {"answer": "D", "category": "KID", "scored": True}, 30: {"answer": "F", "category": "CS", "scored": True},
            31: {"answer": "A", "category": "KID", "scored": True}, 32: {"answer": "G", "category": "CS", "scored": True}, 33: {"answer": "C", "category": "KID", "scored": True}, 34: {"answer": "J", "category": "IKI", "scored": True}, 35: {"answer": "B", "category": "KID", "scored": True}, 36: {"answer": "H", "category": "CS", "scored": True},
        },
        "scale": {27: 36, 26: 35, 25: 34, 24: 32, 23: 30, 22: 28, 21: 26, 20: 25, 19: 24, 18: 23, 17: 22, 16: 21, 15: 20, 14: 18, 13: 17, 12: 16, 11: 15, 10: 14, 9: 13, 8: 12, 7: 12, 6: 11, 5: 10, 4: 9, 3: 7, 2: 5, 1: 3, 0: 1},
    },
    "science": {
        "title": "Science",
        "prefix": "S",
        "choices": ["A", "B", "C", "D", "F", "G", "H", "J"],
        "scored_count": 34,
        "not_scored": {29, 30, 31, 32, 33, 34},
        "questions": {
            1: {"answer": "A", "category": "IOD", "scored": True}, 2: {"answer": "F", "category": "IOD", "scored": True}, 3: {"answer": "D", "category": "IOD", "scored": True}, 4: {"answer": "H", "category": "IOD", "scored": True}, 5: {"answer": "D", "category": "EMI", "scored": True},
            6: {"answer": "F", "category": "EMI", "scored": True}, 7: {"answer": "C", "category": "EMI", "scored": True}, 8: {"answer": "J", "category": "IOD", "scored": True}, 9: {"answer": "C", "category": "EMI", "scored": True}, 10: {"answer": "F", "category": "EMI", "scored": True},
            11: {"answer": "C", "category": "EMI", "scored": True}, 12: {"answer": "G", "category": "EMI", "scored": True}, 13: {"answer": "C", "category": "EMI", "scored": True}, 14: {"answer": "H", "category": "SIN", "scored": True}, 15: {"answer": "B", "category": "SIN", "scored": True},
            16: {"answer": "H", "category": "SIN", "scored": True}, 17: {"answer": "B", "category": "SIN", "scored": True}, 18: {"answer": "F", "category": "SIN", "scored": True}, 19: {"answer": "D", "category": "SIN", "scored": True}, 20: {"answer": "F", "category": "EMI", "scored": True},
            21: {"answer": "C", "category": "SIN", "scored": True}, 22: {"answer": "J", "category": "IOD", "scored": True}, 23: {"answer": "C", "category": "SIN", "scored": True}, 24: {"answer": "J", "category": "IOD", "scored": True}, 25: {"answer": "B", "category": "IOD", "scored": True},
            26: {"answer": "J", "category": "IOD", "scored": True}, 27: {"answer": "D", "category": "IOD", "scored": True}, 28: {"answer": "G", "category": "IOD", "scored": True}, 29: {"answer": "D", "category": None, "scored": False}, 30: {"answer": "J", "category": None, "scored": False},
            31: {"answer": "C", "category": None, "scored": False}, 32: {"answer": "J", "category": None, "scored": False}, 33: {"answer": "D", "category": None, "scored": False}, 34: {"answer": "F", "category": None, "scored": False}, 35: {"answer": "B", "category": "IOD", "scored": True},
            36: {"answer": "F", "category": "SIN", "scored": True}, 37: {"answer": "B", "category": "IOD", "scored": True}, 38: {"answer": "G", "category": "IOD", "scored": True}, 39: {"answer": "C", "category": "IOD", "scored": True}, 40: {"answer": "J", "category": "IOD", "scored": True},
        },
        "scale": {34: 36, 33: 35, 32: 34, 31: 33, 30: 32, 29: 31, 28: 30, 27: 29, 26: 28, 25: 27, 24: 26, 23: 25, 22: 25, 21: 24, 20: 23, 19: 23, 18: 22, 17: 21, 16: 20, 15: 19, 14: 18, 13: 18, 12: 17, 11: 16, 10: 15, 9: 14, 8: 12, 7: 12, 6: 11, 5: 10, 4: 9, 3: 7, 2: 6, 1: 3, 0: 1},
    },
}

CATEGORY_GROUPS = {
    "math": {
        "PHM": ["A", "F", "G", "N", "S"],
    },
}

COMPOSITE_SECTIONS = tuple(ACT_SCORING_CONFIG["composite_rule"]["include_sections"])


def normalize_detected_answer(value: str | None) -> str:
    if not value:
        return "blank"
    normalized = str(value).strip().upper()
    if normalized in {"A", "B", "C", "D", "F", "G", "H", "J"}:
        return normalized
    if normalized in {"BLANK", "MULTIPLE", "UNCLEAR"}:
        return normalized.lower()
    return "unclear"


def round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def score_detected_answers(detected_answers: dict[str, str] | None):
    detected_answers = detected_answers or {}
    section_scores = {}

    for slug, rubric in ACT_RUBRIC.items():
        category_scores = {}
        raw_score = 0
        scored_questions = 0
        answered_scored_questions = 0
        correct_labels = []

        for question_number, meta in rubric["questions"].items():
            label = f"{rubric['prefix']}{question_number}"
            detected = normalize_detected_answer(detected_answers.get(label))
            if not meta["scored"]:
                continue

            scored_questions += 1
            if detected not in {"blank", "multiple", "unclear"}:
                answered_scored_questions += 1

            category = meta["category"]
            category_bucket = category_scores.setdefault(category, {"correct": 0, "total": 0})
            category_bucket["total"] += 1

            if detected == meta["answer"]:
                raw_score += 1
                category_bucket["correct"] += 1
                correct_labels.append(label)

        for group_name, member_categories in CATEGORY_GROUPS.get(slug, {}).items():
            category_scores[group_name] = {
                "correct": sum(category_scores.get(member, {"correct": 0})["correct"] for member in member_categories),
                "total": sum(category_scores.get(member, {"total": 0})["total"] for member in member_categories),
            }

        scale_score = rubric["scale"].get(raw_score)
        section_scores[slug] = {
            "title": rubric["title"],
            "rawScore": raw_score,
            "maxRaw": scored_questions,
            "scaleScore": scale_score,
            "answeredScoredQuestions": answered_scored_questions,
            "blankSection": answered_scored_questions == 0,
            "categoryScores": category_scores,
            "correctLabels": correct_labels,
        }

    required_blank = any(section_scores[slug]["blankSection"] for slug in COMPOSITE_SECTIONS)
    if required_blank:
        composite_score = None
        percent = None
        total = None
    else:
        composite_average = sum(section_scores[slug]["scaleScore"] for slug in COMPOSITE_SECTIONS) / len(COMPOSITE_SECTIONS)
        composite_score = round_half_up(composite_average)
        total = 36
        percent = round((composite_score / total) * 100, 1)

    return {
        "testName": ACT_SCORING_CONFIG["test_name"],
        "version": ACT_SCORING_CONFIG["version"],
        "sectionScores": section_scores,
        "compositeScore": composite_score,
        "score": composite_score,
        "total": total,
        "percent": percent,
        "compositeComputed": not required_blank,
    }
