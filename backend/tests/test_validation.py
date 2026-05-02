from app.constants import CANONICAL_GOVERNMENT_WARNING
from app.models import ApplicationData, LabelFields, ReviewStatus
from app.services.validation import validate_label


def test_brand_name_normalization_routes_to_review_not_fail() -> None:
    application = ApplicationData(
        brand_name="Stone's Throw",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        bottler="Bottled by Old Tom Distillery, Louisville, KY",
        imported=False,
    )
    raw_text = "\n".join(
        [
            "STONE'S THROW",
            "Kentucky Straight Bourbon Whiskey",
            "45% Alc./Vol. (90 Proof)",
            "750 mL",
            "Bottled by Old Tom Distillery, Louisville, KY",
            CANONICAL_GOVERNMENT_WARNING,
        ]
    )
    extracted_fields = LabelFields(
        brand_name="STONE'S THROW",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        bottler="Bottled by Old Tom Distillery, Louisville, KY",
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )

    overall_status, field_results, warnings, _ = validate_label(
        application=application,
        raw_text=raw_text,
        extracted_fields=extracted_fields,
        average_confidence=72.4,
    )

    brand_result = next(result for result in field_results if result.field == "brand_name")

    assert overall_status == ReviewStatus.NEEDS_REVIEW
    assert brand_result.status == ReviewStatus.NEEDS_REVIEW
    assert warnings == []


def test_alcohol_mismatch_fails_review() -> None:
    application = ApplicationData(
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        imported=False,
    )
    raw_text = "\n".join(
        [
            "OLD TOM DISTILLERY",
            "40% Alc./Vol. (80 Proof)",
            CANONICAL_GOVERNMENT_WARNING,
        ]
    )
    extracted_fields = LabelFields(
        brand_name="OLD TOM DISTILLERY",
        alcohol_content="40% Alc./Vol. (80 Proof)",
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )

    overall_status, field_results, _, _ = validate_label(
        application=application,
        raw_text=raw_text,
        extracted_fields=extracted_fields,
        average_confidence=70.0,
    )

    alcohol_result = next(result for result in field_results if result.field == "alcohol_content")

    assert overall_status == ReviewStatus.FAIL
    assert alcohol_result.status == ReviewStatus.FAIL


def test_summary_lists_failed_and_review_fields() -> None:
    application = ApplicationData(
        brand_name="Isla Dorada",
        class_type="Dark Rum",
        alcohol_content="40% Alc./Vol. (80 Proof)",
        net_contents="700 mL",
        bottler="Imported by Atlantic Beverage Co., New York, NY",
        country_of_origin="Jamaica",
        imported=True,
    )
    raw_text = "\n".join(
        [
            "ISLA DORADA",
            "Dark Rum",
            "40% Alc./Vol. (80 Proof)",
            "700 mL",
            "Imported by Atlantic Beverage Co., New York, NY",
            "Product of Dominican Republic",
            CANONICAL_GOVERNMENT_WARNING,
        ]
    )
    extracted_fields = LabelFields(
        brand_name="ISLA DORADA",
        class_type="Dark Rum",
        alcohol_content="40% Alc./Vol. (80 Proof)",
        net_contents="700 mL",
        bottler="Imported by Atlantic Beverage Co., New York, NY",
        country_of_origin="Product of Dominican Republic",
        government_warning=CANONICAL_GOVERNMENT_WARNING,
    )

    overall_status, field_results, _, summary = validate_label(
        application=application,
        raw_text=raw_text,
        extracted_fields=extracted_fields,
        average_confidence=95.0,
    )

    assert overall_status == ReviewStatus.FAIL
    assert any(result.status == ReviewStatus.NEEDS_REVIEW for result in field_results)
    assert "Failed: Country of origin." in summary
    assert "Needs review: Brand name." in summary
