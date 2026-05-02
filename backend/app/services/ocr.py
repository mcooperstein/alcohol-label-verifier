from __future__ import annotations

from dataclasses import dataclass
import re

import numpy as np

from .parsing import extract_label_fields, normalize_for_match, similarity, split_lines


class OCRUnavailableError(RuntimeError):
    """Raised when the local OCR toolchain is unavailable."""


@dataclass
class OCRResult:
    text: str
    average_confidence: float | None
    rotation_degrees: int = 0
    page_segmentation_mode: int = 6
    image_variant: str = "thresholded"


def normalize_ocr_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip(" _-|~`'\":;,.")


def is_meaningful_ocr_line(line: str) -> bool:
    normalized = normalize_ocr_line(line)
    if not normalized:
        return False

    alnum_count = sum(character.isalnum() for character in normalized)
    alpha_count = sum(character.isalpha() for character in normalized)
    digit_count = sum(character.isdigit() for character in normalized)
    signal_tokens = [
        re.sub(r"[^A-Za-z0-9%./-]", "", token)
        for token in normalized.split()
    ]
    significant_tokens = [token for token in signal_tokens if len(token) >= 4]

    if alnum_count == 0:
        return False

    return (
        digit_count >= 2
        or alpha_count >= 4
        or bool(significant_tokens)
    ) and alnum_count / len(normalized) >= 0.35


def is_uppercase_fragment(line: str) -> bool:
    alpha_characters = [character for character in line if character.isalpha()]
    if len(alpha_characters) < 3:
        return False

    uppercase_ratio = sum(character.isupper() for character in alpha_characters) / len(alpha_characters)
    compact_alpha = "".join(alpha_characters)
    return uppercase_ratio >= 0.7 and len(compact_alpha) <= 14


def should_merge_ocr_lines(previous_line: str, current_line: str) -> bool:
    if any(character.isdigit() for character in previous_line + current_line):
        return False

    previous_alpha = "".join(character for character in previous_line if character.isalpha())
    current_alpha = "".join(character for character in current_line if character.isalpha())
    if not previous_alpha or not current_alpha:
        return False

    return (
        is_uppercase_fragment(previous_line)
        and is_uppercase_fragment(current_line)
        and len(previous_alpha) <= 8
        and len(current_alpha) <= 12
    )


def sanitize_ocr_text(raw_text: str) -> str:
    cleaned_lines: list[str] = []

    for line in raw_text.splitlines():
        normalized = normalize_ocr_line(line)
        if not is_meaningful_ocr_line(normalized):
            continue

        if cleaned_lines and should_merge_ocr_lines(cleaned_lines[-1], normalized):
            cleaned_lines[-1] = f"{cleaned_lines[-1]} {normalized}"
            continue

        if cleaned_lines and normalize_for_match(cleaned_lines[-1]) == normalize_for_match(normalized):
            continue

        cleaned_lines.append(normalized)

    return "\n".join(cleaned_lines)


def rotate_image(image: np.ndarray, rotation_degrees: int) -> np.ndarray:
    if rotation_degrees == 0:
        return image
    if rotation_degrees == 90:
        return np.rot90(image, k=3).copy()
    if rotation_degrees == 180:
        return np.rot90(image, k=2).copy()
    if rotation_degrees == 270:
        return np.rot90(image, k=1).copy()
    raise ValueError(f"Unsupported rotation: {rotation_degrees}")


def candidate_score(
    text: str,
    average_confidence: float | None,
    expected_texts: list[str] | None = None,
) -> float:
    field_count = sum(value is not None for value in extract_label_fields(text).model_dump().values())
    expected_bonus, strong_match_count, _ = expected_match_metrics(text, expected_texts)
    return (
        (average_confidence or 0.0) * 2.0
        + field_count * 18
        + expected_bonus * 140
        + strong_match_count * 120
    )


def expected_match_metrics(
    text: str,
    expected_texts: list[str] | None,
) -> tuple[float, int, float]:
    lines = split_lines(text)
    expected_bonus = 0.0
    strong_match_count = 0
    max_similarity = 0.0

    for expected_text in expected_texts or []:
        normalized = expected_text.strip()
        if not normalized:
            continue
        best_similarity = max((similarity(line, normalized) for line in lines), default=0.0)
        expected_bonus += best_similarity
        max_similarity = max(max_similarity, best_similarity)
        if best_similarity >= 0.55:
            strong_match_count += 1

    return expected_bonus, strong_match_count, max_similarity


def extract_text_once(
    image,
    *,
    rotation_degrees: int,
    page_segmentation_mode: int,
    image_variant: str,
) -> OCRResult:
    import pytesseract
    from pytesseract import Output

    rotated_image = rotate_image(image, rotation_degrees)
    ocr_data = pytesseract.image_to_data(
        rotated_image,
        output_type=Output.DICT,
        config=f"--oem 3 --psm {page_segmentation_mode}",
    )

    lines: list[str] = []
    current_line_tokens: list[str] = []
    current_key: tuple[int, int, int, int] | None = None
    confidences: list[float] = []

    for index, token in enumerate(ocr_data["text"]):
        text = token.strip()
        if not text:
            continue

        line_key = (
            int(ocr_data["page_num"][index]),
            int(ocr_data["block_num"][index]),
            int(ocr_data["par_num"][index]),
            int(ocr_data["line_num"][index]),
        )

        if current_key is None:
            current_key = line_key

        if line_key != current_key:
            if current_line_tokens:
                lines.append(" ".join(current_line_tokens))
            current_line_tokens = []
            current_key = line_key

        current_line_tokens.append(text)

        confidence = float(ocr_data["conf"][index])
        if confidence >= 0:
            confidences.append(confidence)

    if current_line_tokens:
        lines.append(" ".join(current_line_tokens))

    average_confidence = round(sum(confidences) / len(confidences), 2) if confidences else None

    raw_text = "\n".join(lines)
    sanitized_text = sanitize_ocr_text(raw_text)

    return OCRResult(
        text=sanitized_text or raw_text,
        average_confidence=average_confidence,
        rotation_degrees=rotation_degrees,
        page_segmentation_mode=page_segmentation_mode,
        image_variant=image_variant,
    )


def extract_text(
    image,
    alternate_images: list[tuple[str, np.ndarray]] | None = None,
    expected_texts: list[str] | None = None,
) -> OCRResult:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:  # pragma: no cover - dependency failure path
        raise OCRUnavailableError("pytesseract is not installed.") from exc

    try:
        initial_result = extract_text_once(
            image,
            rotation_degrees=0,
            page_segmentation_mode=6,
            image_variant="thresholded",
        )
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError(
            "Tesseract OCR is not installed or is not available on the system PATH."
        ) from exc

    candidates = [initial_result]
    initial_score = candidate_score(
        initial_result.text,
        initial_result.average_confidence,
        expected_texts=expected_texts,
    )
    _, initial_strong_match_count, initial_max_similarity = expected_match_metrics(
        initial_result.text,
        expected_texts,
    )
    should_try_rotations = (
        image.shape[1] > image.shape[0]
        or initial_score < 170
        or initial_strong_match_count == 0
        or initial_max_similarity < 0.7
    )

    if should_try_rotations:
        image_variants = {"thresholded": image, **dict(alternate_images or [])}
        prioritized_specs: list[tuple[str, int, int]] = [
            ("thresholded", 0, 11),
            ("boosted grayscale", 0, 11),
            ("boosted grayscale", 0, 6),
        ]

        if image.shape[1] > image.shape[0]:
            prioritized_specs = [
                ("thresholded", 90, 11),
                ("thresholded", 270, 11),
                ("boosted grayscale", 90, 11),
                ("boosted grayscale", 270, 11),
                *prioritized_specs,
            ]

        seen_specs = {("thresholded", 0, 6)}
        for image_variant, rotation_degrees, page_segmentation_mode in prioritized_specs:
            if (image_variant, rotation_degrees, page_segmentation_mode) in seen_specs:
                continue
            candidate_image = image_variants.get(image_variant)
            if candidate_image is None:
                continue
            seen_specs.add((image_variant, rotation_degrees, page_segmentation_mode))
            candidates.append(
                extract_text_once(
                    candidate_image,
                    rotation_degrees=rotation_degrees,
                    page_segmentation_mode=page_segmentation_mode,
                    image_variant=image_variant,
                )
            )

    return max(
        candidates,
        key=lambda candidate: candidate_score(
            candidate.text,
            candidate.average_confidence,
            expected_texts=expected_texts,
        ),
    )
