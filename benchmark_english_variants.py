import json
from pathlib import Path

import omr_api


EXPECTED_ENGLISH = {
    "EN1": "A",
    "EN2": "H",
    "EN3": "B",
    "EN4": "H",
    "EN5": "C",
    "EN6": "G",
    "EN7": "C",
    "EN8": "G",
    "EN9": "D",
    "EN10": "G",
    "EN11": "blank",
    "EN12": "F",
    "EN13": "B",
    "EN14": "H",
    "EN15": "blank",
    "EN16": "D",
}


VARIANT_CONFIGS = [
    {
        "variant_name": "adaptive_strong",
        "blank_threshold": 0.12,
        "multiple_min_threshold": 0.10,
        "multiple_margin_threshold": 0.06,
        "score_mode": "inner_mean",
    },
    {
        "variant_name": "adaptive_soft",
        "blank_threshold": 0.115,
        "multiple_min_threshold": 0.095,
        "multiple_margin_threshold": 0.055,
        "score_mode": "inner_mean",
    },
    {
        "variant_name": "adaptive_strong",
        "blank_threshold": 0.11,
        "multiple_min_threshold": 0.085,
        "multiple_margin_threshold": 0.05,
        "score_mode": "fill_ratio",
    },
    {
        "variant_name": "adaptive_soft",
        "blank_threshold": 0.105,
        "multiple_min_threshold": 0.08,
        "multiple_margin_threshold": 0.045,
        "score_mode": "fill_ratio",
    },
    {
        "variant_name": "otsu",
        "blank_threshold": 0.11,
        "multiple_min_threshold": 0.09,
        "multiple_margin_threshold": 0.05,
        "score_mode": "fill_ratio",
    },
]

ENGLISH_OFFSETS = [-36, -24, -12, 0, 12, 24, 36]
ENGLISH_Y_OFFSETS = [-24, -12, 0, 12, 24]
ENGLISH_X_SCALES = [0.92, 0.96, 1.0, 1.04, 1.08]
ENGLISH_Y_SCALES = [0.92, 0.96, 1.0, 1.04, 1.08]


def score_variant(predicted):
    exact = 0
    blanks_correct = 0
    wrong = []
    for label, expected in EXPECTED_ENGLISH.items():
        actual = predicted.get(label, "missing")
        if actual == expected:
            exact += 1
            if expected == "blank":
                blanks_correct += 1
        else:
            wrong.append({"label": label, "expected": expected, "actual": actual})
    return {
        "exactMatches": exact,
        "blankMatches": blanks_correct,
        "totalChecked": len(EXPECTED_ENGLISH),
        "wrong": wrong,
    }


def main():
    image_path = Path("debug-original.jpg")
    if not image_path.exists():
        raise SystemExit("debug-original.jpg not found")

    image_bytes = image_path.read_bytes()
    original_color = omr_api.decode_bytes_to_color(image_bytes)
    original_gray = omr_api.cv2.cvtColor(original_color, omr_api.cv2.COLOR_BGR2GRAY)
    normalization = omr_api.prepare_normalized_sheet(
        original_color=original_color,
        original_gray=original_gray,
        page_dimensions=tuple(omr_api.ENGINE.template.page_dimensions),
    )
    normalized_gray = normalization["normalizedGray"]

    results = []
    for config in VARIANT_CONFIGS:
        candidate = omr_api.extract_answers_by_section_variant(normalized_gray, **config)
        if candidate is None:
            results.append(
                {
                    **config,
                    "usable": False,
                    "exactMatches": 0,
                    "blankMatches": 0,
                    "totalChecked": len(EXPECTED_ENGLISH),
                    "wrong": [{"label": "ALL", "expected": "n/a", "actual": "section_detection_failed"}],
                }
            )
            continue

        scored = score_variant(candidate["answers"])
        results.append(
            {
                **config,
                "usable": True,
                **scored,
            }
        )

    results.sort(
        key=lambda item: (
            item["exactMatches"],
            item["blankMatches"],
            1 if item["usable"] else 0,
        ),
        reverse=True,
    )

    best_variant = next((item for item in results if item.get("usable")), None)
    geometry_results = []
    if best_variant:
        base_config = {
            "variant_name": best_variant["variant_name"],
            "blank_threshold": best_variant["blank_threshold"],
            "multiple_min_threshold": best_variant["multiple_min_threshold"],
            "multiple_margin_threshold": best_variant["multiple_margin_threshold"],
            "score_mode": best_variant["score_mode"],
        }
        for x_offset in ENGLISH_OFFSETS:
            for y_offset in ENGLISH_Y_OFFSETS:
                for x_scale_adjust in ENGLISH_X_SCALES:
                    for y_scale_adjust in ENGLISH_Y_SCALES:
                        candidate = extract_english_with_geometry(
                            normalized_gray,
                            x_offset=x_offset,
                            y_offset=y_offset,
                            x_scale_adjust=x_scale_adjust,
                            y_scale_adjust=y_scale_adjust,
                            **base_config,
                        )
                        if candidate is None:
                            continue

                        scored = score_variant(candidate["answers"])
                        geometry_results.append(
                            {
                                "xOffset": x_offset,
                                "yOffset": y_offset,
                                "xScaleAdjust": x_scale_adjust,
                                "yScaleAdjust": y_scale_adjust,
                                **scored,
                            }
                        )

        geometry_results.sort(
            key=lambda item: (item["exactMatches"], item["blankMatches"]),
            reverse=True,
        )

    output = {
        "normalization": normalization["method"],
        "results": results,
        "bestGeometry": geometry_results[:10],
    }
    print(json.dumps(output, indent=2))


def extract_english_with_geometry(
    normalized_gray,
    *,
    variant_name,
    blank_threshold,
    multiple_min_threshold,
    multiple_margin_threshold,
    score_mode,
    x_offset,
    y_offset,
    x_scale_adjust,
    y_scale_adjust,
):
    binary_variants = dict(omr_api.build_section_binary_variants(normalized_gray))
    binary = binary_variants.get(variant_name)
    if binary is None:
        return None

    section_bands = omr_api.detect_section_bands(binary)
    if section_bands is None or "EN" not in section_bands:
        return None

    actual_box = dict(section_bands["EN"])
    actual_box["left"] = int(actual_box["left"] + x_offset)
    actual_box["right"] = int(actual_box["right"] + x_offset)
    actual_box["top"] = int(actual_box["top"] + y_offset)
    actual_box["bottom"] = int(actual_box["bottom"] + y_offset)

    template_box = omr_api.SECTION_TEMPLATE_BOXES["EN"]
    x_scale = ((actual_box["right"] - actual_box["left"]) / max(template_box["right"] - template_box["left"], 1)) * x_scale_adjust
    y_scale = ((actual_box["bottom"] - actual_box["top"]) / max(template_box["bottom"] - template_box["top"], 1)) * y_scale_adjust

    extracted = {}
    section_layouts = [item for item in omr_api.ACT_FIELD_LAYOUTS if item["prefix"] == "EN"]
    for layout in section_layouts:
        base_x = actual_box["left"] + ((layout["origin"][0] - template_box["left"]) * x_scale)
        base_y = actual_box["top"] + ((layout["origin"][1] - template_box["top"]) * y_scale)
        bubble_gap = layout["bubblesGap"] * x_scale
        row_gap = layout["labelsGap"] * y_scale
        bubble_width = omr_api.ACT_TEMPLATE_LAYOUT["bubbleDimensions"][0] * x_scale
        bubble_height = omr_api.ACT_TEMPLATE_LAYOUT["bubbleDimensions"][1] * y_scale

        for offset in range(layout["count"]):
            question_number = layout["start"] + offset
            question_label = f"EN{question_number}"
            row_y = base_y + (offset * row_gap)
            bubble_scores = []

            for bubble_index in range(len(omr_api.ANSWER_OPTIONS)):
                x1 = int(round(base_x + (bubble_index * bubble_gap)))
                y1 = int(round(row_y))
                x2 = int(round(x1 + bubble_width))
                y2 = int(round(y1 + bubble_height))
                x1, y1, x2, y2 = omr_api.clamp_box_to_image(x1, y1, x2, y2, binary.shape)
                bubble_scores.append(omr_api.score_bubble_patch(binary, x1, y1, x2, y2, mode=score_mode))

            selected_answer = omr_api.classify_bubble_scores(
                bubble_scores,
                blank_threshold=blank_threshold,
                multiple_min_threshold=multiple_min_threshold,
                multiple_margin_threshold=multiple_margin_threshold,
            )
            extracted[question_label] = omr_api.normalize_single_answer(question_label, selected_answer)

    return {"answers": extracted}


if __name__ == "__main__":
    main()
