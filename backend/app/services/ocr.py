from __future__ import annotations

from dataclasses import dataclass
import re

import numpy as np

from .parsing import extract_label_fields, similarity, split_lines


class OCRUnavailableError(RuntimeError):
    """Raised when the local OCR toolchain is unavailable."""


@dataclass
class OCRResult:
    text: str
    average_confidence: float | None
    rotation_degrees: int = 0
    page_segmentation_mode: int = 6
    image_variant: str = "thresholded"


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

    return OCRResult(
        text="\n".join(lines),
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
