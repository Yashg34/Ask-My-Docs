"""Aggregates scored_results.json into mean scores per metric + a markdown
report with the worst-scoring questions per metric, so you can spot patterns
(e.g. all faithfulness failures on one document) instead of just a number.

Usage:
    python report.py
"""

import json
import statistics as stats

from config import RESULTS_DIR

SCORED_PATH = RESULTS_DIR / "scored_results.json"
REPORT_PATH = RESULTS_DIR / "report.md"

METRICS = [
    "hit_rate", "context_recall", "context_precision", "mrr",
    "citation_precision", "citation_recall", "citation_presence",
    "faithfulness", "answer_correctness", "answer_relevancy",
]


def main():
    items = json.loads(SCORED_PATH.read_text())
    scored = [i for i in items if "error" not in i]

    lines = ["# Evaluation Report", "", f"Scored {len(scored)}/{len(items)} questions", "", "| Metric | Mean |", "|---|---|"]

    worst_sections = []
    for m in METRICS:
        values = [(i["id"], i[m]) for i in scored if i.get(m) is not None]
        if not values:
            continue
        mean = stats.mean(v for _, v in values)
        lines.append(f"| {m} | {mean:.3f} |")

        worst = sorted(values, key=lambda x: x[1])[:5]
        worst_sections.append(f"### Worst on `{m}`\n" + "\n".join(f"- {qid}: {v:.2f}" for qid, v in worst))

    lines.append("")
    lines.extend(worst_sections)

    REPORT_PATH.write_text("\n".join(lines))
    print(f"✅ Report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()