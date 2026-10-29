"""
Unit tests for DGCA CAR rules indexing, RAG retrieval, and gold set evaluation.
"""

from pathlib import Path
import json

from skymediator.ingest.build_rules_index import (
    build_rules_index,
    generate_rag_gold_dataset,
    retrieve_fdtl,
    DGCA_CAR_CLAUSES
)


def test_build_rules_index(tmp_path: Path):
    out = tmp_path / "rules.json"
    res_path = build_rules_index(out)
    assert res_path.exists()

    with open(res_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == len(DGCA_CAR_CLAUSES)
    assert data[0]["clause_id"] == "CAR-7-J-III-Para-6.1"


def test_generate_rag_gold_dataset(tmp_path: Path):
    out = tmp_path / "gold.jsonl"
    res_path = generate_rag_gold_dataset(out)
    assert res_path.exists()

    with open(res_path, "r", encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]

    assert len(lines) == 50
    assert "query" in lines[0]
    assert "expected_clause_id" in lines[0]


def test_retrieve_fdtl_accuracy():
    # Query WOCL night duty limits
    res = retrieve_fdtl("what is the flight duty period limit in WOCL night hours", k=2)
    assert len(res) > 0
    top = res[0]
    assert top["clause_id"] == "CAR-7-J-III-Para-6.2"
    assert top["score"] >= 0.50

    # Query passenger delay meals
    res_pax = retrieve_fdtl("are passengers entitled to meals for 2 hours delay", k=2)
    assert len(res_pax) > 0
    assert res_pax[0]["clause_id"] == "CAR-3-M-IV-Para-3.1"
