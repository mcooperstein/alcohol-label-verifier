from app.services.ocr import recover_likely_title, sanitize_ocr_text


def test_sanitize_ocr_text_removes_low_signal_noise_and_merges_title_fragments() -> None:
    raw_text = "\n".join(
        [
            "_-",
            "a aa",
            "! ax}",
            "BIGE",
            "0",
            "UBLE IPA!",
            "x",
            "got Se.",
        ]
    )

    assert sanitize_ocr_text(raw_text) == "\n".join(
        [
            "BIGE UBLE IPA!",
            "got Se",
        ]
    )


def test_sanitize_ocr_text_keeps_numeric_compliance_lines() -> None:
    raw_text = "\n".join(
        [
            "750 mL",
            "45% Alc./Vol. (90 Proof)",
            "*",
        ]
    )

    assert sanitize_ocr_text(raw_text) == "\n".join(
        [
            "750 mL",
            "45% Alc./Vol. (90 Proof)",
        ]
    )


def test_recover_likely_title_uses_expected_text_for_strong_fragment_match() -> None:
    raw_text = "\n".join(
        [
            "BIGE UBLE IPA!",
            "got Se",
        ]
    )

    assert recover_likely_title(
        raw_text,
        ["Big Tree", "Double IPA", "Big Tree Double IPA"],
    ) == "Big Tree Double IPA"
