from app.services.ocr import recover_expected_text, sanitize_ocr_text


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


def test_recover_expected_text_uses_expected_values_for_strong_fragment_match() -> None:
    raw_text = "\n".join(
        [
            "BIGE UBLE IPA!",
            "got Se",
        ]
    )

    assert recover_expected_text(
        raw_text,
        ["Big Tree", "Double IPA", "Big Tree Double IPA"],
    ) == "Big Tree Double IPA"


def test_recover_expected_text_includes_multiple_recovered_lines() -> None:
    raw_text = "\n".join(
        [
            "atOMIC q UC",
            "Hazy Boule iol",
            "aic. 8% BY",
        ]
    )

    assert recover_expected_text(
        raw_text,
        ["Atomic Duck", "Hazy Double I.P.A.", "8% By Vol."],
    ) == "\n".join(
        [
            "Atomic Duck",
            "Hazy Double I.P.A.",
            "8% By Vol.",
        ]
    )
