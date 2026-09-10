"""
Data Quality engine.

Structured on the Kahn harmonised DQ terminology (Conformance, Completeness,
Plausibility) extended with the four operational dimensions that actually
decide whether an RWD asset can carry a launch decision: Timeliness, Coverage,
Linkage and Referential Integrity - plus a Governance dimension covering
licence validity and consent.

Each check is a small, named, independently runnable object with:
    dimension     - the FFU dimension it rolls up into
    measure()     - returns the observed value (a rate, a count, a ratio)
    green / red   - thresholds; the score is linear between them
    business_impact / remediation / owner - the BA-authored fields that turn a
                    red number into an actionable backlog item

Scores are 0-100 and roll up per dimension by worst-case, because a single
broken dimension is not averaged away by healthy ones.
"""

import datetime

TODAY = datetime.date(2026, 9, 10)

DIMENSIONS = [
    "completeness_days_supply", "completeness_index_dates", "completeness_clinical",
    "conformance_codes", "plausibility_dates", "plausibility_units",
    "deduplication", "timeliness", "coverage", "linkage_rate",
    "referential_integrity", "representativeness", "governance",
]


class Check:
    def __init__(self, cid, dimension, table, description, sql, green, red,
                 unit, business_impact, remediation, owner, higher_is_better=False,
                 severity="medium"):
        self.id = cid
        self.dimension = dimension
        self.table = table
        self.description = description
        self.sql = sql
        self.green = green
        self.red = red
        self.unit = unit
        self.business_impact = business_impact
        self.remediation = remediation
        self.owner = owner
        self.higher_is_better = higher_is_better
        self.severity = severity

    def score(self, value):
        if value is None:
            return 0.0
        if self.higher_is_better:
            if value >= self.green:
                return 100.0
            if value <= self.red:
                return 0.0
            return 100.0 * (value - self.red) / (self.green - self.red)
        if value <= self.green:
            return 100.0
        if value >= self.red:
            return 0.0
        return 100.0 * (self.red - value) / (self.red - self.green)

    def status(self, score):
        return "PASS" if score >= 80 else ("WARN" if score >= 50 else "FAIL")

    def run(self, wh):
        rows, ms = wh.query(self.sql)
        value = list(rows[0].values())[0] if rows else None
        affected = list(rows[0].values())[1] if rows and len(rows[0]) > 1 else None
        sc = self.score(value)
        return {
            "check_id": self.id, "dimension": self.dimension, "table": self.table,
            "description": self.description, "value": value, "unit": self.unit,
            "rows_affected": affected, "score": round(sc, 1), "status": self.status(sc),
            "green_threshold": self.green, "red_threshold": self.red,
            "severity": self.severity, "business_impact": self.business_impact,
            "remediation": self.remediation, "owner": self.owner,
            "exec_ms": round(ms, 1),
        }


CHECKS = [
    Check("DQ-01", "completeness_days_supply", "claim_pharmacy",
          "Pharmacy claims with a missing or zero days_supply",
          """SELECT ROUND(100.0 * SUM(CASE WHEN days_supply IS NULL OR days_supply = 0
                          THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct,
                    SUM(CASE WHEN days_supply IS NULL OR days_supply = 0 THEN 1 ELSE 0 END) AS n
               FROM claim_pharmacy""",
          green=2.0, red=10.0, unit="% of rows", severity="high",
          business_impact="PDC adherence (M06) treats these rows as zero days of "
                          "coverage, understating adherence and weakening the "
                          "support-programme business case.",
          remediation="Impute days_supply from quantity x standard pack size for "
                      "the 11 highest-volume molecules; escalate the residual to "
                      "the PBM vendor as a contractual data-quality defect.",
          owner="RWD Data Engineering"),

    Check("DQ-02", "plausibility_dates", "claim_medical",
          "Medical claims dated in the future",
          f"""SELECT ROUND(100.0 * SUM(CASE WHEN service_date > '{TODAY.isoformat()}'
                          THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct,
                     SUM(CASE WHEN service_date > '{TODAY.isoformat()}' THEN 1 ELSE 0 END) AS n
                FROM claim_medical""",
          green=0.1, red=5.0, unit="% of rows", severity="high",
          business_impact="Future-dated claims inflate the most recent periods of "
                          "every trend, which is precisely the window launch "
                          "leadership reads first.",
          remediation="Add a hard ingestion reject for service_date > ingest_date "
                      "and quarantine the affected rows for vendor replay.",
          owner="RWD Data Engineering"),

    Check("DQ-03", "plausibility_units", "ehr_encounter",
          "Eosinophil counts implausible for 10^9/L (likely submitted in cells/uL)",
          """SELECT ROUND(100.0 * SUM(CASE WHEN eosinophil_count > 20 THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN eosinophil_count IS NOT NULL THEN 1 ELSE 0 END), 0), 2) AS pct,
                    SUM(CASE WHEN eosinophil_count > 20 THEN 1 ELSE 0 END) AS n
               FROM ehr_encounter""",
          green=0.5, red=8.0, unit="% of non-null labs", severity="high",
          business_impact="Type 2 biomarker phenotyping silently mis-classifies "
                          "these patients as eosinophilic, corrupting any "
                          "biomarker-defined sub-cohort.",
          remediation="Apply a UCUM unit-harmonisation rule at ingestion and "
                      "back-convert values above 20 by dividing by 1000.",
          owner="Clinical Data Products"),

    Check("DQ-04", "completeness_clinical", "ehr_encounter",
          "Encounters for dermatology patients with no EASI severity score",
          """SELECT ROUND(100.0 * SUM(CASE WHEN e.easi_score IS NULL THEN 1 ELSE 0 END)
                    / COUNT(*), 2) AS pct,
                    SUM(CASE WHEN e.easi_score IS NULL THEN 1 ELSE 0 END) AS n
               FROM ehr_encounter e JOIN patient p ON p.patient_id = e.patient_id
              WHERE p.primary_condition IN ('atopic_dermatitis', 'both')""",
          green=20.0, red=60.0, unit="% of encounters", severity="medium",
          business_impact="Severity-stratified effectiveness analyses can only be "
                          "run on the minority of encounters that carry a score, "
                          "and that minority skews to specialist care.",
          remediation="Negotiate structured EASI capture in the next EHR network "
                      "contract cycle; in the interim derive proxy severity from "
                      "treatment intensity and document the proxy in the dictionary.",
          owner="Clinical Data Products"),

    Check("DQ-05", "timeliness", "source_metadata",
          "Worst publication lag across contracted sources against the 30-day SLA",
          """SELECT MAX(publication_lag_days) AS worst_lag,
                    (SELECT COUNT(*) FROM source_metadata WHERE publication_lag_days > 30) AS n
               FROM source_metadata""",
          green=30.0, red=75.0, unit="days", severity="high",
          business_impact="Any metric that depends on the QC provincial feed is "
                          "structurally two months stale, so QC cannot be compared "
                          "like-for-like against other provinces in a monthly review.",
          remediation="Either re-contract for a 30-day feed or publish QC on a "
                      "separate, explicitly lagged panel. Do not blend silently.",
          owner="RWD Data Sourcing & Contracts"),

    Check("DQ-06", "deduplication", "claim_medical",
          "Exact duplicate medical claim rows",
          """SELECT ROUND(100.0 * (COUNT(*) - COUNT(DISTINCT claim_id)) / COUNT(*), 2) AS pct,
                    COUNT(*) - COUNT(DISTINCT claim_id) AS n
               FROM claim_medical""",
          green=0.1, red=3.0, unit="% of rows", severity="high",
          business_impact="Duplicates inflate utilisation and cost metrics (M08, "
                          "M11), which are the two numbers the payer dossier rests on.",
          remediation="Add a deterministic dedupe on the natural key "
                      "(patient_id, service_date, proc_code, paid_amount) in the "
                      "silver layer, and assert uniqueness in the pipeline tests.",
          owner="RWD Data Engineering"),

    Check("DQ-07", "conformance_codes", "patient",
          "Patient rows whose source-native sex coding is outside the M/F/U value set",
          """SELECT ROUND(100.0 * SUM(CASE WHEN sex_raw NOT IN ('M','F','U')
                          THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct,
                    SUM(CASE WHEN sex_raw NOT IN ('M','F','U') THEN 1 ELSE 0 END) AS n
               FROM patient""",
          green=0.5, red=30.0, unit="% of rows", severity="medium",
          business_impact="Any analyst who reaches for sex_raw instead of the "
                          "harmonised sex column silently drops or mis-buckets "
                          "every patient sourced from the QC provincial feed.",
          remediation="Harmonisation already exists in the `sex` column. Revoke "
                      "read access to sex_raw outside the engineering role and "
                      "mark it deprecated in the data dictionary.",
          owner="RWD Data Engineering"),

    Check("DQ-08", "representativeness", "registry_enrollment",
          "Registry rural share relative to the rural share of the patient spine",
          """SELECT ROUND(
                (SELECT 1.0 * SUM(CASE WHEN p.rurality='rural' THEN 1 ELSE 0 END)/COUNT(*)
                   FROM registry_enrollment r JOIN patient p ON p.patient_id=r.patient_id)
                /
                (SELECT 1.0 * SUM(CASE WHEN rurality='rural' THEN 1 ELSE 0 END)/COUNT(*)
                   FROM patient), 3) AS ratio,
                (SELECT COUNT(*) FROM registry_enrollment) AS n""",
          green=0.85, red=0.45, unit="ratio vs spine", higher_is_better=True,
          severity="high",
          business_impact="The registry systematically under-represents rural "
                          "patients. Any PRO or quality-of-life finding drawn from "
                          "it describes urban patients and must not be generalised.",
          remediation="Either weight registry analyses to the claims spine by "
                      "rurality and severity, or restrict registry-derived claims "
                      "to urban populations in the label. Weighting is preferred.",
          owner="Medical Affairs / Registry Operations"),

    Check("DQ-09", "plausibility_dates", "claim_medical",
          "Claims dated before the patient's year of birth",
          """SELECT ROUND(100.0 * SUM(CASE WHEN CAST(substr(m.service_date,1,4) AS INT)
                          < p.birth_year THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct,
                    SUM(CASE WHEN CAST(substr(m.service_date,1,4) AS INT)
                          < p.birth_year THEN 1 ELSE 0 END) AS n
               FROM claim_medical m JOIN patient p ON p.patient_id = m.patient_id""",
          green=0.05, red=2.0, unit="% of rows", severity="medium",
          business_impact="A temporally impossible record anywhere in the asset "
                          "undermines confidence in every date-based metric, which "
                          "is most of the product.",
          remediation="Add a cross-entity plausibility assertion "
                      "(service_date >= date_of_birth) to the pipeline test suite.",
          owner="RWD Data Engineering"),

    Check("DQ-10", "referential_integrity", "claim_medical",
          "Claims referencing a provider_id absent from the provider dimension",
          """SELECT ROUND(100.0 * SUM(CASE WHEN pr.provider_id IS NULL THEN 1 ELSE 0 END)
                    / COUNT(*), 2) AS pct,
                    SUM(CASE WHEN pr.provider_id IS NULL THEN 1 ELSE 0 END) AS n
               FROM claim_medical m LEFT JOIN provider pr ON pr.provider_id = m.provider_id""",
          green=0.5, red=8.0, unit="% of rows", severity="medium",
          business_impact="Specialty-based analyses (M07, field targeting) silently "
                          "drop these claims, biasing specialist involvement downward.",
          remediation="Backfill the provider dimension from the full national "
                      "registry rather than the active-prescriber subset.",
          owner="RWD Data Engineering"),

    Check("DQ-11", "linkage_rate", "patient",
          "Patients on the spine linkable to at least one pharmacy claim",
          """SELECT ROUND(100.0 * (SELECT COUNT(DISTINCT patient_id) FROM claim_pharmacy)
                    / (SELECT COUNT(*) FROM patient), 2) AS pct,
                    (SELECT COUNT(*) FROM patient) AS n""",
          green=90.0, red=60.0, unit="% of patients", higher_is_better=True,
          severity="high",
          business_impact="Unlinked patients cannot contribute to any treatment "
                          "metric, so every therapy denominator is smaller than the "
                          "epidemiological population it appears to describe.",
          remediation="Review the deterministic linkage key and add a probabilistic "
                      "fallback; report the linkage rate alongside every denominator.",
          owner="RWD Data Engineering"),

    Check("DQ-12", "coverage", "ehr_encounter",
          "Patients on the spine with any EHR encounter",
          """SELECT ROUND(100.0 * (SELECT COUNT(DISTINCT patient_id) FROM ehr_encounter)
                    / (SELECT COUNT(*) FROM patient), 2) AS pct,
                    (SELECT COUNT(DISTINCT patient_id) FROM ehr_encounter) AS n""",
          green=60.0, red=20.0, unit="% of patients", higher_is_better=True,
          severity="medium",
          business_impact="Clinical detail exists for a minority of the spine. Any "
                          "metric requiring labs or severity scores runs on a "
                          "subset that is not representative of the whole.",
          remediation="Expand the EHR network contract, and always report "
                      "EHR-derived metrics with their own coverage denominator.",
          owner="Clinical Data Products"),

    Check("DQ-13", "governance", "source_metadata",
          "Contracted sources whose licence expires within 90 days",
          f"""SELECT COUNT(*) AS n_expiring, COUNT(*) AS n
                FROM source_metadata
               WHERE license_expiry <= '{(TODAY + datetime.timedelta(days=90)).isoformat()}'""",
          green=0, red=2, unit="sources", severity="high",
          business_impact="An insight published from an asset whose licence has "
                          "lapsed is a contractual breach, and the insight has to "
                          "be withdrawn from every downstream deck.",
          remediation="Trigger the renewal workflow 120 days out; block publication "
                      "from any source inside 30 days of expiry.",
          owner="RWD Data Sourcing & Contracts"),

    Check("DQ-14", "completeness_index_dates", "patient",
          "Patients missing a confirmed diagnosis date or a first symptom date",
          """SELECT ROUND(100.0 * SUM(CASE WHEN index_dx_date IS NULL
                          OR first_symptom_date IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct,
                    SUM(CASE WHEN index_dx_date IS NULL OR first_symptom_date IS NULL
                          THEN 1 ELSE 0 END) AS n
               FROM patient""",
          green=2.0, red=15.0, unit="% of patients", severity="high",
          business_impact="Time-to-event metrics (M01, M02) silently exclude these "
                          "patients, and the exclusion is not random.",
          remediation="Extend the index-date algorithm to fall back to the earliest "
                      "condition-specific claim when no confirmed code is present.",
          owner="RWD Data Engineering"),

    Check("DQ-15", "governance", "registry_enrollment",
          "Registry rows retained despite withdrawn consent",
          """SELECT SUM(CASE WHEN consent_flag = 0 THEN 1 ELSE 0 END) AS n_withdrawn,
                    SUM(CASE WHEN consent_flag = 0 THEN 1 ELSE 0 END) AS n
               FROM registry_enrollment""",
          green=0, red=1, unit="rows", severity="critical",
          business_impact="Processing data for a patient who has withdrawn consent "
                          "is a privacy incident, reportable regardless of whether "
                          "the row ever reached a report.",
          remediation="Add a consent-withdrawal purge job on the registry refresh "
                      "and enforce consent_flag = 1 in the cohort layer.",
          owner="Privacy Office / Registry Operations"),
]


def run_all(wh):
    return [c.run(wh) for c in CHECKS]


def dimension_scores(results):
    """Roll up to one score per dimension using worst-case, not average."""
    out = {}
    for r in results:
        d = r["dimension"]
        if d not in out or r["score"] < out[d]["score"]:
            out[d] = {"dimension": d, "score": r["score"], "status": r["status"],
                      "driver": r["check_id"], "driver_description": r["description"]}
    return out


def overall(results):
    dims = dimension_scores(results)
    if not dims:
        return 0.0
    return round(sum(d["score"] for d in dims.values()) / len(dims), 1)


def failing(results, level=("FAIL", "WARN")):
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted([r for r in results if r["status"] in level],
                  key=lambda r: (order.get(r["severity"], 9), r["score"]))
