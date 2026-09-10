"""
Cohort compiler.

A CohortSpec is a small, declarative, JSON-serialisable object. It is the only
thing the LLM is ever allowed to produce - the agent never writes SQL. That
single constraint is what makes the system safe to point at patient data:

  * no prompt can inject SQL, because no model output reaches the SQL string;
  * every value is a bound parameter;
  * the spec hashes to a stable `cohort_hash`, which becomes the citation that
    travels with every number the product publishes.

If two analysts, six months apart, quote the same cohort_hash, they are
provably talking about the same patients.
"""

import hashlib
import json

from . import semantic_layer as sl

SPEC_VERSION = "1.2.0"

BASE_COLUMNS = [
    "patient_id", "birth_year", "sex", "province", "rurality", "insurance_type",
    "enrollment_start", "enrollment_end", "index_dx_date", "first_symptom_date",
    "severity", "primary_condition",
]


class CohortError(ValueError):
    pass


class CohortSpec:
    """Declarative patient selection.

    filters              dict of dimension -> list of allowed values
    index_from/index_to  inclusive ISO date bounds on index_dx_date
    min_followup_days    require this much enrolment after the index diagnosis
    require_confirmed_dx exclude patients with no confirmed diagnosis date
    label                human-readable name, carried into citations
    """

    def __init__(self, filters=None, index_from=None, index_to=None,
                 min_followup_days=0, require_confirmed_dx=True, label=None):
        self.filters = {}
        for dim, vals in (filters or {}).items():
            if dim not in sl.DIMENSIONS:
                raise CohortError(
                    f"'{dim}' is not a governed dimension. Available: {sorted(sl.DIMENSIONS)}"
                )
            vals = [vals] if isinstance(vals, str) else list(vals)
            allowed = sl.DIMENSIONS[dim]["values"]
            bad = [v for v in vals if v not in allowed]
            if bad:
                raise CohortError(f"value(s) {bad} not valid for dimension '{dim}'. "
                                  f"Allowed: {allowed}")
            self.filters[dim] = sorted(vals)
        self.index_from = index_from
        self.index_to = index_to
        self.min_followup_days = int(min_followup_days or 0)
        self.require_confirmed_dx = bool(require_confirmed_dx)
        self.label = label or self.describe()

    # ---------------------------------------------------------------- spec
    def to_dict(self):
        return {
            "spec_version": SPEC_VERSION,
            "filters": self.filters,
            "index_from": self.index_from,
            "index_to": self.index_to,
            "min_followup_days": self.min_followup_days,
            "require_confirmed_dx": self.require_confirmed_dx,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(filters=d.get("filters"), index_from=d.get("index_from"),
                   index_to=d.get("index_to"),
                   min_followup_days=d.get("min_followup_days", 0),
                   require_confirmed_dx=d.get("require_confirmed_dx", True),
                   label=d.get("label"))

    def hash(self):
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "CH-" + hashlib.sha256(payload.encode()).hexdigest()[:12].upper()

    def describe(self):
        if not self.filters and not self.index_from and not self.index_to:
            parts = ["all patients"]
        else:
            parts = []
            for dim, vals in sorted(self.filters.items()):
                parts.append(f"{dim} = {'/'.join(vals)}")
            if self.index_from:
                parts.append(f"diagnosed on or after {self.index_from}")
            if self.index_to:
                parts.append(f"diagnosed on or before {self.index_to}")
        if self.min_followup_days:
            parts.append(f"{self.min_followup_days}+ days of follow-up")
        return "; ".join(parts)

    def child(self, dim, value):
        """Derive a single-value break-out cohort (used for group-by analysis)."""
        f = dict(self.filters)
        f[dim] = [value]
        return CohortSpec(f, self.index_from, self.index_to,
                          self.min_followup_days, self.require_confirmed_dx)

    # ----------------------------------------------------------------- sql
    def compile(self):
        """Return (sql, params). No user value is ever interpolated into SQL."""
        selects = list(BASE_COLUMNS)
        for dim, meta in sl.DIMENSIONS.items():
            if meta["type"] == "derived":
                selects.append(f"{meta['expr']} AS {dim}")
        where, params = ["1 = 1"], []

        for dim in sorted(self.filters):
            vals = self.filters[dim]
            meta = sl.DIMENSIONS[dim]
            expr = meta["expr"] if meta["type"] == "derived" else meta["column"]
            where.append(f"{expr} IN ({','.join('?' * len(vals))})")
            params.extend(vals)

        if self.require_confirmed_dx:
            where.append("index_dx_date IS NOT NULL")
        if self.index_from:
            where.append("index_dx_date >= ?")
            params.append(self.index_from)
        if self.index_to:
            where.append("index_dx_date <= ?")
            params.append(self.index_to)
        if self.min_followup_days:
            where.append("julianday(enrollment_end) - julianday(index_dx_date) >= ?")
            params.append(self.min_followup_days)

        sql = ("SELECT " + ", ".join(selects) + "\n  FROM patient\n WHERE "
               + "\n   AND ".join(where))
        return sql, params

    def size(self, wh):
        sql, params = self.compile()
        return wh.scalar(f"SELECT COUNT(*) FROM ({sql})", params)

    def __repr__(self):
        return f"<CohortSpec {self.hash()} {self.describe()}>"


ALL_PATIENTS = CohortSpec(label="All diagnosed patients")
