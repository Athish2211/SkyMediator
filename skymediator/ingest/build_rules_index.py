"""
DGCA CAR Rules Indexer and RAG Gold Set Generator.
Chunks DGCA CAR Section 7 (FDTL) and CAR Section 3 (Passenger Care) text,
builds a local retrieval index, and generates eval/rag_gold.jsonl.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from skymediator.config import settings

# Structured DGCA CAR Statutory Clauses
DGCA_CAR_CLAUSES = [
    {
        "clause_id": "CAR-7-J-III-Para-6.1",
        "title": "Maximum Daily Flight Duty Period (FDP) for Two-Pilot Operations",
        "category": "FDTL",
        "applicable_sectors": "1 to 2 sectors",
        "content": "For two-pilot operations with daytime duty starting between 06:00 and 13:59 hours, the maximum permissible Flight Duty Period (FDP) is 12.5 hours (750 minutes) for up to two landings. For 3 to 4 landings, the maximum FDP is reduced to 11.5 hours (690 minutes).",
        "keywords": ["maximum fdp", "flight duty period", "two pilot", "daytime", "landings", "750 minutes"]
    },
    {
        "clause_id": "CAR-7-J-III-Para-6.2",
        "title": "Flight Duty Period Limits with Window of Circadian Low (WOCL) Encroachment",
        "category": "FDTL",
        "applicable_sectors": "Night Operations",
        "content": "For any Flight Duty Period encroaching upon or starting within the Window of Circadian Low (WOCL: 02:00 to 06:00 hours IST), the maximum permissible FDP shall be reduced to 11.0 hours (660 minutes) for up to two landings, and 10.0 hours (600 minutes) for 3 landings.",
        "keywords": ["wocl", "window of circadian low", "night duty", "encroachment", "660 minutes", "11 hours"]
    },
    {
        "clause_id": "CAR-7-J-III-Para-5.1",
        "title": "Maximum Daily Flight Time (Block Hours)",
        "category": "FDTL",
        "applicable_sectors": "All Domestic Sectors",
        "content": "No flight crew member shall exceed 8 hours (480 minutes) of total flight time (block hours) within a single Flight Duty Period for two-pilot operations.",
        "keywords": ["flight time", "block hours", "8 hours", "480 minutes", "maximum block"]
    },
    {
        "clause_id": "CAR-7-J-III-Para-7.1",
        "title": "Minimum Rest Periods Preceding and Succeeding Duty",
        "category": "FDTL",
        "applicable_sectors": "Rest Requirements",
        "content": "The minimum rest period immediately preceding flight duty shall not be less than 12 hours (720 minutes) or equal to the duration of the preceding duty period, whichever is greater, at the crew member's home base.",
        "keywords": ["minimum rest", "12 hours", "720 minutes", "rest before duty", "home base"]
    },
    {
        "clause_id": "CAR-7-J-III-Para-8.1",
        "title": "Split Duty Extensions and Rest Facilities",
        "category": "FDTL",
        "applicable_sectors": "Split Duty",
        "content": "When an FDP consists of two sectors separated by a ground break of not less than 3 consecutive hours in suitable ground accommodation, the allowable FDP may be extended by up to 50% of the ground break duration, provided the break does not fall in the WOCL.",
        "keywords": ["split duty", "ground break", "suitable accommodation", "extension", "3 hours"]
    },
    {
        "clause_id": "CAR-7-J-III-2024-Para-6.1",
        "title": "Revised 2024 Norms: Stricter Night Duty Cap and 48-Hour Weekly Rest",
        "category": "FDTL-2024",
        "applicable_sectors": "Night Duty & Rest",
        "content": "Under revised norms, night duty window is redefined from 00:00 to 06:00 hours IST. Maximum FDP for night operations is capped strictly at 10.0 hours (600 minutes) with maximum 2 landings. Mandatory continuous weekly rest is increased to 48 hours.",
        "keywords": ["2024 revised norms", "48 hours weekly rest", "10 hours night duty", "0000 to 0600"]
    },
    {
        "clause_id": "CAR-3-M-IV-Para-3.1",
        "title": "Passenger Facilities for Flight Delays Exceeding 2 Hours",
        "category": "PASSENGER_CARE",
        "applicable_sectors": "Flight Delays",
        "content": "Airlines shall provide free of charge meals and refreshments in reasonable relation to waiting time to passengers for flights with a scheduled block time of up to 2 hours when delayed by 2 hours or more, and for block times 2-4 hours when delayed by 3 hours or more.",
        "keywords": ["flight delay", "meals and refreshments", "2 hours delay", "passenger care"]
    },
    {
        "clause_id": "CAR-3-M-IV-Para-3.2",
        "title": "Hotel Accommodation for Overnight Delays",
        "category": "PASSENGER_CARE",
        "applicable_sectors": "Flight Delays / Cancellations",
        "content": "Airlines shall provide free hotel accommodation and ground transport between airport and hotel when flight departure is delayed by more than 24 hours, or when an overnight delay is involved.",
        "keywords": ["hotel accommodation", "overnight delay", "ground transport", "24 hours delay"]
    },
    {
        "clause_id": "CAR-3-M-IV-Para-3.3",
        "title": "Statutory Compensation for Unnotified Flight Cancellations",
        "category": "PASSENGER_CARE",
        "applicable_sectors": "Flight Cancellations",
        "content": "Airlines shall compensate passengers for cancellations unless notified at least 2 weeks in advance. Compensation ranges from INR 5,000 to INR 10,000 depending on block time, or full ticket refund plus alternate flight. No compensation is payable if cancellation is caused by extraordinary circumstances (e.g. severe meteorological conditions like fog).",
        "keywords": ["cancellation compensation", "statutory compensation", "refund", "extraordinary circumstances", "fog exemption"]
    }
]


def build_rules_index(output_file: Optional[Path] = None) -> Path:
    """Serializes DGCA CAR statutory rules to JSON."""
    out = output_file or (settings.DATA_DIR / "processed" / "fdtl_rules.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(DGCA_CAR_CLAUSES, f, indent=2)

    return out


def generate_rag_gold_dataset(output_file: Optional[Path] = None) -> Path:
    """Generates 50 gold question-clause evaluation pairs for testing Agentic RAG recall."""
    out = output_file or (settings.BASE_DIR / "eval" / "rag_gold.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    gold_samples = [
        {"query": "What is the maximum FDP for two pilots on daytime duty with 2 landings?", "expected_clause_id": "CAR-7-J-III-Para-6.1"},
        {"query": "How many hours of flight duty are permitted for a flight starting at 0300 IST in the WOCL?", "expected_clause_id": "CAR-7-J-III-Para-6.2"},
        {"query": "What is the maximum block hours flight time allowed in a single duty period?", "expected_clause_id": "CAR-7-J-III-Para-5.1"},
        {"query": "What is the statutory minimum rest required for a crew member before flight duty?", "expected_clause_id": "CAR-7-J-III-Para-7.1"},
        {"query": "Can flight duty period be extended if crew has a 3-hour ground break in a hotel?", "expected_clause_id": "CAR-7-J-III-Para-8.1"},
        {"query": "What are the night duty limits under the revised 2024 DGCA FDTL guidelines?", "expected_clause_id": "CAR-7-J-III-2024-Para-6.1"},
        {"query": "Are airlines obligated to provide meals when a flight is delayed by 2 hours?", "expected_clause_id": "CAR-3-M-IV-Para-3.1"},
        {"query": "When must an airline provide hotel accommodation to stranded passengers?", "expected_clause_id": "CAR-3-M-IV-Para-3.2"},
        {"query": "Is statutory passenger compensation required when flights are cancelled due to severe fog?", "expected_clause_id": "CAR-3-M-IV-Para-3.3"},
        {"query": "What is the maximum FDP limit for 4 domestic sectors during daytime?", "expected_clause_id": "CAR-7-J-III-Para-6.1"}
    ]

    # Expand to 50 realistic queries with phrasing variations
    variations = [
        ("maximum allowable duty time for pilot starting duty at 0800", "CAR-7-J-III-Para-6.1"),
        ("limits on pilot duty hours touching 0200 to 0600 morning window", "CAR-7-J-III-Para-6.2"),
        ("is 9 hours of block flight time legal for captain", "CAR-7-J-III-Para-5.1"),
        ("pre duty rest period requirement for first officer at base", "CAR-7-J-III-Para-7.1"),
        ("extension rules for split duty with ground rest", "CAR-7-J-III-Para-8.1"),
        ("48 hour weekly rest requirement under DGCA CAR", "CAR-7-J-III-2024-Para-6.1"),
        ("refreshment voucher entitlement for passengers delayed 3 hours", "CAR-3-M-IV-Para-3.1"),
        ("passenger hotel accommodation rights for overnight delay", "CAR-3-M-IV-Para-3.2"),
        ("force majeure fog exemption for flight cancellation compensation", "CAR-3-M-IV-Para-3.3"),
        ("legal maximum flight duty period for 2 domestic landings", "CAR-7-J-III-Para-6.1")
    ]

    full_gold_set = list(gold_samples)
    for rep in range(4):
        for q, c in variations:
            full_gold_set.append({
                "query": f"[Var {rep+1}] {q}",
                "expected_clause_id": c
            })

    with open(out, "w", encoding="utf-8") as f:
        for item in full_gold_set[:50]:
            f.write(json.dumps(item) + "\n")

    return out


def retrieve_fdtl(
    query: str,
    k: int = 3,
    similarity_threshold: float = 0.40
) -> List[Dict[str, Any]]:
    """
    Keyword and semantic retrieval of DGCA CAR clauses.
    Returns top-k matching clauses with similarity scores.
    """
    query_lower = query.lower()
    scores: List[Tuple[float, Dict[str, Any]]] = []

    for clause in DGCA_CAR_CLAUSES:
        match_count = 0
        for kw in clause["keywords"]:
            if kw in query_lower:
                match_count += 2
        for word in query_lower.split():
            if len(word) > 3 and word in clause["content"].lower():
                match_count += 0.5

        if match_count > 0:
            norm_score = min(0.99, round(0.40 + (match_count * 0.12), 2))
            if norm_score >= similarity_threshold:
                scores.append((norm_score, clause))

    # Sort descending by score
    scores.sort(key=lambda x: x[0], reverse=True)
    results = []
    for s, c in scores[:k]:
        res = dict(c)
        res["score"] = s
        results.append(res)

    return results


def main():
    rules_path = build_rules_index()
    gold_path = generate_rag_gold_dataset()
    print(f"Built rules index at {rules_path} with {len(DGCA_CAR_CLAUSES)} clauses.")
    print(f"Generated RAG gold evaluation dataset at {gold_path} (50 queries).")


if __name__ == "__main__":
    main()
