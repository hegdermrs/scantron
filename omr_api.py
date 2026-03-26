import base64
import json
import os
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile

PROJECT_ROOT = Path(__file__).resolve().parent
OMR_CHECKER_ROOT = PROJECT_ROOT / "vendor" / "OMRChecker"
if str(OMR_CHECKER_ROOT) not in sys.path:
    sys.path.insert(0, str(OMR_CHECKER_ROOT))


def load_dotenv_file(path: Path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv_file(PROJECT_ROOT / ".env")

from src.template import Template  # noqa: E402
from src.utils.parsing import get_concatenated_response, open_config_with_defaults  # noqa: E402
from act_scoring import score_detected_answers
from ai_scoring import score_sections_with_ai, should_use_ai

app = FastAPI(title="Scantron OMR API")

TEMPLATE_DIR = PROJECT_ROOT / "omr_templates" / "act_fixed"
TEMPLATE_PATH = TEMPLATE_DIR / "template.json"
CONFIG_PATH = TEMPLATE_DIR / "config.json"
ACT_ALT_BUBBLE_MAP = {"A": "F", "B": "G", "C": "H", "D": "J"}
ACT_CONFIDENT_ANSWERS = {"A", "B", "C", "D", "F", "G", "H", "J"}
ACT_ALT_QUESTION_SETS = {
    "EN": {10, 20, 30, 40, 50},
    "M": set(range(2, 46, 2)),
    "R": {8, 16, 24, 32, 36},
    "S": {8, 16, 24, 32, 40},
}
LABEL_PATTERN = re.compile(r"^([A-Z]+)(\d+)$")
FIELD_LABEL_PATTERN = re.compile(r"^([A-Z]+)(\d+)\.\.(\d+)$")
SECTION_PREFIXES = ("EN", "M", "R", "S")
SECTION_TITLES = {
    "EN": "English",
    "M": "Mathematics",
    "R": "Reading",
    "S": "Science",
}
ANSWER_OPTIONS = ("A", "B", "C", "D")
SECTION_BAND_PADDINGS = {
    "EN": {"top": 55, "bottom": 40},
    "M": {"top": 55, "bottom": 40},
    "R": {"top": 55, "bottom": 36},
    "S": {"top": 55, "bottom": 36},
}

ACT_TEMPLATE_LAYOUT = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
ACT_FIELD_LAYOUTS = []
for field_name, block in ACT_TEMPLATE_LAYOUT["fieldBlocks"].items():
    field_label = block["fieldLabels"][0]
    match = FIELD_LABEL_PATTERN.match(field_label)
    if not match:
        continue

    prefix, start_label, end_label = match.groups()
    ACT_FIELD_LAYOUTS.append(
        {
            "name": field_name,
            "prefix": prefix,
            "start": int(start_label),
            "end": int(end_label),
            "count": int(end_label) - int(start_label) + 1,
            "origin": tuple(block["origin"]),
            "bubblesGap": float(block["bubblesGap"]),
            "labelsGap": float(block["labelsGap"]),
        }
    )

ACT_FIELD_LAYOUTS.sort(key=lambda item: (item["origin"][1], item["origin"][0]))

SECTION_TEMPLATE_BOXES = {}
for prefix in SECTION_PREFIXES:
    layouts = [item for item in ACT_FIELD_LAYOUTS if item["prefix"] == prefix]
    if not layouts:
        continue

    min_x = min(item["origin"][0] for item in layouts)
    max_x = max(
        item["origin"][0] + ((len(ANSWER_OPTIONS) - 1) * item["bubblesGap"]) + ACT_TEMPLATE_LAYOUT["bubbleDimensions"][0]
        for item in layouts
    )
    min_y = min(item["origin"][1] for item in layouts)
    max_y = max(
        item["origin"][1] + ((item["count"] - 1) * item["labelsGap"]) + ACT_TEMPLATE_LAYOUT["bubbleDimensions"][1]
        for item in layouts
    )
    padding = SECTION_BAND_PADDINGS[prefix]
    SECTION_TEMPLATE_BOXES[prefix] = {
        "left": int(min_x - 40),
        "right": int(max_x + 32),
        "top": int(min_y - padding["top"]),
        "bottom": int(max_y + padding["bottom"]),
    }


@app.get("/")
async def root():
    return {
        "name": "Scantron OMR API",
        "status": "ok",
        "docs": "/docs",
        "gradeEndpoint": "/grade-act-sheet",
        "template": "act_page2_standard",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


class FixedActOmrEngine:
    def __init__(self, template_path: Path, config_path: Path):
        self.template_path = template_path
        self.config_path = config_path
        self.tuning_config = open_config_with_defaults(config_path)
        self.template = Template(template_path, self.tuning_config)

    def grade(
        self,
        *,
        content: bytes,
        submission_id: str = "",
        test_id: str = "",
        test_code: str = "",
        test_name: str = "",
        source: str = "",
        strategy: str = "",
    ):
        original_color = decode_bytes_to_color(content)
        if original_color is None:
            return self.build_failure_response(
                submission_id=submission_id,
                test_id=test_id,
                test_code=test_code,
                test_name=test_name,
                source=source,
                notes="Could not decode image",
            )

        original_gray = cv2.cvtColor(original_color, cv2.COLOR_BGR2GRAY)
        image_ops = self.template.image_instance_ops
        image_ops.reset_all_save_img()
        image_ops.append_save_img(1, original_gray)

        normalization = prepare_normalized_sheet(
            original_color=original_color,
            original_gray=original_gray,
            page_dimensions=tuple(self.template.page_dimensions),
        )
        normalized_gray = normalization["normalizedGray"]
        normalized_color = normalization["normalizedColor"]
        detection_overlay = normalization["detectionOverlay"]
        page_found = normalization["pageFound"]
        normalization_method = normalization["method"]
        image_ops.append_save_img(2, normalized_gray)

        ai_result = None
        if should_use_ai(strategy):
            ai_section_images = build_section_images_for_ai(normalized_gray)
            if ai_section_images is not None:
                try:
                    ai_result = score_sections_with_ai(section_images=ai_section_images, strategy=strategy)
                except Exception as exc:
                    ai_result = {
                        "answers": {},
                        "notes": f"ai_error={exc}",
                        "sectionConfidence": {},
                        "model": "",
                    }

        section_reader_result = try_extract_answers_by_section(normalized_gray)
        if ai_result and ai_result.get("answers"):
            answers = normalize_answers(ai_result["answers"])
            answer_summary = summarize_answers(answers)
            multi_marked = answer_summary["multiple_count"]
            extraction_method = "ai_section_reader"
            extracted_marked = section_reader_result["markedImage"] if section_reader_result else cv2.cvtColor(normalized_gray, cv2.COLOR_GRAY2BGR)
            effective_page_found = True
        elif section_reader_result is None:
            return self.build_failure_response(
                submission_id=submission_id,
                test_id=test_id,
                test_code=test_code,
                test_name=test_name,
                source=source,
                notes=(
                    "template=act_page2_standard, "
                    f"normalization={normalization_method}, "
                    "extraction=simple_section_reader_failed, "
                    f"page_found={page_found}, "
                    f"{normalization['notes']}"
                ).strip(", "),
            )
        else:
            answers = section_reader_result["answers"]
            answer_summary = section_reader_result["summary"]
            multi_marked = section_reader_result["multipleMarked"]
            extraction_method = "simple_section_reader"
            extracted_marked = section_reader_result["markedImage"]
            effective_page_found = page_found or section_reader_result is not None

        scoring_summary = score_detected_answers(answers)

        total_questions = len(answers)
        confident_answers = answer_summary["confident_count"]
        confidence = round(confident_answers / total_questions, 4) if total_questions else 0.0
        review_needed = (
            not effective_page_found
            or answer_summary["multiple_count"] > 0
            or answer_summary["unclear_count"] > 0
            or multi_marked > 0
        )
        final_status = "needs_review" if review_needed else "processed"

        notes_parts = [
            "template=act_page2_standard",
            "answer_labels=EN1-EN50,M1-M45,R1-R36,S1-S40",
            f"normalization={normalization_method}",
            f"extraction={extraction_method}",
            f"confident={answer_summary['confident_count']}",
            f"multiple={answer_summary['multiple_count']}",
            f"blank={answer_summary['blank_count']}",
            f"unclear={answer_summary['unclear_count']}",
            f"page_found={effective_page_found}",
        ]
        if normalization["notes"]:
            notes_parts.append(normalization["notes"])
        if section_reader_result is not None:
            notes_parts.append(section_reader_result["notes"])
        if ai_result is not None:
            notes_parts.append("ai_enabled=true")
            if ai_result.get("model"):
                notes_parts.append(f"ai_model={ai_result['model']}")
            if ai_result.get("notes"):
                notes_parts.append(ai_result["notes"])

        return {
            "submissionId": submission_id,
            "testId": test_id,
            "testCode": test_code,
            "testName": test_name,
            "source": source,
            "status": final_status,
            "finalStatus": final_status,
            "method": extraction_method,
            "finalMethod": extraction_method,
            "answers": answers,
            "finalAnswers": answers,
            "answerCount": total_questions,
            "confidence": confidence,
            "compositeScore": scoring_summary["compositeScore"],
            "sectionScores": scoring_summary["sectionScores"],
            "score": scoring_summary["score"],
            "total": scoring_summary["total"],
            "percent": scoring_summary["percent"],
            "compositeComputed": scoring_summary["compositeComputed"],
            "testName": scoring_summary["testName"],
            "version": scoring_summary["version"],
            "reviewNeeded": review_needed,
            "pageFound": effective_page_found,
            "notes": ", ".join(notes_parts),
            "debugImages": build_debug_images(
                original=original_color,
                normalized=normalized_color,
                processed=normalized_gray,
                final_marked=extracted_marked,
                detection_overlay=detection_overlay,
                save_img_list=image_ops.save_img_list,
            ),
        }

    @staticmethod
    def build_failure_response(
        *,
        submission_id: str,
        test_id: str,
        test_code: str,
        test_name: str,
        source: str,
        notes: str,
    ):
        return {
            "submissionId": submission_id,
            "testId": test_id,
            "testCode": test_code,
            "testName": test_name,
            "source": source,
            "status": "needs_review",
            "finalStatus": "needs_review",
            "method": "omrchecker",
            "finalMethod": "omrchecker",
            "answers": {},
            "finalAnswers": {},
            "answerCount": 0,
            "confidence": 0.0,
            "compositeScore": None,
            "sectionScores": {},
            "score": None,
            "total": None,
            "percent": None,
            "compositeComputed": False,
            "reviewNeeded": True,
            "pageFound": False,
            "notes": notes,
            "testName": "Prepmedians ACT PT 1",
            "version": "Enhanced ACT",
            "debugImages": {},
        }


ENGINE = FixedActOmrEngine(TEMPLATE_PATH, CONFIG_PATH)


def prepare_normalized_sheet(*, original_color, original_gray, page_dimensions):
    bright_result = try_bright_page_normalization(original_color, page_dimensions)
    if bright_result is not None:
        normalized_gray = finalize_normalized_sheet(bright_result["warpedGray"], page_dimensions)
        normalized_color = cv2.cvtColor(normalized_gray, cv2.COLOR_GRAY2BGR)
        return {
            "normalizedGray": normalized_gray,
            "normalizedColor": normalized_color,
            "detectionOverlay": bright_result["detectionOverlay"],
            "pageFound": True,
            "method": "bright_page_warp",
            "notes": bright_result["notes"],
        }

    section_line_result = try_section_line_normalization(original_color, page_dimensions)
    if section_line_result is not None:
        normalized_gray = finalize_normalized_sheet(section_line_result["warpedGray"], page_dimensions)
        normalized_color = cv2.cvtColor(normalized_gray, cv2.COLOR_GRAY2BGR)
        return {
            "normalizedGray": normalized_gray,
            "normalizedColor": normalized_color,
            "detectionOverlay": section_line_result["detectionOverlay"],
            "pageFound": True,
            "method": "section_line_crop",
            "notes": section_line_result["notes"],
        }

    projection_result = try_projection_crop_normalization(original_color, page_dimensions)
    if projection_result is not None:
        normalized_gray = finalize_normalized_sheet(projection_result["warpedGray"], page_dimensions)
        normalized_color = cv2.cvtColor(normalized_gray, cv2.COLOR_GRAY2BGR)
        return {
            "normalizedGray": normalized_gray,
            "normalizedColor": normalized_color,
            "detectionOverlay": projection_result["detectionOverlay"],
            "pageFound": True,
            "method": "projection_crop",
            "notes": projection_result["notes"],
        }

    resized_gray = cv2.resize(original_gray, page_dimensions, interpolation=cv2.INTER_LINEAR)
    normalized_gray = finalize_normalized_sheet(resized_gray, page_dimensions)
    normalized_color = cv2.cvtColor(normalized_gray, cv2.COLOR_GRAY2BGR)
    fallback_overlay = draw_image_border(original_color)
    return {
        "normalizedGray": normalized_gray,
        "normalizedColor": normalized_color,
        "detectionOverlay": fallback_overlay,
        "pageFound": False,
        "method": "resize_only_fallback",
        "notes": (
            "bright_page_detection_failed=true, "
            "section_line_detection_failed=true, "
            "projection_crop_failed=true"
        ),
    }


def try_omrchecker_crop(image_gray):
    uses_crop_page = any(
        processor.get("name") == "CropPage"
        for processor in ACT_TEMPLATE_LAYOUT.get("preProcessors", [])
    )
    if not uses_crop_page:
        return None

    image_ops = ENGINE.template.image_instance_ops
    processed = image_ops.apply_preprocessors("upload", image_gray, ENGINE.template)
    if processed is None:
        return None
    return processed


def try_bright_page_normalization(original_color, page_dimensions):
    gray = cv2.cvtColor(original_color, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.medianBlur(mask, 7)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    mask = cv2.dilate(mask, kernel, iterations=1)

    corners = find_document_corners(mask, gray.shape, page_dimensions, min_area_ratio=0.3)
    if corners is None:
        return None

    warped_color = four_point_transform(original_color, corners, page_dimensions)
    warped_gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)
    detection_overlay = original_color.copy()
    cv2.polylines(detection_overlay, [corners.astype(np.int32)], True, (255, 0, 0), 6)

    return {
        "warpedGray": warped_gray,
        "detectionOverlay": detection_overlay,
        "notes": "bright_page_detection=true",
    }


def try_low_saturation_page_normalization(original_color, page_dimensions):
    hsv = cv2.cvtColor(original_color, cv2.COLOR_BGR2HSV)
    h_channel, s_channel, v_channel = cv2.split(hsv)
    del h_channel

    low_s_mask = cv2.inRange(s_channel, 0, 72)
    bright_mask = cv2.inRange(v_channel, 120, 255)
    mask = cv2.bitwise_and(low_s_mask, bright_mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=1)

    corners = find_document_corners(mask, original_color.shape[:2], page_dimensions, min_area_ratio=0.22)
    if corners is None:
        return None

    warped_color = four_point_transform(original_color, corners, page_dimensions)
    warped_gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)
    detection_overlay = original_color.copy()
    cv2.polylines(detection_overlay, [corners.astype(np.int32)], True, (255, 255, 0), 6)

    return {
        "warpedGray": warped_gray,
        "detectionOverlay": detection_overlay,
        "notes": "low_saturation_page_detection=true",
    }


def try_section_line_normalization(original_color, page_dimensions):
    gray = cv2.cvtColor(original_color, cv2.COLOR_BGR2GRAY)
    enhanced = enhance_grayscale(gray)
    deskewed_gray, deskewed_color, angle = deskew_by_horizontal_lines(enhanced, original_color)

    binary = cv2.adaptiveThreshold(
        deskewed_gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        7,
    )
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(deskewed_gray.shape[1] // 8, 40), 3),
    )
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    horizontal = cv2.dilate(horizontal, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)), iterations=1)

    contours, _ = cv2.findContours(horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    line_boxes = []
    min_width = deskewed_gray.shape[1] * 0.45
    max_height = max(int(deskewed_gray.shape[0] * 0.018), 18)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= min_width and h <= max_height:
            line_boxes.append((x, y, w, h))

    merged_lines = merge_horizontal_line_boxes(line_boxes)
    if len(merged_lines) < 4:
        return None

    centers_y = [y + (h / 2.0) for _, y, _, h in merged_lines]
    top_idx = int(np.argmin(centers_y))
    bottom_idx = int(np.argmax(centers_y))
    top_line = merged_lines[top_idx]
    bottom_line = merged_lines[bottom_idx]

    left_candidates = np.array([x for x, _, _, _ in merged_lines], dtype=np.float32)
    right_candidates = np.array([x + w for x, _, w, _ in merged_lines], dtype=np.float32)
    left = int(max(0, np.percentile(left_candidates, 20) - (deskewed_gray.shape[1] * 0.03)))
    right = int(min(deskewed_gray.shape[1], np.percentile(right_candidates, 80) + (deskewed_gray.shape[1] * 0.03)))

    top_y = top_line[1]
    bottom_y = bottom_line[1] + bottom_line[3]
    vertical_span = max(bottom_y - top_y, 1)
    crop_top = int(max(0, top_y - (vertical_span * 0.16)))
    crop_bottom = int(min(deskewed_gray.shape[0], bottom_y + (vertical_span * 0.10)))

    cropped_color = deskewed_color[crop_top:crop_bottom, left:right]
    if cropped_color.size == 0:
        return None

    warped_color = cv2.resize(cropped_color, page_dimensions, interpolation=cv2.INTER_LINEAR)
    warped_gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)

    detection_overlay = deskewed_color.copy()
    for x, y, w, h in merged_lines:
        cv2.rectangle(detection_overlay, (x, y), (x + w, y + h), (0, 255, 255), 2)
    cv2.rectangle(detection_overlay, (left, crop_top), (right, crop_bottom), (0, 165, 255), 5)

    return {
        "warpedGray": warped_gray,
        "detectionOverlay": detection_overlay,
        "notes": f"section_line_detection=true, deskew_angle={angle:.2f}",
    }


def try_custom_perspective_normalization(original_color, page_dimensions):
    gray = cv2.cvtColor(original_color, cv2.COLOR_BGR2GRAY)
    enhanced = enhance_grayscale(gray)
    edges = build_document_edges(enhanced)
    corners = find_document_corners(edges, gray.shape, page_dimensions, min_area_ratio=0.2)
    if corners is None:
        return None

    warped_color = four_point_transform(original_color, corners, page_dimensions)
    warped_gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)
    detection_overlay = original_color.copy()
    cv2.polylines(detection_overlay, [corners.astype(np.int32)], True, (0, 255, 0), 6)

    return {
        "warpedGray": warped_gray,
        "detectionOverlay": detection_overlay,
        "notes": "custom_page_detection=true",
    }


def try_projection_crop_normalization(original_color, page_dimensions):
    gray = cv2.cvtColor(original_color, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (15, 15), 0)
    row_means = blurred.mean(axis=1)
    col_means = blurred.mean(axis=0)

    top, bottom = find_bright_band(row_means)
    left, right = find_bright_band(col_means)
    if None in {top, bottom, left, right}:
        return None

    height, width = gray.shape
    box_height = bottom - top
    box_width = right - left
    if box_height < height * 0.6 or box_width < width * 0.6:
        return None

    pad_y = int(box_height * 0.02)
    pad_x = int(box_width * 0.02)
    top = max(0, top - pad_y)
    bottom = min(height, bottom + pad_y)
    left = max(0, left - pad_x)
    right = min(width, right + pad_x)

    cropped_color = original_color[top:bottom, left:right]
    if cropped_color.size == 0:
        return None

    warped_color = cv2.resize(cropped_color, page_dimensions, interpolation=cv2.INTER_LINEAR)
    warped_gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)
    detection_overlay = original_color.copy()
    cv2.rectangle(detection_overlay, (left, top), (right, bottom), (0, 255, 255), 6)
    return {
        "warpedGray": warped_gray,
        "detectionOverlay": detection_overlay,
        "notes": "projection_crop_detection=true",
    }


def try_grabcut_page_normalization(original_color, page_dimensions):
    height, width = original_color.shape[:2]
    margin_x = max(int(width * 0.08), 12)
    margin_y = max(int(height * 0.06), 12)
    rect = (
        margin_x,
        margin_y,
        max(width - (margin_x * 2), 1),
        max(height - (margin_y * 2), 1),
    )

    mask = np.zeros((height, width), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(original_color, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return None

    foreground = np.where(
        (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
        255,
        0,
    ).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17))
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel, iterations=1)

    corners = find_document_corners(foreground, original_color.shape[:2], page_dimensions, min_area_ratio=0.16)
    if corners is None:
        return None

    warped_color = four_point_transform(original_color, corners, page_dimensions)
    warped_gray = cv2.cvtColor(warped_color, cv2.COLOR_BGR2GRAY)
    detection_overlay = original_color.copy()
    cv2.polylines(detection_overlay, [corners.astype(np.int32)], True, (255, 0, 255), 6)

    return {
        "warpedGray": warped_gray,
        "detectionOverlay": detection_overlay,
        "notes": "grabcut_page_detection=true",
    }


def deskew_by_horizontal_lines(image_gray, image_color):
    edges = cv2.Canny(image_gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=120,
        minLineLength=max(image_gray.shape[1] // 4, 80),
        maxLineGap=20,
    )
    angles = []
    if lines is not None:
        for line in lines[:, 0]:
            x1, y1, x2, y2 = line
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(angle) <= 20:
                angles.append(angle)

    if not angles:
        return image_gray, image_color, 0.0

    median_angle = float(np.median(angles))
    rotated_gray = rotate_image(image_gray, -median_angle)
    rotated_color = rotate_image(image_color, -median_angle)
    return rotated_gray, rotated_color, median_angle


def rotate_image(image, angle_degrees):
    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle_degrees, 1.0)
    border_value = 255 if image.ndim == 2 else (255, 255, 255)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )


def merge_horizontal_line_boxes(line_boxes):
    if not line_boxes:
        return []

    sorted_boxes = sorted(line_boxes, key=lambda box: box[1] + (box[3] / 2.0))
    merged = []
    current_group = [sorted_boxes[0]]
    current_center = sorted_boxes[0][1] + (sorted_boxes[0][3] / 2.0)

    for box in sorted_boxes[1:]:
        center_y = box[1] + (box[3] / 2.0)
        if abs(center_y - current_center) <= 18:
            current_group.append(box)
            current_center = float(np.mean([b[1] + (b[3] / 2.0) for b in current_group]))
            continue

        merged.append(combine_line_group(current_group))
        current_group = [box]
        current_center = center_y

    merged.append(combine_line_group(current_group))
    return merged


def combine_line_group(group):
    xs = [x for x, _, _, _ in group]
    ys = [y for _, y, _, _ in group]
    rights = [x + w for x, _, w, _ in group]
    bottoms = [y + h for _, y, _, h in group]
    left = int(min(xs))
    top = int(min(ys))
    right = int(max(rights))
    bottom = int(max(bottoms))
    return left, top, right - left, bottom - top


def find_bright_band(values):
    low = float(np.percentile(values, 15))
    high = float(np.percentile(values, 90))
    threshold = low + ((high - low) * 0.55)
    indices = np.where(values >= threshold)[0]
    if indices.size == 0:
        return None, None

    splits = np.split(indices, np.where(np.diff(indices) > 1)[0] + 1)
    longest = max(splits, key=len)
    return int(longest[0]), int(longest[-1])


def try_extract_answers_by_section(normalized_gray):
    variant_configs = [
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

    best_result = None
    best_score = float("-inf")
    for config in variant_configs:
        candidate = extract_answers_by_section_variant(normalized_gray, **config)
        if candidate is None:
            continue

        summary = candidate["summary"]
        score = (
            summary["confident_count"]
            - (summary["multiple_count"] * 1.5)
            - (summary["unclear_count"] * 1.5)
        )
        if score > best_score:
            best_score = score
            best_result = candidate

    return best_result


def extract_answers_by_section_variant(
    normalized_gray,
    *,
    variant_name,
    blank_threshold,
    multiple_min_threshold,
    multiple_margin_threshold,
    score_mode,
):
    binary_variants = dict(build_section_binary_variants(normalized_gray))
    binary = binary_variants.get(variant_name)
    if binary is None:
        return None

    section_bands = detect_section_bands(binary)
    if section_bands is None:
        return None

    marked = cv2.cvtColor(normalized_gray, cv2.COLOR_GRAY2BGR)
    extracted = {}
    multiple_marked = 0

    for prefix in SECTION_PREFIXES:
        if prefix not in section_bands or prefix not in SECTION_TEMPLATE_BOXES:
            return None

        actual_box = section_bands[prefix]
        template_box = SECTION_TEMPLATE_BOXES[prefix]
        x_scale = (actual_box["right"] - actual_box["left"]) / max(template_box["right"] - template_box["left"], 1)
        y_scale = (actual_box["bottom"] - actual_box["top"]) / max(template_box["bottom"] - template_box["top"], 1)
        section_layouts = [item for item in ACT_FIELD_LAYOUTS if item["prefix"] == prefix]

        for layout in section_layouts:
            base_x = actual_box["left"] + ((layout["origin"][0] - template_box["left"]) * x_scale)
            base_y = actual_box["top"] + ((layout["origin"][1] - template_box["top"]) * y_scale)
            bubble_gap = layout["bubblesGap"] * x_scale
            row_gap = layout["labelsGap"] * y_scale
            bubble_width = ACT_TEMPLATE_LAYOUT["bubbleDimensions"][0] * x_scale
            bubble_height = ACT_TEMPLATE_LAYOUT["bubbleDimensions"][1] * y_scale

            for offset in range(layout["count"]):
                question_number = layout["start"] + offset
                question_label = f"{prefix}{question_number}"
                row_y = base_y + (offset * row_gap)
                bubble_scores = []
                bubble_boxes = []

                for bubble_index in range(len(ANSWER_OPTIONS)):
                    x1 = int(round(base_x + (bubble_index * bubble_gap)))
                    y1 = int(round(row_y))
                    x2 = int(round(x1 + bubble_width))
                    y2 = int(round(y1 + bubble_height))
                    x1, y1, x2, y2 = clamp_box_to_image(x1, y1, x2, y2, binary.shape)
                    bubble_boxes.append((x1, y1, x2, y2))
                    bubble_scores.append(score_bubble_patch(binary, x1, y1, x2, y2, mode=score_mode))

                selected_answer = classify_bubble_scores(
                    bubble_scores,
                    blank_threshold=blank_threshold,
                    multiple_min_threshold=multiple_min_threshold,
                    multiple_margin_threshold=multiple_margin_threshold,
                )
                if selected_answer == "multiple":
                    multiple_marked += 1
                extracted[question_label] = normalize_single_answer(question_label, selected_answer)
                draw_bubble_decision(marked, bubble_boxes, selected_answer)

    summary = summarize_answers(extracted)
    for prefix, box in section_bands.items():
        title = SECTION_TITLES.get(prefix, prefix)
        cv2.rectangle(marked, (box["left"], box["top"]), (box["right"], box["bottom"]), (0, 200, 255), 2)
        cv2.putText(
            marked,
            title,
            (box["left"] + 8, max(20, box["top"] - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 200, 255),
            2,
            cv2.LINE_AA,
        )

    return {
        "answers": extracted,
        "summary": summary,
        "multipleMarked": multiple_marked,
        "markedImage": marked,
        "notes": f"section_reader_bands=true, section_binary={variant_name}, score_mode={score_mode}",
        "variantName": variant_name,
        "scoreMode": score_mode,
        "blankThreshold": blank_threshold,
        "multipleMinThreshold": multiple_min_threshold,
        "multipleMarginThreshold": multiple_margin_threshold,
    }


def detect_section_bands(binary):
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(binary.shape[1] // 6, 80), 3),
    )
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    horizontal = cv2.dilate(horizontal, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 3)), iterations=1)

    contours, _ = cv2.findContours(horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    line_boxes = []
    min_width = binary.shape[1] * 0.55
    max_height = max(int(binary.shape[0] * 0.02), 22)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= min_width and h <= max_height:
            line_boxes.append((x, y, w, h))

    merged_lines = merge_horizontal_line_boxes(line_boxes)
    if len(merged_lines) < 5:
        projection_lines = detect_section_lines_from_projection(horizontal)
        if projection_lines is not None:
            merged_lines = projection_lines
        else:
            return None

    strongest_lines = sorted(merged_lines, key=lambda box: box[2], reverse=True)[:8]
    strongest_lines = sorted(strongest_lines, key=lambda box: box[1] + (box[3] / 2.0))
    if len(strongest_lines) < 5:
        projection_lines = detect_section_lines_from_projection(horizontal)
        if projection_lines is not None:
            strongest_lines = projection_lines
        else:
            return None

    line_centers = [int(round(box[1] + (box[3] / 2.0))) for box in strongest_lines]
    gaps = [
        (line_centers[index + 1] - line_centers[index], index)
        for index in range(len(line_centers) - 1)
    ]
    if len(gaps) < 4:
        return None

    selected_gap_indexes = sorted(index for _, index in sorted(gaps, reverse=True)[:4])
    boundary_indexes = [0]
    boundary_indexes.extend(index + 1 for index in selected_gap_indexes)
    boundary_indexes.append(len(strongest_lines) - 1)
    boundary_indexes = sorted(set(boundary_indexes))
    candidate_lines = [strongest_lines[index] for index in boundary_indexes]
    candidate_lines = sorted(candidate_lines, key=lambda box: box[1] + (box[3] / 2.0))
    if len(candidate_lines) < 5:
        return None

    candidate_lines = candidate_lines[:5]
    left = int(max(0, np.percentile([box[0] for box in candidate_lines], 20) - (binary.shape[1] * 0.02)))
    right = int(
        min(
            binary.shape[1] - 1,
            np.percentile([box[0] + box[2] for box in candidate_lines], 80) + (binary.shape[1] * 0.02),
        )
    )

    bands = {}
    for prefix, upper, lower in zip(SECTION_PREFIXES, candidate_lines[:-1], candidate_lines[1:]):
        upper_center = int(round(upper[1] + (upper[3] / 2.0)))
        lower_center = int(round(lower[1] + (lower[3] / 2.0)))
        top = max(0, upper_center + 6)
        bottom = min(binary.shape[0] - 1, lower_center - 6)
        if bottom <= top:
            return None
        bands[prefix] = {
            "left": left,
            "right": right,
            "top": top,
            "bottom": bottom,
        }

    return bands


def build_section_binary_variants(image_gray):
    variants = []
    adaptive_strong = cv2.adaptiveThreshold(
        image_gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        35,
        10,
    )
    variants.append(("adaptive_strong", adaptive_strong))

    adaptive_soft = cv2.adaptiveThreshold(
        image_gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        7,
    )
    variants.append(("adaptive_soft", adaptive_soft))

    _, otsu_binary = cv2.threshold(
        image_gray,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    variants.append(("otsu", otsu_binary))

    return variants


def build_section_images_for_ai(normalized_gray):
    binary_variants = dict(build_section_binary_variants(normalized_gray))
    for variant_name, binary in binary_variants.items():
        section_bands = detect_section_bands(binary)
        if section_bands is None:
            continue

        section_images = {}
        for prefix in SECTION_PREFIXES:
            box = section_bands.get(prefix)
            if box is None:
                return None
            crop = binary[box["top"]:box["bottom"], box["left"]:box["right"]]
            if crop.size == 0:
                return None
            section_images[prefix] = crop

        section_images["_variant"] = variant_name
        return section_images

    return None


def detect_section_lines_from_projection(horizontal_binary):
    row_strength = horizontal_binary.sum(axis=1).astype(np.float32)
    if row_strength.size == 0:
        return None

    kernel_size = max(9, ((horizontal_binary.shape[0] // 120) * 2) + 1)
    smoothed = cv2.GaussianBlur(row_strength.reshape(-1, 1), (1, kernel_size), 0).reshape(-1)
    threshold = max(np.percentile(smoothed, 97), smoothed.max() * 0.55)
    peak_rows = np.where(smoothed >= threshold)[0]
    if peak_rows.size < 5:
        return None

    groups = np.split(peak_rows, np.where(np.diff(peak_rows) > max(6, kernel_size // 2))[0] + 1)
    candidate_rows = []
    for group in groups:
        if group.size == 0:
            continue
        center = int(round(float(group.mean())))
        candidate_rows.append(center)

    if len(candidate_rows) < 5:
        return None

    candidate_rows = sorted(candidate_rows)
    if len(candidate_rows) > 5:
        strengths = []
        for row in candidate_rows:
            start = max(0, row - 2)
            end = min(smoothed.shape[0], row + 3)
            strengths.append((float(smoothed[start:end].mean()), row))
        candidate_rows = sorted(row for _, row in sorted(strengths, reverse=True)[:5])

    if len(candidate_rows) < 5:
        return None

    line_width = horizontal_binary.shape[1]
    return [(0, row - 2, line_width, 4) for row in candidate_rows[:5]]


def enhance_grayscale(image_gray):
    blurred = cv2.GaussianBlur(image_gray, (5, 5), 0)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    enhanced = clahe.apply(blurred)
    return enhanced


def build_document_edges(image_gray):
    normalized = cv2.normalize(image_gray, None, 0, 255, cv2.NORM_MINMAX)
    edges = cv2.Canny(normalized, 60, 180)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    return edges


def find_document_corners(binary_image, image_shape, page_dimensions, min_area_ratio=0.2):
    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(image_shape[0] * image_shape[1])
    target_ratio = page_dimensions[0] / page_dimensions[1]
    best_candidate = None
    best_score = float("-inf")

    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < image_area * min_area_ratio:
            continue

        perimeter = cv2.arcLength(contour, True)
        approximation = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        candidates = []
        if len(approximation) == 4:
            candidates.append(approximation.reshape(4, 2).astype(np.float32))

        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect).astype(np.float32)
        if cv2.contourArea(box) >= image_area * min_area_ratio:
            candidates.append(box)

        for candidate in candidates:
            ordered = order_points(candidate)
            score = score_document_candidate(ordered, image_shape, image_area, target_ratio)
            if score > best_score:
                best_score = score
                best_candidate = ordered

    return best_candidate


def score_document_candidate(points, image_shape, image_area, target_ratio):
    area = cv2.contourArea(points.astype(np.float32))
    if area <= 0:
        return float("-inf")

    area_ratio = area / image_area
    if area_ratio > 0.94:
        return float("-inf")

    width_a = np.linalg.norm(points[2] - points[3])
    width_b = np.linalg.norm(points[1] - points[0])
    height_a = np.linalg.norm(points[1] - points[2])
    height_b = np.linalg.norm(points[0] - points[3])
    width = max(width_a, width_b, 1.0)
    height = max(height_a, height_b, 1.0)
    candidate_ratio = min(width, height) / max(width, height)
    ratio_penalty = abs(candidate_ratio - target_ratio)

    margin_x = image_shape[1] * 0.03
    margin_y = image_shape[0] * 0.03
    xs = points[:, 0]
    ys = points[:, 1]
    border_hits = 0
    if np.min(xs) <= margin_x:
        border_hits += 1
    if np.max(xs) >= image_shape[1] - margin_x:
        border_hits += 1
    if np.min(ys) <= margin_y:
        border_hits += 1
    if np.max(ys) >= image_shape[0] - margin_y:
        border_hits += 1

    if border_hits >= 4 and area_ratio > 0.82:
        return float("-inf")

    border_penalty = 0.14 * border_hits

    center_x = image_shape[1] / 2.0
    center_y = image_shape[0] / 2.0
    centroid = points.mean(axis=0)
    center_distance = np.linalg.norm(centroid - np.array([center_x, center_y], dtype=np.float32))
    max_distance = np.linalg.norm(np.array([center_x, center_y], dtype=np.float32))
    center_penalty = (center_distance / max(max_distance, 1.0)) * 0.1

    return area_ratio - (ratio_penalty * 1.8) - border_penalty - center_penalty


def order_points(points):
    rect = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1)

    rect[0] = points[np.argmin(sums)]
    rect[2] = points[np.argmax(sums)]
    rect[1] = points[np.argmin(diffs)]
    rect[3] = points[np.argmax(diffs)]
    return rect


def four_point_transform(image, points, page_dimensions):
    destination = np.array(
        [
            [0, 0],
            [page_dimensions[0] - 1, 0],
            [page_dimensions[0] - 1, page_dimensions[1] - 1],
            [0, page_dimensions[1] - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(points, destination)
    return cv2.warpPerspective(image, matrix, page_dimensions)


def finalize_normalized_sheet(image_gray, page_dimensions):
    resized = cv2.resize(image_gray, page_dimensions, interpolation=cv2.INTER_LINEAR)
    enhanced = enhance_grayscale(resized)
    return enhanced


def draw_image_border(image):
    overlay = image.copy()
    height, width = overlay.shape[:2]
    cv2.rectangle(overlay, (5, 5), (width - 5, height - 5), (0, 0, 255), 5)
    return overlay


def normalize_answers(raw_answers):
    normalized = {}
    for question, value in raw_answers.items():
        normalized[question] = normalize_single_answer(question, value)
    return normalized


def normalize_single_answer(question, value):
    answer = (value or "").strip()
    if answer == "" or answer.lower() == "blank":
        return "blank"

    if answer.lower() == "multiple":
        return "multiple"

    if len(answer) > 1:
        return "multiple"

    if answer not in {"A", "B", "C", "D"}:
        return "unclear"

    match = LABEL_PATTERN.match(question)
    if not match:
        return answer

    section, question_number = match.group(1), int(match.group(2))
    if question_number in ACT_ALT_QUESTION_SETS.get(section, set()):
        return ACT_ALT_BUBBLE_MAP.get(answer, answer)

    return answer


def summarize_answers(answers):
    summary = {
        "confident_count": 0,
        "multiple_count": 0,
        "blank_count": 0,
        "unclear_count": 0,
    }

    for answer in answers.values():
        if answer in ACT_CONFIDENT_ANSWERS:
            summary["confident_count"] += 1
        elif answer == "multiple":
            summary["multiple_count"] += 1
        elif answer == "blank":
            summary["blank_count"] += 1
        else:
            summary["unclear_count"] += 1

    return summary


def should_prefer_section_reader(section_reader_result, omr_summary, page_found):
    if section_reader_result is None:
        return False

    section_summary = section_reader_result["summary"]
    omr_score = (
        omr_summary["confident_count"]
        - (omr_summary["multiple_count"] * 2)
        - omr_summary["unclear_count"]
    )
    section_score = (
        section_summary["confident_count"]
        - (section_summary["multiple_count"] * 2)
        - section_summary["unclear_count"]
    )

    if not page_found and section_summary["confident_count"] >= omr_summary["confident_count"]:
        return True

    return section_score > omr_score + 6


def clamp_box_to_image(x1, y1, x2, y2, image_shape):
    height, width = image_shape[:2]
    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(x1 + 1, min(width, x2))
    y2 = max(y1 + 1, min(height, y2))
    return x1, y1, x2, y2


def score_bubble_patch(binary_image, x1, y1, x2, y2, mode="inner_mean"):
    patch = binary_image[y1:y2, x1:x2]
    if patch.size == 0:
        return 0.0

    inset_y = max(1, int(round((y2 - y1) * 0.22)))
    inset_x = max(1, int(round((x2 - x1) * 0.22)))
    inner = patch[
        inset_y: max(inset_y + 1, patch.shape[0] - inset_y),
        inset_x: max(inset_x + 1, patch.shape[1] - inset_x),
    ]
    if inner.size == 0:
        inner = patch

    if mode == "fill_ratio":
        return float(np.count_nonzero(inner) / inner.size)

    return float(np.mean(inner) / 255.0)


def classify_bubble_scores(
    scores,
    *,
    blank_threshold=0.12,
    multiple_min_threshold=0.10,
    multiple_margin_threshold=0.06,
):
    if not scores:
        return "blank"

    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    best_index, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if best_score < blank_threshold:
        return "blank"

    if second_score >= multiple_min_threshold and (best_score - second_score) < multiple_margin_threshold:
        return "multiple"

    return ANSWER_OPTIONS[best_index]


def draw_bubble_decision(image, bubble_boxes, selected_answer):
    option_index = None
    if selected_answer in ANSWER_OPTIONS:
        option_index = ANSWER_OPTIONS.index(selected_answer)

    for index, (x1, y1, x2, y2) in enumerate(bubble_boxes):
        color = (140, 140, 140)
        thickness = 1
        if selected_answer == "multiple":
            color = (0, 0, 255)
            thickness = 2
        elif selected_answer == "blank":
            color = (120, 120, 120)
        elif option_index == index:
            color = (0, 255, 0)
            thickness = 2

        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)


def encode_image_to_base64(image):
    if image is None:
        return None

    success, buffer = cv2.imencode(".jpg", image)
    if not success:
        return None

    return base64.b64encode(buffer.tobytes()).decode("utf-8")


def build_debug_images(*, original, normalized, processed, final_marked, detection_overlay, save_img_list):
    debug_images = {}

    original_base64 = encode_image_to_base64(original)
    normalized_base64 = encode_image_to_base64(normalized)
    processed_base64 = encode_image_to_base64(processed)
    marked_base64 = encode_image_to_base64(final_marked)
    detection_base64 = encode_image_to_base64(detection_overlay)

    if original_base64:
        debug_images["originalImageBase64"] = original_base64
    if normalized_base64:
        debug_images["normalizedImageBase64"] = normalized_base64
    if processed_base64:
        debug_images["processedImageBase64"] = processed_base64
    if marked_base64:
        debug_images["finalMarkedImageBase64"] = marked_base64
    if detection_base64:
        debug_images["detectionOverlayBase64"] = detection_base64

    for level, images in save_img_list.items():
        if images:
            stack_base64 = encode_image_to_base64(images[-1])
            if stack_base64:
                debug_images[f"debugLevel{level}Base64"] = stack_base64

    return debug_images


def decode_bytes_to_color(content: bytes):
    image_array = np.frombuffer(content, dtype=np.uint8)
    return cv2.imdecode(image_array, cv2.IMREAD_COLOR)


def grade_upload(content: bytes, submission_id="", test_id="", test_code="", test_name="", source="", strategy=""):
    return ENGINE.grade(
        content=content,
        submission_id=submission_id,
        test_id=test_id,
        test_code=test_code,
        test_name=test_name,
        source=source,
        strategy=strategy,
    )


@app.post("/grade-act-sheet")
async def grade_act_sheet(
    file: UploadFile = File(...),
    submissionId: str = Form(""),
    testId: str = Form(""),
    testCode: str = Form(""),
    testName: str = Form(""),
    source: str = Form(""),
    strategy: str = Form(""),
):
    content = await file.read()
    return grade_upload(
        content,
        submission_id=submissionId,
        test_id=testId,
        test_code=testCode,
        test_name=testName,
        source=source,
        strategy=strategy,
    )


@app.post("/preprocess")
async def preprocess_omr(
    file: UploadFile = File(...),
    submissionId: str = Form(""),
    testId: str = Form(""),
    testCode: str = Form(""),
    testName: str = Form(""),
    source: str = Form(""),
    strategy: str = Form(""),
):
    content = await file.read()
    return grade_upload(
        content,
        submission_id=submissionId,
        test_id=testId,
        test_code=testCode,
        test_name=testName,
        source=source,
        strategy=strategy,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
