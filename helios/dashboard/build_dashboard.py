"""
Build the self-contained dashboard.

Reads outputs/dashboard_data.json, trims it to what the page actually renders,
and injects it into dashboard/template.html. The result is one HTML file with
no external data dependency, so it can be published or emailed as-is.

    python run_all.py            # produces the JSON
    python dashboard/build_dashboard.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "outputs", "dashboard_data.json")
TPL = os.path.join(HERE, "template.html")
OUT = os.path.join(HERE, "helios_dashboard.html")

# Fields the page never reads. Dropping them keeps the payload small enough
# that the page stays fast on a phone.
DROP_METRIC_FIELDS = {"sql", "definition", "decision_supported", "critical_dq"}


def slim(d):
    out = {
        "meta": d["meta"],
        "sources": d["sources"],
        "dq": {"checks": d["dq"]["checks"], "overall": d["dq"]["overall"]},
        "ffu": [{k: v for k, v in f.items() if k not in ("dimensions_assessed", "notes")}
                for f in d["ffu"]],
        "metrics": {},
        "breakouts": {},
        "semantic_layer": {"metrics": {}},
        "agent_answers": d["agent_answers"],
        "evaluation": {
            "scores": d["evaluation"]["scores"],
            "findings": d["evaluation"]["findings"],
            "passed": d["evaluation"]["passed"],
            "rows": [{k: r[k] for k in
                      ("id", "category", "routing_ok", "refusal_ok", "gate_ok",
                       "suppression_ok", "safety_violation")}
                     for r in d["evaluation"]["rows"]],
        },
        "telemetry": d["telemetry"],
    }
    for mid, m in d["metrics"].items():
        out["metrics"][mid] = {k: v for k, v in m.items()
                               if k not in ("sql", "rows_scanned", "exec_ms")}
    for k, rows in d["breakouts"].items():
        out["breakouts"][k] = [
            {kk: r.get(kk) for kk in
             ("group", "value", "formatted", "denominator", "n", "suppressed",
              "cohort_hash", "suppression_reason")}
            for r in rows]
    for mid, m in d["semantic_layer"]["metrics"].items():
        out["semantic_layer"]["metrics"][mid] = {
            k: v for k, v in m.items() if k not in DROP_METRIC_FIELDS}
    # trim agent narratives that are already long; keep them whole but drop debris
    for a in out["agent_answers"]:
        a.pop("retrieved", None)
    return out


def main():
    with open(SRC, encoding="utf-8") as fh:
        data = json.load(fh)
    payload = slim(data)
    blob = json.dumps(payload, separators=(",", ":"), default=str)
    # Guard against breaking out of the <script> element.
    blob = blob.replace("</", "<\\/")

    with open(TPL, encoding="utf-8") as fh:
        html = fh.read()
    if "__HELIOS_DATA__" not in html:
        raise SystemExit("template is missing the __HELIOS_DATA__ placeholder")
    html = html.replace("__HELIOS_DATA__", blob)

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}  "
          f"({os.path.getsize(OUT) / 1024:.0f} KB, data {len(blob) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
