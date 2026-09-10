"""
Fitness-for-Use (FFU) scoring.

The idea this product is built around
-------------------------------------
Most data-quality tooling answers "is this dataset good?". That question has no
useful answer, because the same asset is excellent for one decision and
dangerous for another. A 40% EHR lab-missingness rate is irrelevant to a
launch-uptake trend and disqualifying for a biomarker sub-analysis.

So HELIOS never scores a dataset. It scores a (metric x cohort) pair - that is,
a specific business question - and returns a verdict on what that answer may be
used for:

    GREEN  decision-grade   may be quoted in a governance forum as-is
    AMBER  directional      may be used with its caveat attached, never alone
    RED    not fit          blocked from publication; the agent must refuse

Score composition
-----------------
    60%  asset quality   - weighted mean of the DQ dimensions this metric
                           actually depends on (metric.critical_dq)
    25%  cohort sufficiency - is the denominator big enough to support the
                           claim, and does the break-out survive small-cell
                           policy?
    15%  governance      - licence validity, consent, and source availability

Veto rules (these override the weighted score, because some failures are not
tradeable against a good average):
    V1  any critical DQ dimension below 25          -> RED
    V2  any critical-severity governance failure    -> RED and blocked
    V3  denominator below the minimum cell size     -> RED and blocked
    V4  the metric's required source is expired     -> RED and blocked
"""

import datetime

from . import cohort as co
from . import dq as dqmod
from . import privacy
from . import semantic_layer as sl

TODAY = datetime.date(2026, 9, 10)

# Which contracted source each physical table belongs to. A governance failure
# is only allowed to veto a metric that actually reads the affected source -
# a consent breach in the registry must not block a pharmacy-claims metric.
TABLE_SOURCES = {
    "registry_enrollment": ["REG_T2INFLAM"],
    "claim_pharmacy": ["CLM_NATL_PBM"],
    "claim_medical": ["CLM_PRIV_PAYER", "PROV_ADMIN_QC"],
    "ehr_encounter": ["EHR_AMBULATORY"],
    "patient": ["*"],              # the spine underpins every metric
    "provider": ["*"],
    "source_metadata": ["*"],
}

GREEN, AMBER = 75.0, 50.0
W_ASSET, W_COHORT, W_GOV = 0.60, 0.25, 0.15

# A denominator large enough for the claim to be stable, by grain.
MIN_VIABLE_N = {"rate": 100, "distribution": 100, "series": 200, "category": 200}


def band(score, vetoed=False):
    if vetoed or score < AMBER:
        return "RED"
    return "GREEN" if score >= GREEN else "AMBER"


PERMITTED_USE = {
    "GREEN": "Decision-grade. May be quoted directly in a governance forum.",
    "AMBER": "Directional only. Must be published with its caveat attached and "
             "must not be the sole basis for an investment decision.",
    "RED": "Not fit for this question. Publication is blocked until the named "
           "remediation lands.",
}


def _cohort_sufficiency(wh, metric_id, cohort_spec, n):
    """Score how well this specific cohort supports this specific metric."""
    m = sl.metric(metric_id)
    floor = MIN_VIABLE_N.get(m["grain"], 100)
    notes = []
    if n is None or n < privacy.MIN_CELL:
        return 0.0, [f"denominator of {n} is below the minimum cell size "
                     f"({privacy.MIN_CELL}); the result cannot be released"], True
    if n < floor:
        score = 100.0 * n / floor
        notes.append(f"denominator of {n:,} is below the {floor:,} needed for a "
                     f"stable {m['grain']} estimate; the confidence interval will "
                     f"be too wide to separate this from the comparator")
    else:
        score = 100.0
    # A narrow cohort inherits the representativeness problem of its source.
    if cohort_spec.filters.get("rurality") == ["rural"]:
        score = min(score, 70.0)
        notes.append("rural-only cohorts inherit the registry under-coverage "
                     "documented in DQ-08; claims-derived metrics are safer here "
                     "than registry-derived ones")
    return score, notes, False


def _governance(wh, metric_id, dq_results):
    m = sl.metric(metric_id)
    notes, blocked = [], False
    rows, _ = wh.query("SELECT source_id, license_expiry, consent_basis, "
                       "publication_lag_days FROM source_metadata")
    by_id = {r["source_id"]: r for r in rows}
    score = 100.0
    for sid in m["required_sources"]:
        src = by_id.get(sid)
        if not src:
            notes.append(f"required source {sid} is not registered in the catalogue")
            return 0.0, notes, True
        expiry = datetime.date.fromisoformat(src["license_expiry"])
        days = (expiry - TODAY).days
        if days < 0:
            notes.append(f"licence for {sid} expired on {src['license_expiry']}")
            return 0.0, notes, True
        if days < 90:
            score = min(score, 55.0)
            notes.append(f"licence for {sid} expires in {days} days - renewal must "
                         f"close before this metric can be re-published")
    required = set(m["required_sources"])
    for r in dq_results:
        if r["dimension"] != "governance" or r["status"] != "FAIL":
            continue
        affected = set(TABLE_SOURCES.get(r["table"], []))
        if "*" not in affected and not (affected & required):
            continue          # the failure sits in a source this metric never reads
        notes.append(f"{r['check_id']}: {r['description']} "
                     f"({r['rows_affected']} rows)")
        if r["severity"] == "critical":
            blocked = True
            score = 0.0
        else:
            score = min(score, 40.0)
    return score, notes, blocked


def assess(wh, metric_id, cohort_spec=None, dq_results=None, n=None):
    """Score one business question. Returns a JSON-serialisable verdict."""
    cohort_spec = cohort_spec or co.ALL_PATIENTS
    dq_results = dq_results if dq_results is not None else dqmod.run_all(wh)
    m = sl.metric(metric_id)
    dims = dqmod.dimension_scores(dq_results)
    by_check = {r["check_id"]: r for r in dq_results}

    if n is None:
        n = cohort_spec.size(wh)

    # ---- 1. asset quality, restricted to the dimensions this metric uses ---
    contributions, vetoed, veto_reasons = [], False, []
    for d in m["critical_dq"]:
        info = dims.get(d)
        if not info:
            continue
        contributions.append(info)
        if info["score"] < 25:
            vetoed = True
            veto_reasons.append(
                f"V1 - {d} scores {info['score']:.0f}/100, driven by "
                f"{info['driver']} ({info['driver_description']})")
    asset = (sum(c["score"] for c in contributions) / len(contributions)
             if contributions else 100.0)

    # ---- 2. cohort sufficiency --------------------------------------------
    coh_score, coh_notes, coh_block = _cohort_sufficiency(wh, metric_id, cohort_spec, n)
    if coh_block:
        vetoed = True
        veto_reasons.append("V3 - " + coh_notes[0])

    # ---- 3. governance -----------------------------------------------------
    gov_score, gov_notes, gov_block = _governance(wh, metric_id, dq_results)
    if gov_block:
        vetoed = True
        veto_reasons.append("V2/V4 - " + (gov_notes[0] if gov_notes else "governance failure"))

    total = round(W_ASSET * asset + W_COHORT * coh_score + W_GOV * gov_score, 1)
    verdict = band(total, vetoed)

    # ---- the two weakest dimensions, with their remediation ---------------
    drivers = []
    for info in sorted(contributions, key=lambda c: c["score"])[:2]:
        chk = by_check.get(info["driver"], {})
        drivers.append({
            "dimension": info["dimension"], "score": info["score"],
            "check_id": info["driver"], "issue": info["driver_description"],
            "observed": f"{chk.get('value')} {chk.get('unit', '')}".strip(),
            "business_impact": chk.get("business_impact"),
            "remediation": chk.get("remediation"), "owner": chk.get("owner"),
        })

    return {
        "metric_id": metric_id,
        "metric_label": m["label"],
        "cohort_hash": cohort_spec.hash(),
        "cohort": cohort_spec.describe(),
        "n": n,
        "ffu_score": total,
        "band": verdict,
        "permitted_use": PERMITTED_USE[verdict],
        "blocked": verdict == "RED",
        "components": {
            "asset_quality": round(asset, 1),
            "cohort_sufficiency": round(coh_score, 1),
            "governance": round(gov_score, 1),
        },
        "dimensions_assessed": [c["dimension"] for c in contributions],
        "veto_reasons": veto_reasons,
        "notes": coh_notes + gov_notes,
        "top_drivers": drivers,
        "metric_caveat": m["caveat"],
    }


def assess_all(wh, cohort_spec=None, dq_results=None):
    """Score every governed metric against one cohort.

    Cohort sufficiency is judged on each metric's OWN denominator, not on the
    size of the requested cohort. Asking "all patients" for a severe-only
    metric leaves ~7,000 patients in the denominator, not 40,000, and scoring
    it on the larger number would overstate how much evidence is behind it.
    """
    from . import metrics as metmod
    dq_results = dq_results if dq_results is not None else dqmod.run_all(wh)
    cohort_spec = cohort_spec or co.ALL_PATIENTS
    out = []
    for mid in sl.METRICS:
        res = metmod.compute(wh, mid, cohort_spec)
        n = res.denominator if res.denominator is not None else res.n
        out.append(assess(wh, mid, cohort_spec, dq_results, n))
    return out
