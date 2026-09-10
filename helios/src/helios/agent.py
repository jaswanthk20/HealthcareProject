"""Answer only from published aggregate cells; no invented observations or figures."""
import re
from . import llm, retrieval

DEFAULTS = {"geography": "Canada (excluding territories)", "age": "Total, 18 years and over", "sex": "Both sexes"}

def ask(payload, question, planner=None):
    refusal = llm.scope_violation(question)
    if refusal:
        return {"status": "refused", "text": "Individual targeting and unrelated requests are outside this aggregate public-data product.", "rows": []}
    if re.search(r"rural|urban|payer|insurance|wait time|diagnos.*delay|brand share|cost|prescrib|children|pediatric|paediatric|forecast|predict|causal|cause", question, re.I):
        return {"status": "refused", "text": "This source does not report that measure or population breakdown.", "rows": []}
    plan = (planner or llm.get_planner()).plan(question, retrieval.retrieve(question))
    if plan["intent"] != "metric_query" or plan["validation_errors"]:
        # A fallback warning alone is acceptable; invalid population values are not.
        if plan["intent"] != "metric_query" or any(not e.startswith(("model call failed:", "model endpoint")) for e in plan["validation_errors"]):
            return {"status": "refused", "text": "Choose one supported indicator and a published population.", "rows": []}
    filters = dict(DEFAULTS)
    for dim, values in plan["filters"].items():
        if len(values) != 1:
            return {"status": "refused", "text": "Select one population per dimension, or ask for a provincial comparison.", "rows": []}
        filters[dim] = values[0]
    years = re.findall(r"\b20\d{2}\b", question)
    if len(set(years)) > 1:
        return {"status": "refused", "text": "Use the dashboard trend for multiple years.", "rows": []}
    year = years[0] if years else payload["source"]["latest_year"]
    breakdown = plan.get("breakdown")
    rows = [r for r in payload["rows"] if r["indicator"] == plan["metric_id"] and r["year"] == year
            and all(dim == breakdown or r[dim] == value for dim, value in filters.items())]
    if not rows:
        return {"status": "unavailable", "text": "No published cells match this selection.", "rows": []}
    lines = [payload["indicators"][plan["metric_id"]] + " (" + year + ")"]
    for row in rows:
        prefix = f"{row['geography']}; {row['age']}; {row['sex']}"
        if row["value"] is None:
            lines.append(prefix + ": unavailable (" + (payload["flags"].get(row["value_status"]) if row["value_status"] else "Not available") + ").")
        else:
            interval = f"; 95% CI {row['low']}–{row['high']}%" if row["low"] is not None and row["high"] is not None else "; interval unavailable"
            lines.append(prefix + f": {row['value']}%" + interval + "; " + row["quality"] + ".")
    lines += payload["limitations"]
    lines.append("Source: " + payload["source"]["url"])
    return {"status": "answered", "text": "\n".join(lines), "rows": rows, "plan": plan}
