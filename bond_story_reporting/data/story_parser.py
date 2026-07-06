from __future__ import annotations

import re
from typing import Any

_TOKEN_SPLIT_RE = re.compile(r"[\s,|/_]+")
_YEAR_RE = re.compile(r"^(19\d{2}|20\d{2})$")
_NUMERIC_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?%?$")
_BALANCE_BUCKET_RE = re.compile(
    r"(?<![A-Z0-9])(?:LB\d{2,6}[A-Z]*|LIB\d{2,6}[A-Z]*|[<>]=?\$?\d+(?:\.\d+)?[KMB]?)(?![A-Z0-9])",
    flags=re.IGNORECASE,
)

_PROGRAM_HINTS = {
    "FNCL",
    "FHLMC",
    "FHCI",
    "FHCL",
    "FHLG",
    "FNC",
    "FNCI",
    "GNMA",
    "GNCI",
    "GNSF",
    "UMBS",
    "UMBI",
    "FNM",
    "FRE",
    "GN",
    "G2",
    "G1",
    "GOVT",
    "USDA",
    "JUMBO",
    "NONQM",
}

_FAMILY_HINTS = {
    "FNCL",
    "FHLMC",
    "FHCI",
    "FHCL",
    "FHLG",
    "FNC",
    "FNCI",
    "GNMA",
    "GNCI",
    "GNSF",
    "UMBS",
    "UMBI",
    "TEXAS",
    "GOVT",
    "NONQM",
}

_GEOGRAPHY_CODES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "DC",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "PR",
    "VI",
    "NATL",
    "NATIONAL",
}


def _clean_token(token: str) -> str:
    return token.strip().strip("()[]{}").replace("%", "")


def tokenize_story_label(raw_story_name: Any) -> list[str]:
    """Split a story label into stable tokens.

    The parser intentionally keeps behavior permissive to avoid dropping data for
    malformed labels. Empty tokens are removed.
    """

    text = str(raw_story_name or "").strip()
    if not text:
        return []
    return [tok for tok in _TOKEN_SPLIT_RE.split(text) if tok]


def _extract_year(tokens: list[str]) -> int | None:
    for token in tokens:
        cleaned = _clean_token(token).upper()
        if _YEAR_RE.match(cleaned):
            year = int(cleaned)
            if 1900 <= year <= 2099:
                return year
    return None


def _extract_coupon(tokens: list[str]) -> float | None:
    for token in tokens:
        cleaned = _clean_token(token)
        if not cleaned:
            continue
        if not _NUMERIC_TOKEN_RE.match(token.strip()):
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue
        # Coupon domain guard: allow broad historical range, reject obvious years.
        if 0.125 <= value <= 15.0:
            return value
    return None


def _extract_program(tokens: list[str]) -> str | None:
    upper_tokens = [_clean_token(tok).upper() for tok in tokens if tok]
    for token in upper_tokens:
        if token in _PROGRAM_HINTS:
            return token
    for token in upper_tokens:
        if token.isalpha() and 2 <= len(token) <= 8:
            return token
    return None


def _extract_geography(tokens: list[str]) -> str | None:
    for token in tokens:
        cleaned = _clean_token(token).upper()
        if cleaned in _GEOGRAPHY_CODES:
            return cleaned
    return None


def _extract_balance_bucket(text: str) -> str | None:
    match = _BALANCE_BUCKET_RE.search(text.upper())
    if match:
        return match.group(0)
    return None


def _extract_story_family(tokens: list[str], program: str | None) -> str | None:
    upper_tokens = [_clean_token(tok).upper() for tok in tokens if tok]
    for token in upper_tokens:
        if token in _FAMILY_HINTS:
            return token
    if program:
        return program
    for token in upper_tokens:
        if token.isalpha() and len(token) >= 3:
            return token
    return None


def parse_story_label(raw_story_name: Any) -> dict[str, Any]:
    """Parse a bond/MBS story label into normalized fields.

    The parser is designed for resilience:
    - missing pieces are allowed
    - parse errors never raise exceptions
    - output always contains the same keys
    """

    text = str(raw_story_name or "").strip()
    tokens = tokenize_story_label(text)

    if not tokens:
        return {
            "program": None,
            "coupon": None,
            "origination_year": None,
            "geography": None,
            "loan_balance_bucket": None,
            "story_family": None,
            "story_tag": None,
            "parse_success": False,
            "parse_error": "empty_story_name",
        }

    year = _extract_year(tokens)
    coupon = _extract_coupon(tokens)
    program = _extract_program(tokens)
    geography = _extract_geography(tokens)
    loan_balance_bucket = _extract_balance_bucket(text)
    story_family = _extract_story_family(tokens, program=program)

    consumed: set[str] = set()
    if program:
        consumed.add(program.upper())
    if geography:
        consumed.add(geography.upper())
    if story_family:
        consumed.add(story_family.upper())
    if loan_balance_bucket:
        consumed.add(loan_balance_bucket.upper())
    if year is not None:
        consumed.add(str(year))
    if coupon is not None:
        consumed.add(str(coupon))
        if float(coupon).is_integer():
            consumed.add(str(int(coupon)))

    tag_tokens: list[str] = []
    for token in tokens:
        raw = token.strip()
        cleaned_upper = _clean_token(raw).upper()
        if not cleaned_upper:
            continue
        if cleaned_upper in consumed:
            continue
        if _YEAR_RE.match(cleaned_upper):
            continue
        if _NUMERIC_TOKEN_RE.match(raw):
            continue
        tag_tokens.append(raw)

    story_tag = " ".join(tag_tokens[:6]) if tag_tokens else None
    parse_success = any(
        [
            program is not None,
            coupon is not None,
            year is not None,
            geography is not None,
            loan_balance_bucket is not None,
            story_family is not None,
        ]
    )

    return {
        "program": program,
        "coupon": coupon,
        "origination_year": year,
        "geography": geography,
        "loan_balance_bucket": loan_balance_bucket,
        "story_family": story_family,
        "story_tag": story_tag,
        "parse_success": parse_success,
        "parse_error": None if parse_success else "insufficient_story_tokens",
    }
