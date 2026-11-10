"""Compare retrieval modes against human-readable, versioned relevance judgements."""
import argparse
import json
import platform
import sqlite3

from silt_relay import Archive, DATA, MODES, TOP_K


def measure(archive, cases, mode):
    answer_count = outcome_correct = supported = emitted = evidence_total = found = 0
    withheld_total = withheld_correct = retrieval_total = retrieval_found = 0
    unsafe = []
    failures = []
    for case in cases:
        gold = set(case["sources"])
        if case["task"] == "search":
            ids = [hit["id"] for hit in archive.search(case["question"], mode)]
            retrieved = gold.intersection(ids)
            retrieval_total += len(gold)
            retrieval_found += len(retrieved)
            if retrieved != gold:
                failures.append({"id": case["id"], "missing": sorted(gold - retrieved), "top": ids})
            continue

        result = archive.answer(case["question"], mode)
        answer_count += 1
        actual = {claim["source_id"] for claim in result["claims"]}
        choices = sorted(row["code"] for row in result["choices"])
        correct_outcome = result["outcome"] == case["outcome"] and choices == case.get("choices", [])
        outcome_correct += correct_outcome
        if case["outcome"] in {"insufficient_evidence", "needs_clarification", "partially_answered"}:
            withheld_total += 1
            withheld_correct += correct_outcome and actual == gold

        source_text = {row["id"]: row["text"] for row in result["retrieved"]}
        for claim in result["claims"]:
            source_id = claim["source_id"]
            matches = source_text.get(source_id) == claim["text"] == archive.passages[source_id].text
            if not matches:
                unsafe.append(case["id"])
            supported += matches and source_id in gold
            emitted += 1
        evidence_total += len(gold)
        found += len(gold & actual)
        if not correct_outcome or actual != gold:
            failures.append({
                "id": case["id"], "expected_outcome": case["outcome"], "outcome": result["outcome"],
                "missing": sorted(gold - actual), "unexpected": sorted(actual - gold),
            })

    return {
        f"passage_recall_at_{TOP_K}": [retrieval_found, retrieval_total],
        "answer_outcome_accuracy": [outcome_correct, answer_count],
        "citation_support": [supported, emitted],
        "required_answer_evidence_recall": [found, evidence_total],
        "withholding_correctness": [withheld_correct, withheld_total],
        "invalid_citations": unsafe,
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "evaluation"), default="evaluation")
    args = parser.parse_args()
    cases = json.loads((DATA / "evaluation.json").read_text(encoding="utf-8"))
    selected = [case for case in cases if case["split"] == args.split]
    archive = Archive.from_directory(DATA)
    try:
        report = {mode: measure(archive, selected, mode) for mode in MODES}
    finally:
        archive.close()
    print(json.dumps({
        "split": args.split, "cases": len(selected), "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version, "modes": report,
    }, ensure_ascii=False, indent=2))
    if any(metrics["invalid_citations"] for metrics in report.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
