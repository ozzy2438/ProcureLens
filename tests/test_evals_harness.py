import json
import pathlib

GOLDEN = pathlib.Path(__file__).parent.parent / "evals" / "golden_set.jsonl"


def test_golden_set_is_valid_jsonl():
    cases = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    assert len(cases) >= 5
    assert all("id" in c and "question" in c for c in cases)
