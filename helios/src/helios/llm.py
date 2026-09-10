"""Select governed public health indicators and published population dimensions.

The deterministic planner uses a controlled vocabulary. The optional model
endpoint returns the same validated plan and falls back when unavailable.
Neither planner produces observations, percentages or confidence intervals.
"""

import json
import os
import time
import urllib.request

from . import cohort as co
from . import retrieval
from . import semantic_layer as sl


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["metric_query", "out_of_scope", "needs_clarification"],
            "description": "metric_query when a governed metric answers the "
                           "question; out_of_scope when the product holds no "
                           "such metric; needs_clarification when the question "
                           "is too vague to bind to one metric.",
        },
        "metric_id": {
            "type": ["string", "null"],
            "enum": sorted(sl.METRICS) + [None],
            "description": "The governed metric that answers the question.",
        },
        "filters": {
            "type": "object",
            "description": "Cohort filters, keyed by governed dimension name; "
                           "each value is a list of allowed dimension values.",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
        },
        "breakdown": {
            "type": ["string", "null"],
            "enum": sorted(sl.DIMENSIONS) + [None],
            "description": "Dimension to break the result out by, if the user "
                           "asked for a comparison.",
        },
        "reasoning": {
            "type": "string",
            "description": "One sentence on why this metric answers the question.",
        },
    },
    "required": ["intent", "metric_id", "filters", "breakdown", "reasoning"],
    "additionalProperties": False,
}

SYSTEM = """You are the planning component of HELIOS, a real-world-data \
dashboard of official public population-health statistics.

Your ONLY job is to translate a business question into a plan that selects one \
governed metric and one cohort. You never write SQL, never invent a metric, \
and never estimate a number yourself.

Rules:
1. metric_id MUST be one of the governed metric ids provided in the context. \
If no governed metric answers the question, set intent to "out_of_scope" and \
metric_id to null. Refusing is a correct answer and is preferred over \
stretching an unrelated metric to fit.
2. filters may only use the governed dimensions and their exact listed values.
3. Set breakdown only when the user asked for a comparison across a dimension \
("by province", "rural versus urban", "which payer channel").
4. If the question could plausibly bind to two very different metrics, set \
intent to "needs_clarification".
5. Never infer a patient-level or prescriber-level answer. This product \
reports on populations only."""


# --------------------------------------------------------------------------
# Scope guard.
#
# Applied BEFORE planning, so it protects every planner including the model.
# HELIOS reports on populations. A question that asks it to single out one
# patient or one prescriber is refused on principle, not because the data
# happens to be thin - re-identification risk and prescriber-privacy rules do
# not become acceptable at a larger denominator.
# --------------------------------------------------------------------------
OUT_OF_SCOPE_PATTERNS = [
    (r"\b(which|what|who|name|identify|list)\b[^?]{0,40}\b"
     r"(doctor|physician|prescriber|gp|specialist|hcp|clinician)\b",
     "This question asks HELIOS to identify an individual prescriber. The "
     "product reports on populations only; prescriber-level targeting is out "
     "of scope for this platform and is governed separately."),
    # Must name an INDIVIDUAL patient. "cost per patient year" is a population
    # measure and has to pass; an earlier, looser version of this pattern
    # refused it, which the golden set caught.
    (r"\b(which|what|whose|name|identify)\s+(single\s+|individual\s+|specific\s+)?"
     r"patient\b(?!s)|\bthe\s+patient\s+(with|who|whose)\b|"
     r"\bshow\s+me\s+the\s+patient\b",
     "This question asks HELIOS to identify an individual patient. Patient-"
     "level output is prohibited: the product releases aggregate figures "
     "subject to the minimum cell size only."),

    (r"\b(write|draft|compose|generate|create|produce)\b[^?]{0,30}\b"
     r"(promotional|marketing|email|letter|press\s+release|social\s+post|"
     r"ad\s+copy|advert|brochure|detail\s+aid)\b",
     "Content generation is outside this product's purpose. HELIOS produces "
     "governed evidence; promotional material runs through medical, legal and "
     "regulatory review in a separate system."),

    (r"\b(share|stock)\s+price\b|\b(revenue|earnings|sales)\s+(forecast|guidance)\b"
     r"|\bmarket\s+cap\b",
     "This is a financial-markets question. HELIOS holds real-world health "
     "data only and has no governed metric that could answer it."),
    (r"\b(top|highest|best|biggest)\s+(prescriber|prescribers|doctor|doctors|"
     r"physician|physicians)\b",
     "Prescriber ranking is out of scope. HELIOS reports population-level "
     "measures; prescriber targeting runs through a separate governed process."),
    (r"\b(re-?identif|deanonymi|de-anonymi|unmask)\w*\b",
     "Re-identification is prohibited under the data-sharing agreements "
     "covering every source in this product."),
    (r"\bpredict\b[^?]{0,30}\b(individual|specific|this)\s+patient\b",
     "Individual patient prediction is a clinical-decision-support use that "
     "sits outside this product's intended use and its regulatory basis."),
]

_COMPILED_SCOPE = [(__import__("re").compile(p, __import__("re").I), msg)
                   for p, msg in OUT_OF_SCOPE_PATTERNS]


def scope_violation(question):
    """Return a refusal reason if the question is categorically out of scope."""
    for pat, msg in _COMPILED_SCOPE:
        if pat.search(question):
            return msg
    return None


def _context_block(hits):
    lines = ["Retrieved from the governed semantic layer:"]
    for h in hits:
        d = h["doc"]
        lines.append(f"- [{d['kind']}] {d['doc_id']}: {d['title']}")
        if d["kind"] == "metric":
            m = sl.METRICS[d["doc_id"]]
            lines.append(f"    definition: {m['definition']}")
            lines.append(f"    supports decision: {m['decision_supported']}")
    lines.append("\nGoverned dimensions and their permitted values:")
    for did, dim in sl.DIMENSIONS.items():
        lines.append(f"- {did}: {', '.join(dim['values'])}")
    return "\n".join(lines)


class Plan(dict):
    """A validated plan. Construction fails loudly on anything ungoverned."""

    @classmethod
    def validate(cls, raw, planner, latency_ms, usage=None):
        intent = raw.get("intent", "needs_clarification")
        mid = raw.get("metric_id")
        errors = []
        if intent == "metric_query":
            if mid not in sl.METRICS:
                errors.append(f"metric_id '{mid}' is not a governed metric")
                intent = "out_of_scope"
        filters = {}
        for dim, vals in (raw.get("filters") or {}).items():
            if dim not in sl.DIMENSIONS:
                errors.append(f"dropped ungoverned filter dimension '{dim}'")
                continue
            allowed = sl.DIMENSIONS[dim]["values"]
            keep = [v for v in (vals if isinstance(vals, list) else [vals]) if v in allowed]
            bad = [v for v in (vals if isinstance(vals, list) else [vals]) if v not in allowed]
            if bad:
                errors.append(f"dropped ungoverned value(s) {bad} for '{dim}'")
            if keep:
                filters[dim] = keep
        bd = raw.get("breakdown")
        if bd is not None and bd not in sl.DIMENSIONS:
            errors.append(f"dropped ungoverned breakdown '{bd}'")
            bd = None
        return cls({
            "intent": intent, "metric_id": mid if intent == "metric_query" else None,
            "filters": filters, "breakdown": bd,
            "reasoning": raw.get("reasoning", ""),
            "planner": planner, "latency_ms": round(latency_ms, 1),
            "validation_errors": errors, "usage": usage or {},
        })

    def to_cohort(self):
        return co.CohortSpec(filters=self["filters"])


class DeterministicPlanner:
    """Controlled vocabulary. No network, no key, fully reproducible."""

    name = "deterministic"

    def plan(self, question, hits=None):
        t0 = time.perf_counter()
        # Resolve the break-out first, then remove that phrase before metric
        # matching: "by province" should choose the VIEW, never the metric.
        breakdown, filters = retrieval.detect_dimension(question)
        match_text = retrieval.strip_breakdown_phrase(question, breakdown)
        mid, score, why, bq_breakdown = retrieval.best_metric(question, match_text)
        breakdown = breakdown or bq_breakdown
        if mid is None:
            raw = {"intent": "out_of_scope", "metric_id": None, "filters": {},
                   "breakdown": None,
                   "reasoning": "No governed metric matched this question "
                                f"(best retrieval score {score:.2f}). HELIOS "
                                "answers only from its governed indicator registry."}
        else:
            raw = {"intent": "metric_query", "metric_id": mid, "filters": filters,
                   "breakdown": breakdown,
                   "reasoning": f"{why}; retrieval score {score:.2f}."}
        return Plan.validate(raw, self.name, (time.perf_counter() - t0) * 1000)


class ModelPlanner:
    """Configurable JSON chat endpoint, with a deterministic fallback."""

    name = "model"

    def __init__(self, model=None, endpoint=None, api_key=None):
        self.model = model or os.environ.get("HELIOS_MODEL")
        self.endpoint = endpoint or os.environ.get("HELIOS_MODEL_ENDPOINT")
        self.api_key = api_key if api_key is not None else os.environ.get("HELIOS_MODEL_API_KEY")
        self.fallback = DeterministicPlanner()

    def plan(self, question, hits=None):
        if not self.model or not self.endpoint:
            p = self.fallback.plan(question, hits)
            p["planner"] = f"{self.name}-unavailable->{self.fallback.name}"
            p["validation_errors"].append("model endpoint or model identifier is not configured")
            return p
        hits = hits if hits is not None else retrieval.retrieve(question, k=6)
        t0 = time.perf_counter()
        try:
            payload = {
                "model": self.model,
                "max_tokens": 2000,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content":
                     f"{_context_block(hits)}\n\nBusiness question: {question}"},
                ],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "governed_plan", "schema": PLAN_SCHEMA,
                }},
            }
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            request = urllib.request.Request(
                self.endpoint, data=json.dumps(payload).encode("utf-8"),
                headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=30) as response:
                resp = json.load(response)
            raw = json.loads(resp["choices"][0]["message"]["content"])
            tokens = resp.get("usage") or {}
            usage = {"input_tokens": tokens.get("prompt_tokens", 0),
                     "output_tokens": tokens.get("completion_tokens", 0)}
            return Plan.validate(raw, self.name, (time.perf_counter() - t0) * 1000, usage)
        except Exception as exc:                       # noqa: BLE001 - degrade, never fail
            p = self.fallback.plan(question, hits)
            p["planner"] = f"{self.name}-error->{self.fallback.name}"
            # Keep endpoint details and credentials out of exported telemetry.
            p["validation_errors"].append(f"model call failed: {type(exc).__name__}")
            return p


def get_planner(name=None):
    name = name or os.environ.get("HELIOS_PLANNER", "deterministic")
    if name == "model":
        return ModelPlanner()
    if name == "deterministic":
        return DeterministicPlanner()
    raise ValueError("planner must be deterministic or model")
