"""
NFIRS incident-type code lookup.

Loads reference/nfirs_incident_types.csv (published NFIRS 5.0 codeset, public domain)
so analyses can auto-label the `actual_incident_type` field from the First Due feed
instead of hand-mapping codes.

    from reference.nfirs import label, category
    label("321")      -> "EMS call, excluding vehicle accident with injury"
    category("321")   -> "Rescue / EMS"
"""
import csv
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSV = os.path.join(_HERE, "nfirs_incident_types.csv")

# First-digit series -> NFIRS category name
SERIES = {
    "1": "Fire",
    "2": "Overpressure / explosion (no fire)",
    "3": "Rescue / EMS",
    "4": "Hazardous condition",
    "5": "Service call",
    "6": "Good intent",
    "7": "False alarm / false call",
    "8": "Severe weather / natural disaster",
    "9": "Special incident",
}

with open(_CSV, newline="", encoding="utf-8") as _f:
    CODES = {row["code"]: row["description"] for row in csv.DictReader(_f)}


def label(code) -> str:
    """Description for an NFIRS code. Falls back to the series header (e.g. 321 -> 300)
    then to 'Unknown (<code>)'."""
    code = str(code or "").strip()
    if code in CODES:
        return CODES[code]
    if len(code) == 3 and (code[0] + "00") in CODES:
        return CODES[code[0] + "00"]
    return f"Unknown ({code})"


def category(code) -> str:
    """NFIRS series category for a code, e.g. 321 -> 'Rescue / EMS'."""
    code = str(code or "").strip()
    return SERIES.get(code[:1], "Unknown")


if __name__ == "__main__":
    for c in ("111", "321", "322", "412", "553", "600", "745", "999"):
        print(f"{c}  [{category(c)}]  {label(c)}")
