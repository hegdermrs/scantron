from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

import omr_api


DEFAULT_VARIANT = "adaptive_soft"
DEFAULT_SCORE_MODE = "fill_ratio"


def main():
    parser = argparse.ArgumentParser(description="Export ACT section row crops for ML labeling.")
    parser.add_argument("--image", required=True, help="Path to source image")
    parser.add_argument("--out", default="training_rows", help="Output directory")
    parser.add_argument("--section", choices=["EN", "M", "R", "S", "all"], default="EN")
    parser.add_argument("--variant", default=DEFAULT_VARIANT, choices=["adaptive_strong", "adaptive_soft", "otsu"])
    parser.add_argument("--json-manifest", action="store_true", help="Write manifest.json")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    image_bytes = image_path.read_bytes()
    original_color = omr_api.decode_bytes_to_color(image_bytes)
    if original_color is None:
        raise SystemExit("Could not decode image")

    original_gray = cv2.cvtColor(original_color, cv2.COLOR_BGR2GRAY)
    normalization = omr_api.prepare_normalized_sheet(
        original_color=original_color,
        original_gray=original_gray,
        page_dimensions=tuple(omr_api.ENGINE.template.page_dimensions),
    )
    normalized_gray = normalization["normalizedGray"]

    binary_variants = dict(omr_api.build_section_binary_variants(normalized_gray))
    binary = binary_variants.get(args.variant)
    if binary is None:
        raise SystemExit(f"Binary variant not found: {args.variant}")

    section_bands = omr_api.detect_section_bands(binary)
    if section_bands is None:
        raise SystemExit("Could not detect section bands")

    requested_sections = omr_api.SECTION_PREFIXES if args.section == "all" else (args.section,)
    manifest = {
        "image": str(image_path),
        "normalization": normalization["method"],
        "binaryVariant": args.variant,
        "sections": {},
    }

    for prefix in requested_sections:
        section_rows = export_section_rows(
            normalized_gray=normalized_gray,
            binary=binary,
            section_bands=section_bands,
            prefix=prefix,
            out_dir=out_dir,
        )
        manifest["sections"][prefix] = section_rows

    if args.json_manifest:
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(manifest, indent=2))


def export_section_rows(*, normalized_gray, binary, section_bands, prefix, out_dir):
    actual_box = section_bands[prefix]
    template_box = omr_api.SECTION_TEMPLATE_BOXES[prefix]
    x_scale = (actual_box["right"] - actual_box["left"]) / max(template_box["right"] - template_box["left"], 1)
    y_scale = (actual_box["bottom"] - actual_box["top"]) / max(template_box["bottom"] - template_box["top"], 1)
    section_layouts = [item for item in omr_api.ACT_FIELD_LAYOUTS if item["prefix"] == prefix]

    section_title = omr_api.SECTION_TITLES.get(prefix, prefix)
    section_dir = out_dir / prefix
    section_dir.mkdir(parents=True, exist_ok=True)

    exported = []
    for layout in section_layouts:
        base_x = actual_box["left"] + ((layout["origin"][0] - template_box["left"]) * x_scale)
        base_y = actual_box["top"] + ((layout["origin"][1] - template_box["top"]) * y_scale)
        bubble_gap = layout["bubblesGap"] * x_scale
        row_gap = layout["labelsGap"] * y_scale
        bubble_width = omr_api.ACT_TEMPLATE_LAYOUT["bubbleDimensions"][0] * x_scale
        bubble_height = omr_api.ACT_TEMPLATE_LAYOUT["bubbleDimensions"][1] * y_scale

        left = int(round(base_x - (18 * x_scale)))
        right = int(round(base_x + ((len(omr_api.ANSWER_OPTIONS) - 1) * bubble_gap) + bubble_width + (18 * x_scale)))
        left = max(0, min(binary.shape[1] - 1, left))
        right = max(left + 1, min(binary.shape[1], right))

        for offset in range(layout["count"]):
            question_number = layout["start"] + offset
            question_label = f"{prefix}{question_number}"
            row_y = base_y + (offset * row_gap)
            top = int(round(row_y - (8 * y_scale)))
            bottom = int(round(row_y + bubble_height + (8 * y_scale)))
            top = max(0, min(binary.shape[0] - 1, top))
            bottom = max(top + 1, min(binary.shape[0], bottom))

            gray_crop = normalized_gray[top:bottom, left:right]
            binary_crop = binary[top:bottom, left:right]
            if gray_crop.size == 0 or binary_crop.size == 0:
                continue

            stacked = make_training_panel(gray_crop, binary_crop, question_label, section_title)
            filename = f"{question_label}.png"
            cv2.imwrite(str(section_dir / filename), stacked)
            exported.append(
                {
                    "label": question_label,
                    "file": str((section_dir / filename).resolve()),
                    "top": top,
                    "bottom": bottom,
                    "left": left,
                    "right": right,
                }
            )

    return exported


def make_training_panel(gray_crop, binary_crop, question_label, section_title):
    gray_bgr = cv2.cvtColor(gray_crop, cv2.COLOR_GRAY2BGR)
    binary_bgr = cv2.cvtColor(binary_crop, cv2.COLOR_GRAY2BGR)
    panel = cv2.hconcat([gray_bgr, binary_bgr])
    panel = cv2.copyMakeBorder(panel, 32, 8, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    cv2.putText(
        panel,
        f"{section_title} {question_label}",
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return panel


if __name__ == "__main__":
    main()
