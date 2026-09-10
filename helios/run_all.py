"""
HELIOS - end-to-end pipeline.

    python run_all.py                # full run
    python run_all.py --skip-generate
    python run_all.py --ask "How long do patients wait for a diagnosis?"

Stages
  1  generate the synthetic RWD warehouse (skippable)
  2  run the data-quality suite and snapshot it
  3  score Fitness-for-Use for every governed metric
  4  compute the headline metric pack for the dashboard
  5  run the insight agent over the launch review questions
  6  run the golden-set evaluation and the release gate
  7  export outputs/dashboard_data.json and print the summary

Exit code is non-zero if the release gate fails, so this doubles as the CI job.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from helios import agent as agent_mod          # noqa: E402
from helios import cohort as co                # noqa: E402
from helios import dq as dqmod                 # noqa: E402
from helios import evals as evalmod            # noqa: E402
from helios import ffu as ffumod               # noqa: E402
from helios import metrics as metmod           # noqa: E402
from helios import privacy                     # noqa: E402
from helios import semantic_layer as sl        # noqa: E402
from helios import telemetry as telmod         # noqa: E402
from helios.db import Warehouse                # noqa: E402

DB = os.path.join("data", "helios.db")
OUT = "outputs"

# The questions a launch review actually opens with.
REVIEW_QUESTIONS = [
    "How long do patients wait for a confirmed diagnosis?",
    "Is SANOVIA uptake tracking to the launch curve?",
    "How many severe patients are getting no systemic therapy at all?",
    "Does payer channel change access to advanced therapy?",
    "What is first year adherence on advanced therapy?",
    "What is the emergency department burden for these patients?",
    "What does the real treatment pathway look like?",
    "What is the patient reported quality of life in the registry?",
    "Which individual doctor prescribes the most SANOVIA?",
]


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-generate", action="store_true")
    ap.add_argument("--patients", type=int, default=40000)
    ap.add_argument("--ask", default=None, help="ask one question and exit")
    ap.add_argument("--planner", default=None, choices=("deterministic", "model"),
                    help="deterministic (default) or model")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    # ---- 1. generate --------------------------------------------------
    if not args.skip_generate or not os.path.exists(DB):
        rule("STAGE 1  Generate synthetic RWD warehouse")
        subprocess.run([sys.executable, "data/generator/generate_rwd.py",
                        "--out", DB, "--patients", str(args.patients)], check=True)

    wh = Warehouse(DB)
    tel = telmod.Telemetry(os.path.join(OUT, "telemetry.db"))

    if args.ask:
        from helios import llm
        ag = agent_mod.InsightAgent(wh, planner=llm.get_planner(args.planner),
                                    telemetry=tel)
        print(ag.ask(args.ask).render())
        return 0

    # ---- 2. data quality ----------------------------------------------
    rule("STAGE 2  Data quality suite")
    dq_results = dqmod.run_all(wh)
    tel.snapshot_dq(dq_results)
    dims = dqmod.dimension_scores(dq_results)
    for r in dq_results:
        print(f"  [{r['status']:4s}] {r['check_id']}  {r['score']:5.1f}  "
              f"{r['dimension']:26s} {r['value']} {r['unit']}")
    print(f"\n  Overall DQ score (mean of dimension worst-cases): {dqmod.overall(dq_results)}")
    fails = dqmod.failing(dq_results, ("FAIL",))
    print(f"  {len(fails)} failing checks; top remediation owner: "
          f"{fails[0]['owner'] if fails else 'n/a'}")

    # ---- 3. fitness for use -------------------------------------------
    rule("STAGE 3  Fitness-for-Use by business question")
    ffu_all = ffumod.assess_all(wh, dq_results=dq_results)
    for a in sorted(ffu_all, key=lambda x: x["ffu_score"]):
        print(f"  {a['band']:6s} {a['ffu_score']:5.1f}  {a['metric_id']:38s} "
              f"{a['metric_label'][:44]}")
    bands = {}
    for a in ffu_all:
        bands[a["band"]] = bands.get(a["band"], 0) + 1
    print(f"\n  {bands}")

    # ---- 4. metric pack ------------------------------------------------
    rule("STAGE 4  Headline metric pack")
    pack = {}
    for mid in sl.METRICS:
        r = metmod.compute(wh, mid)
        pack[mid] = r.to_dict()
        print(f"  {mid:38s} {r.formatted():>14s}  n={r.denominator or r.n:,}")

    breakouts = {}
    for mid, dim in [("M01_time_to_diagnosis", "rurality"),
                     ("M01_time_to_diagnosis", "province"),
                     ("M12_untreated_severe_gap", "province"),
                     ("M03_advanced_therapy_initiation_rate", "insurance_type"),
                     ("M05_persistence_12mo", "rurality"),
                     ("M08_ed_visits_per_100_patients", "severity")]:
        rows = metmod.compute_by(wh, mid, dim)
        breakouts[f"{mid}__{dim}"] = [
            {"group": r["group"], **r["result"].to_dict()} for r in rows]
    print(f"  {len(breakouts)} break-outs computed")

    # ---- 5. agent over the review questions ----------------------------
    rule("STAGE 5  Insight agent - launch review questions")
    from helios import llm
    ag = agent_mod.InsightAgent(wh, planner=llm.get_planner(args.planner),
                                telemetry=tel, dq_results=dq_results)
    answers = []
    for q in REVIEW_QUESTIONS:
        a = ag.ask(q)
        answers.append({
            "question": q, "status": a.status, "narrative": a.narrative,
            "band": (a.ffu or {}).get("band"),
            "ffu_score": (a.ffu or {}).get("ffu_score"),
            "citations": a.citations,
            "groundedness": (a.verification or {}).get("groundedness"),
            "claims": (a.verification or {}).get("total_claims"),
            "latency_ms": round(a.timings["total"], 1),
            "metric_id": a.plan.get("metric_id"),
            "breakdown": a.plan.get("breakdown"),
            "planner": a.plan.get("planner"),
            "retrieved": a.retrieved[:4],
        })
        flag = {"answered": "ANSWERED", "refused_not_fit": "REFUSED (not fit)",
                "refused_out_of_scope": "REFUSED (out of scope)",
                "blocked_unverified": "BLOCKED (unverified)"}[a.status]
        print(f"  [{flag:24s}] {q[:52]:52s} {a.timings['total']:7.0f} ms")

    # ---- 6. evaluation + release gate ----------------------------------
    rule("STAGE 6  Golden-set evaluation and release gate")
    rows, scores, findings, passed = evalmod.run_and_gate(ag)
    print(evalmod.report(rows, scores, findings, passed))

    # ---- 7. export ------------------------------------------------------
    rule("STAGE 7  Export")
    src_rows, _ = wh.query("SELECT * FROM source_metadata")
    counts = {t: wh.scalar(f"SELECT COUNT(*) FROM {t}")
              for t in ["patient", "claim_medical", "claim_pharmacy",
                        "ehr_encounter", "registry_enrollment", "provider"]}
    payload = {
        "meta": {
            "generated_at": datetime.datetime.now(datetime.timezone.utc)
                            .isoformat(timespec="seconds"),
            "brand": "SANOVIA (fictional)",
            "therapy_area": "Type 2 inflammation (atopic dermatitis / severe asthma)",
            "launch_date": "2024-09-01",
            "semantic_layer_version": co.SPEC_VERSION,
            "min_cell_size": privacy.MIN_CELL,
            "row_counts": counts,
            "warehouse_queries": wh.stats["queries"],
            "warehouse_rows_scanned": wh.stats["rows"],
        },
        "sources": src_rows,
        "dq": {"checks": dq_results, "dimensions": dims,
               "overall": dqmod.overall(dq_results)},
        "ffu": ffu_all,
        "metrics": pack,
        "breakouts": breakouts,
        "semantic_layer": {
            "metrics": {k: {kk: vv for kk, vv in v.items() if kk != "sql"}
                        for k, v in sl.METRICS.items()},
            "dimensions": sl.DIMENSIONS,
            "tables": sl.TABLES,
            "business_questions": sl.BUSINESS_QUESTIONS,
        },
        "agent_answers": answers,
        "evaluation": {"scores": scores, "findings": findings,
                       "passed": passed, "rows": rows},
        "telemetry": {"summary": tel.summary(), "by_band": tel.by_band(),
                      "stage_latency": tel.stage_latency()},
        "privacy_audit": privacy.audit_log()[-40:],
    }
    path = os.path.join(OUT, "dashboard_data.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, default=str)
    print(f"  wrote {path}  ({os.path.getsize(path) / 1024:.0f} KB)")

    t = tel.summary()
    print(f"\n  Telemetry: {t['answers']} events | "
          f"groundedness {t['mean_groundedness']} | "
          f"p50 {t.get('p50_ms')} ms / p95 {t.get('p95_ms')} ms | "
          f"{t['blocked']} blocked")
    print(f"  Privacy audit entries: {len(privacy.audit_log())}")

    rule("DONE")
    print(f"  Release gate: {'PASS' if passed else 'FAIL'}")
    print("  Next: python dashboard/build_dashboard.py")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
