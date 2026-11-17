"""Part codes and values in free text. No dependencies, so the tests need no store.

A repair question names its part by a code such as BR-R9270, and its answer is a value
such as 6-8 N·m or 2.5 mm. Both are checked word for word, never by meaning: a model that
reads BR-R9270 as BR-R9170, or 4-6 as 4-7, has given a wrong answer that looks sourced.
"""

import re
import unicodedata

# BR-R9270, ST-R8020, RD-M820, CS-R9100, SM-RT800, PD-GR500, CN-LG500, DM-RADBR01 ...
_MODEL = r"[A-Z]{0,3}\d{2,5}[A-Z]{0,3}"
# A code, then the models a manual lists after it without repeating the prefix:
# 'BR-R9100/R8000/R7000', 'ST-R7020 / R7025'. A bare model there starts with a letter or
# has three digits, so '/ 12-speed' and '/ 73 mm' are not read as models.
_BARE = r"(?:[A-Z]{1,3}\d{2,5}[A-Z]{0,3}|\d{3,5}[A-Z]{0,3})"
_CODE = re.compile(
    rf"\b([A-Z]{{2,3}})\s?-\s?({_MODEL})\b((?:\s?/\s?{_BARE}\b(?!\s?-\s?[A-Z0-9])(?!\s?MM))*)"
)
# Manual codes are not parts: a question about DM-TORQUE-04 asks about the chart.
_NOT_A_PART = {"DM", "SI", "UM", "EV"}

_DASHES = re.compile(r"[‐‑‒–—−]")
_RANGE = re.compile(r"(\d)\s*(?:n[·.⋅ ]?m|mm)?\s*(?:-|to)\s*(?=\d)")
# A number, or a range of numbers, with its unit when it has one.
_VALUE = re.compile(
    r"(?<![\w.])(\d+(?:[.,]\d+)?(?:-\d+(?:[.,]\d+)?)?)\s*"
    r"(n·m|nm|n\.m|mm|cm|kgf·cm|in\.?-?lbs?|lbf|°|%|ml|g|t)?(?![\w])"
)


def normalise(text: str) -> str:
    """Fold the ways of writing the same value: '9 – 11', '9 to 11 N·m' -> '9-11'.

    Lower case, one kind of dash, a range written without its first unit, a hyphen with
    no spaces (the PDFs often break 'ST- R8020'), and single spaces.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = _DASHES.sub("-", text)
    text = re.sub(r"\s*-\s*", "-", text)
    text = _RANGE.sub(r"\1-", text)
    return re.sub(r"\s+", " ", text).strip()


def part_codes(text: str) -> set[str]:
    """The part codes in `text`, normalised to 'BR-R9270'. Manual codes are left out.

    'BR-R9100/R8000' gives both BR-R9100 and BR-R8000.
    """
    found = set()
    for prefix, model, more in _CODE.findall(unicodedata.normalize("NFKC", text).upper()):
        if prefix in _NOT_A_PART:
            continue
        found.add(f"{prefix}-{model}")
        found.update(f"{prefix}-{bare}" for bare in re.findall(_BARE, more))
    return found


def values(text: str) -> set[str]:
    """The numeric values in `text`, normalised, without their units: {'6-8', '2.5'}.

    Units are dropped because the manuals often print the unit once, in a table heading,
    and the answer then names it beside every value. Single digits below 10 without a unit
    are left out: they are step numbers and list positions as often as they are values.
    """
    found = set()
    for number, unit in _VALUE.findall(normalise(text)):
        number = number.replace(",", ".")
        if not unit and "-" not in number and "." not in number and len(number) == 1:
            continue
        found.add(number)
    return found


def contains_value(text: str, value: str) -> bool:
    """True if `value` stands in the normalised `text` as a whole number or range.

    '1.6' does not match inside '11.6' or '1.65'. A range '4-6' is also found when the
    passage prints it '4 - 6' or '4 to 6' (normalise folds those). An end of a printed
    range is not a value: '3' is not found in '2.5 - 3 N·m', which says 2.5 to 3.
    """
    pattern = rf"(?<![\d.,-]){re.escape(value)}(?!\d|[.,]\d|-\d)"
    folded = normalise(text).replace(",", ".")
    return re.search(pattern, folded) is not None
