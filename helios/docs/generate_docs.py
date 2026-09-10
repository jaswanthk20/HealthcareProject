"""
Generate the documentation that must never drift from the code.

The data dictionary and the DQ/FFU appendix are derived from the semantic
layer and from a live run, not maintained by hand. A hand-maintained data
dictionary is wrong within two sprints; this one is wrong only if the product
is wrong.

    python docs/generate_docs.py
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from helios import cohort as co            # noqa: E402
from helios import dq as dqmod             # noqa: E402
from helios import ffu as ffumod           # noqa: E402
from helios import privacy                 # noqa: E402
from helios import semantic_layer as sl    # noqa: E402
from helios.db import Warehouse            # noqa: E402

DOCS = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(DOCS, "..", "data", "helios.db")
STAMP = datetime.date.today().isoformat()

BANNER = ("<!-- GENERATED FILE - do not edit by hand.\n"
          "     Source: src/helios/semantic_layer.py + a live warehouse run.\n"
          "     Regenerate: python docs/generate_docs.py -->\n")


def data_dictionary(wh):
    L = [BANNER, "# HELIOS Data Dictionary", "",
         f"*Generated {STAMP} from semantic layer v{co.SPEC_VERSION}. "
         "Every definition below is the one the product actually computes.*", "",
         "All data is synthetic. `SANOVIA` is a fictional brand.", "",
         "---", "", "## 1. Contracted sources", "",
         "| Source | Type | Geography | Refresh | Publication lag | Consent basis "
         "| Licence expiry | Rows |",
         "|---|---|---|---|---|---|---|---|"]
    rows, _ = wh.query("SELECT * FROM source_metadata ORDER BY source_id")
    for r in rows:
        L.append(f"| `{r['source_id']}` | {r['source_type']} | {r['geography']} "
                 f"| {r['refresh_cadence_days']}d | **{r['publication_lag_days']}d** "
                 f"| {r['consent_basis']} | {r['license_expiry']} "
                 f"| {r['record_count']:,} |")

    L += ["", "---", "", "## 2. Tables", ""]
    for tname, t in sl.TABLES.items():
        n = wh.scalar(f"SELECT COUNT(*) FROM {tname}")
        L += [f"### `{tname}`", "",
              f"- **Grain**: {t['grain']}",
              f"- **Rows**: {n:,}",
              f"- **Steward**: {t['steward']}",
              f"- **Privacy class**: {t['pii_class']}", "",
              t["description"], "",
              "| Column | Type | Definition |", "|---|---|---|"]
        cols = wh.columns(tname)
        types = {r["name"]: r["type"] for r in
                 [dict(x) for x in wh.con.execute(f"PRAGMA table_info({tname})")]}
        for c in cols:
            note = t["key_columns"].get(c, "-")
            L.append(f"| `{c}` | {types.get(c, '')} | {note} |")
        L.append("")

    L += ["---", "", "## 3. Governed dimensions", "",
          "Cohort filters and break-outs may only use these. Anything else is "
          "rejected by the cohort compiler before a query is built.", "",
          "| Dimension | Type | Permitted values | Definition |", "|---|---|---|---|"]
    for did, d in sl.DIMENSIONS.items():
        L.append(f"| `{did}` | {d['type']} | {', '.join('`%s`' % v for v in d['values'])} "
                 f"| {d['description']} |")

    L += ["", "---", "", "## 4. Governed metrics", "",
          f"{len(sl.METRICS)} metrics. Each carries the decision it supports, its "
          "owner, the DQ dimensions it depends on, and the caveat that must travel "
          "with any published figure.", ""]
    for mid, m in sl.METRICS.items():
        L += [f"### `{mid}` - {m['label']}", "",
              f"| | |", "|---|---|",
              f"| **Definition** | {m['definition']} |",
              f"| **Grain** | {m['grain']} |",
              f"| **Unit** | {m['unit']} |",
              f"| **Decision supported** | {m['decision_supported']} |",
              f"| **Business owner** | {m['owner']} |",
              f"| **Required sources** | {', '.join('`%s`' % s for s in m['required_sources'])} |",
              f"| **Critical DQ dimensions** | {', '.join('`%s`' % d for d in m['critical_dq'])} |",
              f"| **Caveat (published with every figure)** | {m['caveat']} |", ""]

    L += ["---", "", "## 5. Registered business questions", "",
          "The routing table between a launch decision and a governed metric. A "
          "question that is not on this list and does not match a metric "
          "definition is refused rather than approximated.", "",
          "| ID | Question | Metric | Default break-out | Decision | Stakeholder |",
          "|---|---|---|---|---|---|"]
    for bq in sl.BUSINESS_QUESTIONS:
        L.append(f"| {bq['id']} | {bq['question']} | `{bq['metric']}` "
                 f"| {bq['breakdown'] or '-'} | {bq['decision']} | {bq['stakeholder']} |")

    L += ["", "---", "", "## 6. Privacy policy applied to every figure", "",
          f"- Minimum cell size: **{privacy.MIN_CELL}** patients.",
          "- Primary suppression (P1): any cell with a denominator below the "
          "minimum is suppressed.",
          "- Numerator suppression (P2): a non-zero numerator below the minimum "
          "is suppressed even when the denominator is large.",
          "- Complementary suppression (P3): if exactly one cell in a break-out "
          "is suppressed, the next-smallest is suppressed too, so the first "
          "cannot be recovered by subtraction.",
          "- Consent enforcement (P4): registry rows with `consent_flag = 0` are "
          "excluded at the cohort layer.",
          "- Audit (P5): every suppression decision is logged with its cohort hash.", ""]
    return "\n".join(L)


def dq_ffu_appendix(wh):
    dq_results = dqmod.run_all(wh)
    dims = dqmod.dimension_scores(dq_results)
    ffu_all = ffumod.assess_all(wh, dq_results=dq_results)

    L = [BANNER, "# Appendix - Live Data Quality and Fitness-for-Use Results", "",
         f"*Generated {STAMP} from an actual run against the warehouse.*", "",
         f"**Overall DQ score: {dqmod.overall(dq_results)}/100** "
         "(mean of per-dimension worst-case scores).", "",
         "## A1. Check results", "",
         "| Check | Dimension | Table | Observed | Score | Status | Severity | Owner |",
         "|---|---|---|---|---|---|---|---|"]
    for r in dq_results:
        L.append(f"| {r['check_id']} | `{r['dimension']}` | `{r['table']}` "
                 f"| {r['value']} {r['unit']} | {r['score']} | **{r['status']}** "
                 f"| {r['severity']} | {r['owner']} |")

    L += ["", "## A2. Failing checks, business impact and remediation", ""]
    for r in dqmod.failing(dq_results, ("FAIL", "WARN")):
        L += [f"### {r['check_id']} - {r['description']}", "",
              f"- **Observed**: {r['value']} {r['unit']} "
              f"(green at {r['green_threshold']}, red at {r['red_threshold']})",
              f"- **Rows affected**: {r['rows_affected']:,}" if r['rows_affected'] else "",
              f"- **Severity**: {r['severity']}",
              f"- **Business impact**: {r['business_impact']}",
              f"- **Remediation**: {r['remediation']}",
              f"- **Owner**: {r['owner']}", ""]

    L += ["## A3. Dimension roll-up", "",
          "| Dimension | Score | Status | Driven by |", "|---|---|---|---|"]
    for d in sorted(dims.values(), key=lambda x: x["score"]):
        L.append(f"| `{d['dimension']}` | {d['score']} | {d['status']} "
                 f"| {d['driver']} - {d['driver_description']} |")

    L += ["", "## A4. Fitness-for-Use verdict per metric", "",
          "Scored against the full patient population. A narrower cohort scores "
          "differently, which is the entire point of scoring the question rather "
          "than the dataset.", "",
          "| Metric | FFU | Band | Asset | Cohort | Governance | Permitted use |",
          "|---|---|---|---|---|---|---|"]
    for a in sorted(ffu_all, key=lambda x: -x["ffu_score"]):
        c = a["components"]
        L.append(f"| `{a['metric_id']}` | {a['ffu_score']} | **{a['band']}** "
                 f"| {c['asset_quality']} | {c['cohort_sufficiency']} "
                 f"| {c['governance']} | {a['permitted_use'].split('.')[0]} |")

    blocked = [a for a in ffu_all if a["blocked"]]
    if blocked:
        L += ["", "## A5. Metrics currently blocked from publication", ""]
        for a in blocked:
            L += [f"### `{a['metric_id']}` - {a['metric_label']}", ""]
            for v in a["veto_reasons"]:
                L.append(f"- {v}")
            L.append("")
            for d in a["top_drivers"]:
                L += [f"**Remediation ({d['owner']})**: {d['remediation']}", ""]
    return "\n".join(L)


def main():
    wh = Warehouse(DB)
    targets = [("03_data_dictionary.md", data_dictionary(wh)),
               ("05a_dq_ffu_live_results.md", dq_ffu_appendix(wh))]
    for name, body in targets:
        path = os.path.join(DOCS, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"  wrote docs/{name}  ({len(body) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
