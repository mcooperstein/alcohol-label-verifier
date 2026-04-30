from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..constants import BOTTLER_PREFIXES, CANONICAL_GOVERNMENT_WARNING, CLASS_TYPE_KEYWORDS, COUNTRY_PREFIXES
from ..models import LabelFields

SMART_QUOTES_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
    }
)

NON_ALPHANUMERIC_RE = re.compile(r"[^a-z0-9]+")
VOLUME_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ml|mL|l|L|cl|fl\.?\s?oz|oz)\b")
ABV_RE = re.compile(r"(?P<value>\d{1,3}(?:\.\d+)?)\s*%\s*(?:alc(?:ohol)?(?:\.|/vol\.?)?)?", re.IGNORECASE)
PROOF_RE = re.compile(r"(?P<value>\d{1,3}(?:\.\d+)?)\s*proof", re.IGNORECASE)


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value: str) -> str:
    translated = value.translate(SMART_QUOTES_TRANSLATION)
    return collapse_whitespace(translated)


def normalize_for_match(value: str) -> str:
    lowered = normalize_text(value).lower()
    lowered = lowered.replace("&", " and ")
    return collapse_whitespace(NON_ALPHANUMERIC_RE.sub(" ", lowered))


def split_lines(raw_text: str) -> list[str]:
    return [normalize_text(line) for line in raw_text.splitlines() if normalize_text(line)]


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_for_match(left), normalize_for_match(right)).ratio()


def best_line_match(lines: list[str], expected: str) -> tuple[str | None, float]:
    best_line: str | None = None
    best_score = 0.0

    for line in lines:
        score = similarity(line, expected)
        if score > best_score:
            best_line = line
            best_score = score

    return best_line, best_score


def parse_alcohol_values(value: str | None) -> dict[str, float | None]:
    if not value:
        return {"abv": None, "proof": None}

    normalized = normalize_text(value)
    abv_match = ABV_RE.search(normalized)
    proof_match = PROOF_RE.search(normalized)

    return {
        "abv": float(abv_match.group("value")) if abv_match else None,
        "proof": float(proof_match.group("value")) if proof_match else None,
    }


def parse_volume(value: str | None) -> dict[str, str | float | None]:
    if not value:
        return {"value": None, "unit": None}

    match = VOLUME_RE.search(normalize_text(value))
    if not match:
        return {"value": None, "unit": None}

    unit = normalize_for_match(match.group("unit")).replace(" ", "")
    return {"value": float(match.group("value")), "unit": unit}


def capture_government_warning(raw_text: str) -> str | None:
    normalized = normalize_text(raw_text)
    warning_match = re.search(
        r"(government warning:.*?health problems\.)",
        normalized,
        flags=re.IGNORECASE,
    )
    if warning_match:
        return warning_match.group(1)

    start_match = re.search(r"(government warning:.*)", normalized, flags=re.IGNORECASE)
    if start_match:
        return start_match.group(1)

    return None


def extract_label_fields(raw_text: str) -> LabelFields:
    lines = split_lines(raw_text)

    brand_name = None
    for line in lines[:8]:
        line_match = normalize_for_match(line)
        if not line_match:
            continue
        if any(prefix in line_match for prefix in BOTTLER_PREFIXES):
            continue
        if "government warning" in line_match:
            continue
        if VOLUME_RE.search(line):
            continue
        if ABV_RE.search(line) or PROOF_RE.search(line):
            continue
        brand_name = line
        break

    class_type = next(
        (
            line
            for line in lines
            if any(keyword in normalize_for_match(line) for keyword in CLASS_TYPE_KEYWORDS)
        ),
        None,
    )

    alcohol_content = next(
        (line for line in lines if ABV_RE.search(line) or PROOF_RE.search(line)),
        None,
    )
    net_contents = next((line for line in lines if VOLUME_RE.search(line)), None)
    bottler = next(
        (
            line
            for line in lines
            if any(prefix in normalize_for_match(line) for prefix in BOTTLER_PREFIXES)
        ),
        None,
    )

    country_of_origin = next(
        (
            line
            for line in lines
            if any(prefix in normalize_for_match(line) for prefix in COUNTRY_PREFIXES)
        ),
        None,
    )

    government_warning = capture_government_warning(raw_text)
    if government_warning is None and normalize_for_match(CANONICAL_GOVERNMENT_WARNING) in normalize_for_match(raw_text):
        government_warning = CANONICAL_GOVERNMENT_WARNING

    return LabelFields(
        brand_name=brand_name,
        class_type=class_type,
        alcohol_content=alcohol_content,
        net_contents=net_contents,
        bottler=bottler,
        country_of_origin=country_of_origin,
        government_warning=government_warning,
    )
