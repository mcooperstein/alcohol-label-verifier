from __future__ import annotations

from ..constants import CANONICAL_GOVERNMENT_WARNING, FIELD_LABELS
from ..models import ApplicationData, FieldReviewResult, LabelFields, ReviewStatus
from .parsing import (
    best_line_match,
    normalize_for_match,
    normalize_text,
    parse_alcohol_values,
    parse_volume,
    similarity,
    split_lines,
)


def build_summary(overall_status: ReviewStatus, field_results: list[FieldReviewResult]) -> str:
    failures = sum(result.status == ReviewStatus.FAIL for result in field_results)
    needs_review = sum(result.status == ReviewStatus.NEEDS_REVIEW for result in field_results)

    if overall_status == ReviewStatus.PASS:
        return "All reviewed label checks passed."
    if overall_status == ReviewStatus.NEEDS_REVIEW:
        return f"{needs_review} field(s) need review before a decision."
    return f"{failures} field(s) failed and {needs_review} field(s) need review."


def determine_overall_status(field_results: list[FieldReviewResult]) -> ReviewStatus:
    if any(result.status == ReviewStatus.FAIL for result in field_results):
        return ReviewStatus.FAIL
    if any(result.status == ReviewStatus.NEEDS_REVIEW for result in field_results):
        return ReviewStatus.NEEDS_REVIEW
    return ReviewStatus.PASS


def compare_text_field(
    *,
    field: str,
    expected_value: str | None,
    detected_value: str | None,
    raw_text: str,
    lines: list[str],
    allow_review_on_normalized_match: bool = False,
) -> FieldReviewResult:
    label = FIELD_LABELS[field]

    if not expected_value:
        return FieldReviewResult(
            field=field,
            label=label,
            status=ReviewStatus.PASS,
            reason="No expected value was provided for comparison.",
        )

    expected = normalize_text(expected_value)
    detected = normalize_text(detected_value or "")
    raw_normalized = normalize_text(raw_text)

    if expected in raw_normalized:
        return FieldReviewResult(
            field=field,
            label=label,
            expected_value=expected_value,
            detected_value=detected_value or expected_value,
            status=ReviewStatus.PASS,
            reason="The expected value appears directly in the extracted label text.",
        )

    if expected.casefold() in raw_normalized.casefold():
        return FieldReviewResult(
            field=field,
            label=label,
            expected_value=expected_value,
            detected_value=detected_value or expected_value,
            status=ReviewStatus.NEEDS_REVIEW if allow_review_on_normalized_match else ReviewStatus.PASS,
            reason=(
                "The value matches after case normalization, so a reviewer should confirm formatting."
                if allow_review_on_normalized_match
                else "The value matches after case normalization."
            ),
        )

    if normalize_for_match(expected) in normalize_for_match(raw_text):
        return FieldReviewResult(
            field=field,
            label=label,
            expected_value=expected_value,
            detected_value=detected_value or expected_value,
            status=ReviewStatus.NEEDS_REVIEW if allow_review_on_normalized_match else ReviewStatus.PASS,
            reason=(
                "The value matches after normalization, so a reviewer should confirm punctuation or casing."
                if allow_review_on_normalized_match
                else "The value matches after normalization."
            ),
        )

    best_line, best_score = best_line_match(lines, expected_value)
    if best_line and best_score >= 0.88:
        return FieldReviewResult(
            field=field,
            label=label,
            expected_value=expected_value,
            detected_value=best_line,
            status=ReviewStatus.NEEDS_REVIEW,
            reason="A close OCR match was found, but the value is not exact enough to auto-pass.",
        )

    return FieldReviewResult(
        field=field,
        label=label,
        expected_value=expected_value,
        detected_value=detected_value or best_line,
        status=ReviewStatus.FAIL,
        reason="The expected value could not be matched in the extracted label text.",
    )


def compare_alcohol_content(expected_value: str | None, detected_value: str | None) -> FieldReviewResult:
    expected = parse_alcohol_values(expected_value)
    detected = parse_alcohol_values(detected_value)

    if not expected_value:
        return FieldReviewResult(
            field="alcohol_content",
            label=FIELD_LABELS["alcohol_content"],
            status=ReviewStatus.PASS,
            reason="No expected alcohol content was provided for comparison.",
        )

    if detected["abv"] is None and detected["proof"] is None:
        return FieldReviewResult(
            field="alcohol_content",
            label=FIELD_LABELS["alcohol_content"],
            expected_value=expected_value,
            detected_value=detected_value,
            status=ReviewStatus.FAIL,
            reason="No alcohol content was detected on the label.",
        )

    abv_matches = expected["abv"] == detected["abv"] if expected["abv"] is not None else True
    proof_matches = expected["proof"] == detected["proof"] if expected["proof"] is not None else True

    if abv_matches and proof_matches:
        return FieldReviewResult(
            field="alcohol_content",
            label=FIELD_LABELS["alcohol_content"],
            expected_value=expected_value,
            detected_value=detected_value,
            status=ReviewStatus.PASS,
            reason="Detected alcohol content matches the expected numeric values.",
        )

    if abv_matches or proof_matches:
        return FieldReviewResult(
            field="alcohol_content",
            label=FIELD_LABELS["alcohol_content"],
            expected_value=expected_value,
            detected_value=detected_value,
            status=ReviewStatus.NEEDS_REVIEW,
            reason="Only part of the alcohol statement matched. Review the label manually.",
        )

    return FieldReviewResult(
        field="alcohol_content",
        label=FIELD_LABELS["alcohol_content"],
        expected_value=expected_value,
        detected_value=detected_value,
        status=ReviewStatus.FAIL,
        reason="Detected alcohol content does not match the expected ABV or proof.",
    )


def compare_net_contents(expected_value: str | None, detected_value: str | None) -> FieldReviewResult:
    expected = parse_volume(expected_value)
    detected = parse_volume(detected_value)

    if not expected_value:
        return FieldReviewResult(
            field="net_contents",
            label=FIELD_LABELS["net_contents"],
            status=ReviewStatus.PASS,
            reason="No expected net contents value was provided for comparison.",
        )

    if detected["value"] is None:
        return FieldReviewResult(
            field="net_contents",
            label=FIELD_LABELS["net_contents"],
            expected_value=expected_value,
            detected_value=detected_value,
            status=ReviewStatus.FAIL,
            reason="No net contents statement was detected on the label.",
        )

    if expected == detected:
        return FieldReviewResult(
            field="net_contents",
            label=FIELD_LABELS["net_contents"],
            expected_value=expected_value,
            detected_value=detected_value,
            status=ReviewStatus.PASS,
            reason="Detected net contents match the expected value.",
        )

    if expected["value"] == detected["value"]:
        return FieldReviewResult(
            field="net_contents",
            label=FIELD_LABELS["net_contents"],
            expected_value=expected_value,
            detected_value=detected_value,
            status=ReviewStatus.NEEDS_REVIEW,
            reason="The numeric volume matches, but the unit formatting should be reviewed.",
        )

    return FieldReviewResult(
        field="net_contents",
        label=FIELD_LABELS["net_contents"],
        expected_value=expected_value,
        detected_value=detected_value,
        status=ReviewStatus.FAIL,
        reason="Detected net contents do not match the expected value.",
    )


def compare_country_of_origin(application: ApplicationData, raw_text: str, extracted_fields: LabelFields) -> FieldReviewResult:
    if not application.imported:
        return FieldReviewResult(
            field="country_of_origin",
            label=FIELD_LABELS["country_of_origin"],
            status=ReviewStatus.PASS,
            reason="Country of origin is not required because the product is not marked as imported.",
        )

    if not application.country_of_origin:
        return FieldReviewResult(
            field="country_of_origin",
            label=FIELD_LABELS["country_of_origin"],
            status=ReviewStatus.FAIL,
            reason="Imported products require an expected country of origin value.",
        )

    return compare_text_field(
        field="country_of_origin",
        expected_value=application.country_of_origin,
        detected_value=extracted_fields.country_of_origin,
        raw_text=raw_text,
        lines=split_lines(raw_text),
    )


def compare_government_warning(raw_text: str, detected_value: str | None) -> FieldReviewResult:
    canonical_normalized = normalize_for_match(CANONICAL_GOVERNMENT_WARNING)
    raw_normalized = normalize_for_match(raw_text)

    if canonical_normalized in raw_normalized:
        return FieldReviewResult(
            field="government_warning",
            label=FIELD_LABELS["government_warning"],
            expected_value=CANONICAL_GOVERNMENT_WARNING,
            detected_value=detected_value or CANONICAL_GOVERNMENT_WARNING,
            status=ReviewStatus.PASS,
            reason="The standard government warning text was found in the extracted label text.",
        )

    if detected_value:
        warning_similarity = similarity(detected_value, CANONICAL_GOVERNMENT_WARNING)
        if warning_similarity >= 0.9:
            return FieldReviewResult(
                field="government_warning",
                label=FIELD_LABELS["government_warning"],
                expected_value=CANONICAL_GOVERNMENT_WARNING,
                detected_value=detected_value,
                status=ReviewStatus.NEEDS_REVIEW,
                reason="A close warning statement was found, but the wording may not be exact.",
            )

    if "government warning" in raw_normalized:
        return FieldReviewResult(
            field="government_warning",
            label=FIELD_LABELS["government_warning"],
            expected_value=CANONICAL_GOVERNMENT_WARNING,
            detected_value=detected_value,
            status=ReviewStatus.NEEDS_REVIEW,
            reason="A warning statement was detected, but the full required text could not be confirmed.",
        )

    return FieldReviewResult(
        field="government_warning",
        label=FIELD_LABELS["government_warning"],
        expected_value=CANONICAL_GOVERNMENT_WARNING,
        detected_value=detected_value,
        status=ReviewStatus.FAIL,
        reason="The standard government warning could not be confirmed on the label.",
    )


def validate_label(
    *,
    application: ApplicationData,
    raw_text: str,
    extracted_fields: LabelFields,
    average_confidence: float | None,
) -> tuple[ReviewStatus, list[FieldReviewResult], list[str], str]:
    lines = split_lines(raw_text)
    warnings: list[str] = []

    if average_confidence is not None and average_confidence < 65:
        warnings.append(
            "OCR confidence was lower than expected. Borderline matches should be reviewed carefully."
        )

    field_results = [
        compare_text_field(
            field="brand_name",
            expected_value=application.brand_name,
            detected_value=extracted_fields.brand_name,
            raw_text=raw_text,
            lines=lines,
            allow_review_on_normalized_match=True,
        ),
        compare_text_field(
            field="class_type",
            expected_value=application.class_type,
            detected_value=extracted_fields.class_type,
            raw_text=raw_text,
            lines=lines,
        ),
        compare_alcohol_content(application.alcohol_content, extracted_fields.alcohol_content or raw_text),
        compare_net_contents(application.net_contents, extracted_fields.net_contents or raw_text),
        compare_text_field(
            field="bottler",
            expected_value=application.bottler,
            detected_value=extracted_fields.bottler,
            raw_text=raw_text,
            lines=lines,
        ),
        compare_country_of_origin(application, raw_text, extracted_fields),
        compare_government_warning(raw_text, extracted_fields.government_warning),
    ]

    overall_status = determine_overall_status(field_results)
    summary = build_summary(overall_status, field_results)
    return overall_status, field_results, warnings, summary
