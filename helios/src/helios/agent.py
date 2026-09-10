"""
The HELIOS insight agent.

Pipeline, in order, with a gate at every step that can stop the answer:

    retrieve  -> the governed slice of the semantic layer
    plan      -> {metric, cohort, breakdown}; refuses if nothing governed fits
    compile   -> parameterised SQL; the plan never contains SQL
    execute   -> with small-cell suppression applied inside the metric engine
    gate      -> Fitness-for-Use for THIS metric on THIS cohort
    narrate   -> a grounded answer assembled from executed values only
    scrub     -> identifier redaction on the finished text
    verify    -> every number re-checked against the executed results
    log       -> telemetry with the cohort hash for audit

An answer only reaches the user if it survives all of them. Refusal is a
first-class outcome, not an error path: "the data cannot support this question
yet, here is what would have to change" is the answer that protects a launch
decision.
"""

import time

from . import cohort as co
from . import dq as dqmod
from . import ffu as ffumod
from . import llm
from . import metrics
from . import privacy
from . import retrieval
from . import telemetry as tel
from . import verifier


class Answer:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def to_dict(self):
        d = dict(self.__dict__)
        d["results"] = [r.to_dict() for r in getattr(self, "results", [])]
        return d

    def render(self, width=78):
        L = ["=" * width, f"Q: {self.question}", "=" * width, ""]
        L.append(self.narrative)
        L.append("")
        if self.status == "answered":
            L.append(f"Fitness-for-Use: {self.ffu['band']} "
                     f"({self.ffu['ffu_score']}/100) - {self.ffu['permitted_use']}")
            L.append("")
            L.append("Citations:")
            for c in self.citations:
                L.append(f"  [{c['metric_id']} @ {c['cohort_hash']}] "
                         f"n={c['denominator']:,} | {c['cohort']}")
            L.append("")
            L.append(f"Verification: {self.verification['verified_claims']}"
                     f"/{self.verification['total_claims']} numeric claims traced "
                     f"to executed queries (groundedness "
                     f"{self.verification['groundedness']:.2f})")
        L.append(f"Latency: {self.timings['total']:.0f} ms "
                 f"(plan {self.timings['plan']:.0f}, query {self.timings['query']:.0f}, "
                 f"gate {self.timings['ffu']:.0f}, verify {self.timings['verify']:.0f})")
        return "\n".join(L)


def _fmt_group_line(group, res):
    if res.suppressed:
        return f"  - {group}: {privacy.SUPPRESSED} ({res.suppression_reason})"
    ci = ""
    if res.ci and res.ci[0] is not None and res.grain == "rate":
        lo, hi = res.ci
        scale = 100 if res.unit.startswith("%") else 1
        ci = f" [95% CI {lo * scale:.1f}-{hi * scale:.1f}]"
    n = res.denominator or res.n or 0
    return f"  - {group}: {res.formatted()}{ci} (n={n:,})"


def _narrate(question, primary, breakdown_rows, ffu_verdict, plan):
    """Assemble prose strictly from values that were executed and returned.

    Returns (text, derived) where `derived` lists every number the narrator
    computed rather than read straight off a MetricResult - today only ratios
    between two executed values. Declaring them keeps the verifier strict:
    it never has to guess whether an unfamiliar number was legitimate.
    """
    m_label = primary.label
    parts, derived = [], []

    if primary.suppressed:
        parts.append(
            f"{m_label} cannot be reported for this cohort. "
            f"{primary.suppression_reason.capitalize()}. The privacy policy "
            f"suppresses the cell rather than releasing it.")
    else:
        headline = primary.formatted()
        n = primary.denominator or primary.n or 0
        if primary.grain == "distribution":
            q1, med, q3 = primary.spread
            unit = "" if primary.unit == "CAD" else f" {primary.unit}"
            parts.append(
                f"Across {n:,} patients, the median {m_label.lower()} is "
                f"{headline}, with an interquartile range of {q1:,.0f} to "
                f"{q3:,.0f}{unit}.")
        elif primary.grain == "rate":
            lo, hi = primary.ci
            scale = 100 if primary.unit.startswith("%") else 1
            ci_txt = (f" (95% CI {lo * scale:.1f} to {hi * scale:.1f})"
                      if lo is not None else "")
            parts.append(
                f"{m_label} is {headline}{ci_txt}, based on {primary.numerator:,} "
                f"of {primary.denominator:,} patients.")
        elif primary.grain == "series":
            live = [p for p in primary.series if not p["suppressed"]]
            if live:
                first, last = live[0], live[-1]
                parts.append(
                    f"{m_label} reached {last['value'] * 100:.1f}% in "
                    f"{last['period']}, up from {first['value'] * 100:.1f}% in "
                    f"{first['period']}. The series covers {len(primary.series)} "
                    f"periods and {primary.n:,} new starts in total.")
                supp = len(primary.series) - len(live)
                if supp:
                    parts.append(
                        f"{supp} of the {len(primary.series)} periods are "
                        f"suppressed because the monthly count of new starts "
                        f"falls below the minimum cell size.")
        elif primary.grain == "category":
            top = primary.categories[:3]
            listed = "; ".join(f"{c['value']} ({c['pct'] * 100:.1f}%, n={c['n']:,})"
                               for c in top)
            parts.append(f"The most common patterns across {n:,} patients are: {listed}.")

    if breakdown_rows:
        dim = plan["breakdown"]
        parts.append(f"\nBroken out by {dim.replace('_', ' ')}:")
        for row in breakdown_rows:
            parts.append(_fmt_group_line(row["group"], row["result"]))
        live = [r for r in breakdown_rows if not r["result"].suppressed
                and r["result"].value is not None]
        if len(live) >= 2:
            hi = max(live, key=lambda r: r["result"].value)
            lo = min(live, key=lambda r: r["result"].value)
            if hi["group"] != lo["group"]:
                h, l = hi["result"], lo["result"]
                if l.value:
                    ratio = h.value / l.value
                    derived.append(ratio)
                    parts.append(
                        f"\nThe spread is material: {hi['group']} at "
                        f"{h.formatted()} against {lo['group']} at "
                        f"{l.formatted()}, a ratio of {ratio:.2f}x.")

    parts.append(f"\nHow to read this: {ffu_verdict['permitted_use']}")
    parts.append(f"Caveat carried by this metric: {primary.caveat}")
    return "\n".join(parts), derived


def _refusal_text(reason, detail, remediation=None):
    out = [f"HELIOS cannot answer this question. {reason}", "", detail]
    if remediation:
        out += ["", f"What would have to change: {remediation}"]
    return "\n".join(out)


class InsightAgent:
    def __init__(self, wh, planner=None, telemetry=None, dq_results=None):
        self.wh = wh
        self.planner = planner or llm.get_planner()
        self.tel = telemetry
        self.dq_results = dq_results if dq_results is not None else dqmod.run_all(wh)

    def ask(self, question):
        t_start = time.perf_counter()
        timings = {k: 0.0 for k in
                   ("retrieval", "plan", "query", "ffu", "narrate", "verify", "total")}
        q0 = self.wh.stats["queries"]
        r0 = self.wh.stats["rows"]

        t = time.perf_counter()
        hits = retrieval.retrieve(question, k=6)
        timings["retrieval"] = (time.perf_counter() - t) * 1000

        # Gate 0: categorical scope. Runs before any planner sees the question,
        # so an individual-level ask is refused whether the planner is the rule
        # engine or the model.
        t = time.perf_counter()
        violation = llm.scope_violation(question)
        if violation:
            plan = llm.Plan.validate(
                {"intent": "out_of_scope", "metric_id": None, "filters": {},
                 "breakdown": None, "reasoning": violation},
                "scope-guard", (time.perf_counter() - t) * 1000)
        else:
            plan = self.planner.plan(question, hits)
        timings["plan"] = (time.perf_counter() - t) * 1000

        def finish(ans):
            timings["total"] = (time.perf_counter() - t_start) * 1000
            ans.timings = timings
            ans.plan = plan
            ans.retrieved = [{"doc_id": h["doc"]["doc_id"], "kind": h["doc"]["kind"],
                              "score": h["score"], "matched": h["matched_terms"]}
                             for h in hits]
            if self.tel:
                v = getattr(ans, "verification", {}) or {}
                f = getattr(ans, "ffu", {}) or {}
                self.tel.record({
                    "question": question, "planner": plan["planner"],
                    "intent": plan["intent"], "metric_id": plan.get("metric_id"),
                    "cohort_hash": getattr(ans, "cohort_hash", None),
                    "breakdown": plan.get("breakdown"),
                    "ffu_score": f.get("ffu_score"), "ffu_band": f.get("band"),
                    "blocked": 1 if ans.status != "answered" else 0,
                    "block_reason": getattr(ans, "block_reason", None),
                    "suppressed": 1 if getattr(ans, "suppressed", False) else 0,
                    "numeric_claims": v.get("total_claims"),
                    "verified_claims": v.get("verified_claims"),
                    "groundedness": v.get("groundedness"),
                    "ms_retrieval": timings["retrieval"], "ms_plan": timings["plan"],
                    "ms_query": timings["query"], "ms_ffu": timings["ffu"],
                    "ms_narrate": timings["narrate"], "ms_verify": timings["verify"],
                    "ms_total": timings["total"],
                    "sql_queries": self.wh.stats["queries"] - q0,
                    "rows_scanned": self.wh.stats["rows"] - r0,
                    "input_tokens": plan.get("usage", {}).get("input_tokens"),
                    "output_tokens": plan.get("usage", {}).get("output_tokens"),
                    "validation_errors": plan.get("validation_errors"),
                })
            return ans

        # ---- gate 1: did the question bind to anything governed? ----------
        if plan["intent"] != "metric_query":
            reason = ("No governed metric covers it."
                      if plan["intent"] == "out_of_scope"
                      else "The question is ambiguous between several metrics.")
            return finish(Answer(
                question=question, status="refused_out_of_scope",
                block_reason=plan["intent"],
                narrative=_refusal_text(
                    reason, plan["reasoning"],
                    "Register the question with the RWD & HI product owner. If it "
                    "is a recurring decision need, it becomes a new governed "
                    "metric with a definition, an owner and a DQ profile."),
                results=[], citations=[], ffu={}, verification={}))

        metric_id = plan["metric_id"]
        spec = plan.to_cohort()

        # ---- execute ------------------------------------------------------
        t = time.perf_counter()
        primary = metrics.compute(self.wh, metric_id, spec)
        breakdown_rows = []
        if plan["breakdown"]:
            breakdown_rows = metrics.compute_by(self.wh, metric_id,
                                                plan["breakdown"], spec)
        timings["query"] = (time.perf_counter() - t) * 1000

        # ---- gate 2: fitness for use, scored on the real denominator ------
        t = time.perf_counter()
        verdict = ffumod.assess(self.wh, metric_id, spec, self.dq_results,
                                n=primary.denominator or primary.n)
        timings["ffu"] = (time.perf_counter() - t) * 1000

        if verdict["blocked"]:
            rem = (verdict["top_drivers"][0]["remediation"]
                   if verdict["top_drivers"] else None)
            detail = "\n".join(
                [f"Fitness-for-Use score {verdict['ffu_score']}/100 (RED) for "
                 f"{verdict['metric_label']} on this cohort.", ""]
                + [f"  - {r}" for r in verdict["veto_reasons"]])
            return finish(Answer(
                question=question, status="refused_not_fit",
                block_reason="ffu_red", cohort_hash=spec.hash(),
                narrative=_refusal_text(
                    "The data is not fit for this particular question.", detail, rem),
                results=[primary], citations=[primary.citation()],
                ffu=verdict, verification={},
                suppressed=primary.suppressed))

        # ---- narrate, scrub, verify ---------------------------------------
        t = time.perf_counter()
        text, derived = _narrate(question, primary, breakdown_rows, verdict, plan)
        text = privacy.scrub(text, spec.hash())
        timings["narrate"] = (time.perf_counter() - t) * 1000

        all_results = [primary] + [r["result"] for r in breakdown_rows]
        series = primary.series or []
        extra = [
            verdict["ffu_score"],                                  # quoted FFU score
            verdict["n"] or 0,                                     # gated denominator
            len(breakdown_rows),                                   # groups shown
            len(series),                                           # periods in series
            sum(1 for p in series if p["suppressed"]),             # periods suppressed
            privacy.MIN_CELL,                                      # policy constant
        ] + derived                                                # declared ratios

        # Everything the narrator quoted verbatim from the semantic layer.
        # Break-out group labels belong here too: an age band printed as
        # "40-64" is a governed dimension VALUE, not an assertion about the
        # data, and the golden set caught the verifier flagging it as one.
        static_text = [verdict["permitted_use"], primary.caveat, primary.label,
                       primary.unit, plan["breakdown"] or ""]
        for r in all_results:
            static_text += [r.label, r.unit, r.suppression_reason or "",
                            r.cohort_label]
        for row in breakdown_rows:
            static_text.append(str(row["group"]))
        for c in (primary.categories or []):
            static_text.append(str(c["value"]))

        t = time.perf_counter()
        ver = verifier.verify(text, all_results, extra_allowed=extra,
                              static_text=static_text)
        timings["verify"] = (time.perf_counter() - t) * 1000

        if not ver["passed"]:
            bad = ", ".join(v["text"] for v in ver["violations"][:5])
            return finish(Answer(
                question=question, status="blocked_unverified",
                block_reason="numeric_verification_failed", cohort_hash=spec.hash(),
                narrative=_refusal_text(
                    "The generated answer contained numbers that could not be "
                    "traced to an executed query, so it was blocked before display.",
                    f"Unverified value(s): {bad}",
                    "This is the hallucination gate doing its job. The event is "
                    "logged with the cohort hash for review by the product owner."),
                results=all_results, citations=[r.citation() for r in all_results],
                ffu=verdict, verification=ver, suppressed=primary.suppressed))

        return finish(Answer(
            question=question, status="answered", narrative=text,
            cohort_hash=spec.hash(), results=all_results,
            citations=[r.citation() for r in all_results],
            ffu=verdict, verification=ver, suppressed=primary.suppressed,
            breakdown_rows=[{"group": r["group"], "result": r["result"].to_dict()}
                            for r in breakdown_rows]))


def build(db_path="data/helios.db", planner=None, telemetry_path=None):
    from .db import Warehouse
    wh = Warehouse(db_path)
    t = tel.Telemetry(telemetry_path) if telemetry_path else None
    return InsightAgent(wh, planner=planner, telemetry=t)
