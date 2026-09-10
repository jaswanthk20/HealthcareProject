"""Generate data dictionary and quality results from the validated public-data payload."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    data = json.loads((ROOT / "outputs/dashboard_data.json").read_text(encoding="utf-8"))
    s = data["source"]
    dictionary = "# Official data dictionary\n\nSource: [Statistics Canada table " + s["table"] + "](" + s["url"] + ").\n\n"
    dictionary += "Grain: one percentage estimate per reference year, geography, age, sex and governed indicator. These are published survey aggregates, not patient records.\n\n"
    dictionary += "| Field | Meaning |\n|---|---|\n| year | Official reference year, distinct from release or download date |\n| geography | Province or Canada excluding territories |\n| age / sex | Exact population dimensions from the source |\n| indicator | Governed identifier linked to the official label |\n| value | Published percentage, null when not releasable |\n| low / high | Published bootstrap 95% confidence interval; never recomputed |\n| *_status | Source quality symbols, preserved independently |\n| *_vector | Statistics Canada series reference |\n| quality | published, caution or unavailable; a display rule, not certification |\n\n"
    dictionary += "## Governed indicators\n\n" + "\n".join("- `" + key + "`: " + label for key, label in data["indicators"].items())
    dictionary += "\n\n## Population dimensions\n\n" + "\n".join("- **" + key + "**: " + "; ".join(values) for key, values in data["dimensions"].items()) + "\n"
    (ROOT / "docs/03_data_dictionary.md").write_text(dictionary, encoding="utf-8")
    report = "# Official-source quality results\n\nPublished: " + s["release_date"] + ". Reference years: " + s["first_year"] + "–" + s["latest_year"] + ".\n\n"
    report += "Source rows inspected: " + str(s["source_rows"]) + ". Governed estimate cells: " + str(len(data["rows"])) + ".\n\n"
    report += "| Display status | Cells |\n|---|---:|\n" + "\n".join("| " + q + " | " + str(n) + " |" for q,n in data["quality"].items())
    report += "\n\nMissing and suppressed estimates remain null. No defects or observations are injected. These statuses do not certify clinical fitness.\n\nSource SHA-256: `" + s["source_sha256"] + "`.\n"
    (ROOT / "docs/05a_dq_ffu_live_results.md").write_text(report, encoding="utf-8")

if __name__ == "__main__": main()
