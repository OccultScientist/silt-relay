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
            passage = archive.passages.get(source_id)
            matches = passage is not None and source_text.get(source_id) == claim["text"] == passage.text
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


def discovery_sources(result):
    if result["reference"]:
        yield result["reference"]["code"], result["reference"]
    for source in result["format_conflicts"]:
        yield source["code"], source
    for record in result["matches"]:
        sources = [record["sound"], *record["format_sources"], *record["proposed"]]
        for comparison in record["comparisons"]:
            sources.extend(comparison["original"].values())
            sources.extend(comparison["reissue"].values())
            sources.append(comparison["relationship"])
        for source in sources:
            yield record["code"], source
    for proposal in result["proposals"]:
        for source in [proposal["sound"], *proposal["sources"]]:
            yield proposal["sound"]["code"], source


def measure_discovery(archive, cases, mode):
    family_found = family_total = evidence_found = evidence_total = 0
    changes_correct = changes_total = withholding_correct = withholding_total = 0
    invalid = []
    failures = []
    for case in cases:
        result = archive.dig(case["question"], mode)
        matches = {row["code"]: row for row in result["matches"]}
        gold_families = set(case.get("families", []))
        gold_sources = set(case.get("sources", []))
        alternatives = [set(group) for group in case.get("source_alternatives", [])]
        sources = list(discovery_sources(result))
        source_ids = {source["id"] for _, source in sources}
        issues = {}

        invalid_sources = []
        for owner, source in sources:
            passage = archive.passages.get(source["id"])
            owner_family = archive.releases[owner].get("reissue_of", owner)
            source_release = archive.releases.get(source["code"], {})
            source_family = source_release.get("reissue_of", source["code"])
            if (passage is None or owner_family != source_family or
                    any(getattr(passage, key) != source[key] for key in ("code", "title", "field", "text"))):
                invalid.append({"id": case["id"], "source": source["id"]})
                invalid_sources.append(source["id"])
        if invalid_sources:
            issues["invalid_sources"] = sorted(set(invalid_sources))

        family_found += len(gold_families & matches.keys())
        family_total += len(gold_families)
        evidence_found += len(gold_sources & source_ids) + sum(bool(group & source_ids) for group in alternatives)
        evidence_total += len(gold_sources) + len(alternatives)
        if gold_families - matches.keys():
            issues["missing_families"] = sorted(gold_families - matches.keys())
        if case.get("only_families") and matches.keys() - gold_families:
            issues["unexpected_families"] = sorted(matches.keys() - gold_families)
        unexpected_families = set(case.get("excluded_families", [])) & matches.keys()
        if "allowed_families" in case:
            unexpected_families |= matches.keys() - set(case["allowed_families"])
        if unexpected_families:
            issues["unexpected_families"] = sorted(unexpected_families)
        unexpected_sources = set(case.get("excluded_sources", [])) & source_ids
        if unexpected_sources:
            issues["unexpected_sources"] = sorted(unexpected_sources)
        if "reference" in case and (result["reference"] or {}).get("id") != case["reference"]:
            issues["missing_reference"] = case["reference"]
        if "message_contains" in case and case["message_contains"] not in result["message"]:
            issues["expected_message"] = case["message_contains"]
        for code, expected in case.get("format_checks", {}).items():
            if matches.get(code, {}).get("format_check") != expected:
                issues.setdefault("wrong_format_checks", []).append(code)
        for code, expected in case.get("sound_cues", {}).items():
            actual = matches.get(code, {}).get("matched", {})
            if not expected.items() <= actual.items():
                issues.setdefault("missing_sound_cues", []).append(code)
        if gold_sources - source_ids:
            issues["missing_sources"] = sorted(gold_sources - source_ids)
        missing_alternatives = [sorted(group) for group in alternatives if not group & source_ids]
        if missing_alternatives:
            issues["missing_source_alternatives"] = missing_alternatives
        if "first" in case and next(iter(matches), None) != case["first"]:
            issues["expected_first"] = case["first"]

        deltas = {
            row["reissue"]["tracks"]["code"]: {key: row[key] for key in ("added", "original_only")}
            for match in matches.values() for row in match["comparisons"]
        }
        for reissue, expected in case.get("changes", {}).items():
            changes_total += 1
            if deltas.get(reissue) == expected:
                changes_correct += 1
            else:
                issues.setdefault("wrong_changes", []).append(reissue)

        withholding_issues = {}
        if case.get("no_matches") and matches:
            withholding_issues["unexpected_matches"] = list(matches)
        proposal_ids = sorted(source["id"] for row in result["proposals"] for source in row["sources"])
        if "proposals" in case and proposal_ids != case["proposals"]:
            withholding_issues["expected_proposals"] = case["proposals"]
            withholding_issues["actual_proposals"] = proposal_ids
        for code, expected in case.get("unconfirmed", {}).items():
            actual = set(matches.get(code, {}).get("unmatched", []))
            if set(expected) - actual:
                withholding_issues["unconfirmed_missing"] = sorted(set(expected) - actual)
        if any(key in case for key in ("no_matches", "proposals", "unconfirmed")):
            withholding_total += 1
            withholding_correct += not withholding_issues
        issues.update(withholding_issues)
        if issues:
            failures.append({"id": case["id"], "top": list(matches), **issues})

    return {
        "full_case_passes": [len(cases) - len(failures), len(cases)],
        "expected_family_recall": [family_found, family_total],
        "required_source_recall": [evidence_found, evidence_total],
        "tracklist_changes_correct": [changes_correct, changes_total],
        "withholding_correctness": [withholding_correct, withholding_total],
        "invalid_citations": invalid,
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "evaluation"), default="evaluation")
    suite = parser.add_mutually_exclusive_group()
    suite.add_argument("--discovery", action="store_true", help="Evaluate crate-digging and edition reasoning.")
    suite.add_argument("--audit", action="store_true", help="Re-run fresh questions from the portfolio review.")
    args = parser.parse_args()
    if args.discovery or args.audit:
        split = "audit" if args.audit else "discovery"
        selected = json.loads((DATA / f"{split}.json").read_text(encoding="utf-8"))
        evaluator = measure_discovery
    else:
        split = args.split
        cases = json.loads((DATA / "evaluation.json").read_text(encoding="utf-8"))
        selected = [case for case in cases if case["split"] == split]
        evaluator = measure
    archive = Archive.from_directory(DATA)
    try:
        report = {mode: evaluator(archive, selected, mode) for mode in MODES}
    finally:
        archive.close()
    print(json.dumps({
        "split": split, "cases": len(selected), "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version, "modes": report,
    }, ensure_ascii=False, indent=2))
    if any(metrics["invalid_citations"] for metrics in report.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
