"""Select a cutoff using dev only; report test once without changing service settings."""

import argparse
import hashlib
import json
from pathlib import Path

from scripts.evaluate_knowledge import aggregate, load_cases, metrics

CUTOFFS = (0, 0.0001, 0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)


def score_split(cases, report, split, cutoff):
    source = {row["id"]: row for row in report["cases"]}
    rows = []
    for case in cases:
        if case.split != split:
            continue
        samples = source[case.id]["samples"]
        values = []
        for sample in samples:
            ranked = [
                tuple(ref)
                for ref, score in zip(sample["ranked"], sample["scores"], strict=True)
                if score >= cutoff
            ]
            values.append(metrics(case, ranked))
        rows.append({"metrics": {k: sum(v[k] for v in values) / len(values) for k in values[0]}})
    return aggregate(rows)


def tune(cases, report):
    config = report["ranking_config"]
    if (
        config["score_type"] != "reranker_sigmoid"
        or config["reranker"]["min_score"] != 0
        or report["thresholds"] != [None]
    ):
        raise ValueError("Require reranker output with zero cutoff and no cosine gate")
    dev = [c for c in cases if c.split == "dev"]
    if not any(c.expected for c in dev) or not any(not c.expected for c in dev):
        raise ValueError("Dev needs both positive and negative cases")
    trials = []
    for cutoff in CUTOFFS:
        summary = score_split(cases, report, "dev", cutoff)
        objective = (summary["metrics"]["recall_at_5"] + summary["metrics"]["no_answer_accuracy"]) / 2
        trials.append({"cutoff": cutoff, "objective": objective, "dev": summary})
    # Deterministic tie break: prefer the lower cutoff to preserve recall.
    best = max(trials, key=lambda row: row["objective"])
    return {
        "selection": "dev mean(Recall@5, no-answer accuracy); lower-cutoff tie break",
        "selected_cutoff": best["cutoff"],
        "dev_trials": trials,
        "test": score_split(cases, report, "test", best["cutoff"]),
        "limitation": "Offline filtering of recorded top-20; no service settings changed; no latency estimate",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("report")
    parser.add_argument("--output", default=".run/search-eval/cutoff-selection.json")
    args = parser.parse_args()
    path = Path(args.dataset)
    report = json.loads(Path(args.report).read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest() != report["dataset_sha256"]:
        parser.error("Dataset hash mismatch")
    result = tune(load_cases(path), report)
    result["dataset_sha256"] = report["dataset_sha256"]
    result["source_created_at"] = report["created_at"]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    output.chmod(0o600)
    print(json.dumps({k: v for k, v in result.items() if k != "dev_trials"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
