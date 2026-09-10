"""
Metric engine.

Takes a governed metric id + a CohortSpec, executes the metric's SQL against
the compiled cohort, applies the privacy policy, and returns a MetricResult
that carries its own citation.

The citation is the point. Every MetricResult knows:
    - which metric definition produced it (metric_id + semantic layer version)
    - which patients it covers (cohort_hash)
    - the exact SQL executed and how long it took
    - the denominator it rests on
so any number that reaches a slide can be re-executed and re-checked.
"""

import math
import statistics

from . import cohort as co
from . import privacy
from . import semantic_layer as sl


def wilson_ci(k, n, z=1.96):
    """95% Wilson score interval - stable at the small denominators that
    break the normal approximation, which is most break-out cells.

    Returns (None, None) when the figure is not a genuine proportion. A count
    of events over a count of patients (ED visits per 100 patients) can exceed
    1 and a binomial interval would be nonsense there; reporting no interval is
    correct, inventing one is not.
    """
    if not n or k is None or k < 0 or k > n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


class MetricResult:
    def __init__(self, metric_id, cohort_spec, **kw):
        m = sl.metric(metric_id)
        self.metric_id = metric_id
        self.label = m["label"]
        self.grain = m["grain"]
        self.unit = m["unit"]
        self.caveat = m["caveat"]
        self.owner = m["owner"]
        self.cohort_label = cohort_spec.describe()
        self.cohort_hash = cohort_spec.hash()
        self.value = kw.get("value")
        self.n = kw.get("n")
        self.numerator = kw.get("numerator")
        self.denominator = kw.get("denominator")
        self.ci = kw.get("ci", (None, None))
        self.spread = kw.get("spread")            # (q1, median, q3) for distributions
        self.series = kw.get("series")            # [{period, value, n}, ...]
        self.categories = kw.get("categories")    # [{value, n, pct}, ...]
        self.suppressed = kw.get("suppressed", False)
        self.suppression_reason = kw.get("suppression_reason")
        self.sql = kw.get("sql", "")
        self.exec_ms = kw.get("exec_ms", 0.0)
        self.rows_scanned = kw.get("rows_scanned", 0)

    # ------------------------------------------------------------ display
    def formatted(self):
        if self.suppressed:
            return privacy.SUPPRESSED
        if self.value is None:
            return "n/a"
        if self.unit.startswith("%"):
            return f"{self.value * 100:.1f}%"
        if self.unit == "proportion 0-1":
            return f"{self.value:.2f}"
        if self.unit == "CAD":
            return f"${self.value:,.0f}"
        if self.unit == "days":
            return f"{self.value:,.0f} days"
        return f"{self.value:,.1f}"

    def citation(self):
        return {
            "metric_id": self.metric_id,
            "semantic_layer_version": co.SPEC_VERSION,
            "cohort_hash": self.cohort_hash,
            "cohort": self.cohort_label,
            "denominator": self.denominator if self.denominator is not None else self.n,
            "exec_ms": round(self.exec_ms, 1),
        }

    def to_dict(self):
        d = {k: v for k, v in self.__dict__.items() if k != "sql"}
        d["formatted"] = self.formatted()
        d["citation"] = self.citation()
        return d

    def __repr__(self):
        return f"<{self.metric_id} {self.formatted()} n={self.denominator or self.n}>"


def compute(wh, metric_id, cohort_spec=None, min_cell=privacy.MIN_CELL):
    """Execute one governed metric against one cohort."""
    cohort_spec = cohort_spec or co.ALL_PATIENTS
    m = sl.metric(metric_id)
    csql, cparams = cohort_spec.compile()
    sql = m["sql"].replace("{COHORT}", csql)
    rows, ms = wh.query(sql, cparams)
    base = dict(sql=sql, exec_ms=ms, rows_scanned=len(rows))
    chash = cohort_spec.hash()
    grain = m["grain"]

    if grain == "rate":
        num = rows[0]["numerator"] if rows else 0
        den = rows[0]["denominator"] if rows else 0
        ok, reason = privacy.check_cell(num, den, chash, min_cell)
        if not ok:
            return MetricResult(metric_id, cohort_spec, numerator=num, denominator=den,
                                suppressed=True, suppression_reason=reason, **base)
        scale = m.get("scale", 1.0)
        val = (num / den) * scale if den else None
        # Only a true proportion gets a binomial interval.
        lo, hi = wilson_ci(num, den) if scale == 1.0 else (None, None)
        return MetricResult(metric_id, cohort_spec, value=val, numerator=num,
                            denominator=den, n=den, ci=(lo, hi), **base)

    if grain == "distribution":
        vals = [r["value"] for r in rows if r["value"] is not None]
        ok, reason = privacy.check_cell(None, len(vals), chash, min_cell)
        if not ok:
            return MetricResult(metric_id, cohort_spec, n=len(vals), denominator=len(vals),
                                suppressed=True, suppression_reason=reason, **base)
        vals.sort()
        q1 = vals[int(0.25 * (len(vals) - 1))]
        q3 = vals[int(0.75 * (len(vals) - 1))]
        med = statistics.median(vals)
        return MetricResult(metric_id, cohort_spec, value=med, n=len(vals),
                            denominator=len(vals), spread=(q1, med, q3), **base)

    if grain == "series":
        pts, suppressed_any = [], 0
        for r in rows:
            ok, _ = privacy.check_cell(r["numerator"], r["denominator"], chash, min_cell)
            if not ok:
                suppressed_any += 1
                pts.append({"period": r["period"], "value": None, "n": r["denominator"],
                            "numerator": None, "suppressed": True})
            else:
                pts.append({"period": r["period"],
                            "value": r["numerator"] / r["denominator"] if r["denominator"] else None,
                            "n": r["denominator"], "numerator": r["numerator"],
                            "suppressed": False})
        live = [p for p in pts if not p["suppressed"]]
        total_n = sum(p["n"] or 0 for p in pts)
        return MetricResult(metric_id, cohort_spec,
                            value=live[-1]["value"] if live else None,
                            series=pts, n=total_n, denominator=total_n,
                            suppressed=not live,
                            suppression_reason=("every period is below the minimum cell size"
                                                if not live else None), **base)

    if grain == "category":
        counts = {}
        for r in rows:
            counts[r["value"] or "(none)"] = counts.get(r["value"] or "(none)", 0) + 1
        total = sum(counts.values())
        ok, reason = privacy.check_cell(None, total, chash, min_cell)
        if not ok:
            return MetricResult(metric_id, cohort_spec, n=total, denominator=total,
                                suppressed=True, suppression_reason=reason, **base)
        cats = []
        for v, c in sorted(counts.items(), key=lambda kv: -kv[1]):
            if c < min_cell:
                continue                     # P2 applied per category
            cats.append({"value": v, "n": c, "pct": c / total})
        return MetricResult(metric_id, cohort_spec, value=cats[0]["pct"] if cats else None,
                            categories=cats[:12], n=total, denominator=total, **base)

    raise ValueError(f"unsupported grain '{grain}'")


def compute_by(wh, metric_id, dimension, cohort_spec=None, min_cell=privacy.MIN_CELL):
    """Run a metric once per value of a governed dimension.

    Each break-out gets its own cohort hash, so a cell in a chart is as
    citable as a headline number. Complementary suppression is applied across
    the whole break-out, not per cell.
    """
    cohort_spec = cohort_spec or co.ALL_PATIENTS
    if dimension not in sl.DIMENSIONS:
        raise KeyError(f"'{dimension}' is not a governed dimension")
    out = []
    for value in sl.DIMENSIONS[dimension]["values"]:
        child = cohort_spec.child(dimension, value)
        res = compute(wh, metric_id, child, min_cell)
        out.append({"group": value, "result": res, "n": res.denominator or res.n or 0,
                    "suppressed": res.suppressed, "cohort_hash": res.cohort_hash,
                    "suppression_reason": res.suppression_reason})
    out = [o for o in out if (o["n"] or 0) > 0 or not o["suppressed"]]
    privacy.apply_complementary(out, min_cell)
    for o in out:
        if o["suppressed"] and not o["result"].suppressed:
            o["result"].suppressed = True
            o["result"].suppression_reason = o["suppression_reason"]
    return out
