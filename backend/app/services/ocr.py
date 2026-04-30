from __future__ import annotations

from dataclasses import dataclass


class OCRUnavailableError(RuntimeError):
    """Raised when the local OCR toolchain is unavailable."""


@dataclass
class OCRResult:
    text: str
    average_confidence: float | None


def extract_text(image) -> OCRResult:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:  # pragma: no cover - dependency failure path
        raise OCRUnavailableError("pytesseract is not installed.") from exc

    try:
        ocr_data = pytesseract.image_to_data(image, output_type=Output.DICT, config="--oem 3 --psm 6")
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError(
            "Tesseract OCR is not installed or is not available on the system PATH."
        ) from exc

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

    average_confidence = (
        round(sum(confidences) / len(confidences), 2) if confidences else None
    )

    return OCRResult(text="\n".join(lines), average_confidence=average_confidence)
