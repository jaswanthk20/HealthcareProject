"""
HELIOS Semantic Layer
=====================
The single governed definition of every metric, dimension and table in the
product. This module is the contract between the business and the platform:

  * The BA writes the `definition`, `decision_supported` and `caveat` fields.
  * The engineer writes the `sql`.
  * The retriever (RAG) indexes these records - so the agent reasons over
    *governed metric definitions*, never over free-text guesses.
  * The data dictionary in docs/ is GENERATED from here, so it can never
    drift from what the product actually computes.

Metric grains
-------------
  distribution : SQL returns one `value` per patient  -> median / IQR / mean
  rate         : SQL returns `numerator`, `denominator` -> proportion + 95% CI
  series       : SQL returns `period`, `numerator`, `denominator` -> trend
  category     : SQL returns one `value` per patient -> frequency table

Every metric SQL contains the token {COHORT}, replaced at compile time by the
cohort SELECT produced by cohort.py. Nothing else is interpolated - all user
values are bound parameters.
"""

# --------------------------------------------------------------------------
# Physical layer: what each table is, who owns it, what it may be used for
# --------------------------------------------------------------------------
TABLES = {
    "patient": {
        "grain": "one row per patient",
        "description": "De-identified patient spine with enrollment window, "
                       "geography, payer type and clinician-assigned severity.",
        "steward": "RWD Data Engineering",
        "pii_class": "de-identified / indirect identifiers present",
        "key_columns": {
            "patient_id": "Surrogate key. Never a real health card number.",
            "birth_year": "Year only - full DOB is suppressed at ingestion.",
            "sex": "Harmonised M/F/U.",
            "sex_raw": "Source-native coding; QC admin source uses 1/2. Do NOT "
                       "use for analysis - demonstrates the conformance defect.",
            "province": "Two-letter province code; TERR groups the territories.",
            "rurality": "urban | rural, derived from postal FSA (synthetic here).",
            "insurance_type": "public | private | mixed | uninsured.",
            "enrollment_start": "First date of continuous data capture.",
            "enrollment_end": "Last date of continuous data capture.",
            "first_symptom_date": "First claim carrying a Type 2 symptom code.",
            "index_dx_date": "First claim carrying a confirmed diagnosis code.",
            "severity": "mild | moderate | severe.",
            "primary_condition": "atopic_dermatitis | severe_asthma | both.",
        },
    },
    "claim_medical": {
        "grain": "one row per medical claim line",
        "description": "Adjudicated medical claims from private payer and "
                       "provincial administrative sources.",
        "steward": "RWD Data Engineering",
        "pii_class": "de-identified",
        "key_columns": {
            "service_date": "Date of service. Subject to future-date defect DQ-02.",
            "dx_code": "ICD-10-CA style diagnosis code (illustrative).",
            "proc_code": "Fee code. A605 = specialist consult, H101 = ED visit.",
            "paid_amount": "Amount paid in CAD. Not list price.",
            "ingest_date": "When the row landed in HELIOS - drives latency KPIs.",
        },
    },
    "claim_pharmacy": {
        "grain": "one row per dispensed prescription",
        "description": "National PBM pharmacy dispensing records.",
        "steward": "RWD Data Engineering",
        "pii_class": "de-identified",
        "key_columns": {
            "fill_date": "Dispensing date.",
            "drug_name": "Brand or molecule label. SANOVIA is the fictional "
                         "launch brand used throughout this demo.",
            "drug_class": "Therapeutic class. biologic_* and jak are advanced therapy.",
            "days_supply": "Days of therapy dispensed. NULL/0 on ~7% of rows "
                           "(defect DQ-01) - materially affects PDC adherence.",
        },
    },
    "ehr_encounter": {
        "grain": "one row per ambulatory encounter",
        "description": "Ambulatory EHR network - the only source with clinical "
                       "severity scores and labs. Covers ~42% of the spine.",
        "steward": "Clinical Data Products",
        "pii_class": "de-identified, broad consent",
        "key_columns": {
            "easi_score": "Eczema Area and Severity Index (0-72). ~40% missing.",
            "eosinophil_count": "Blood eosinophils in 10^9/L. ~5% submitted in "
                                "cells/uL instead (defect DQ-03).",
            "fev1_pct_predicted": "Spirometry, asthma patients only.",
        },
    },
    "registry_enrollment": {
        "grain": "one row per registry enrolment",
        "description": "Consented Type 2 inflammation patient registry. Rich "
                       "PRO data but strongly selected - see DQ-08.",
        "steward": "Medical Affairs / Registry Operations",
        "pii_class": "explicit informed consent",
        "key_columns": {
            "pro_dlqi_score": "Dermatology Life Quality Index (0-30).",
            "consent_flag": "0 = consent withdrawn; rows MUST be excluded.",
        },
    },
    "provider": {
        "grain": "one row per prescriber",
        "description": "Prescriber reference dimension.",
        "steward": "RWD Data Engineering",
        "pii_class": "professional, non-patient",
        "key_columns": {"specialty": "GP | DERM | RESP | ALLERGY | PEDS | IM"},
    },
    "source_metadata": {
        "grain": "one row per contracted data source",
        "description": "Contract, cadence, lag, consent basis and licence expiry "
                       "for each asset. Drives the timeliness and licence checks.",
        "steward": "RWD Data Sourcing & Contracts",
        "pii_class": "metadata only",
        "key_columns": {
            "publication_lag_days": "Days between service and availability.",
            "license_expiry": "Contract end date - insights past this cannot ship.",
            "consent_basis": "Legal basis for processing.",
        },
    },
}

# --------------------------------------------------------------------------
# Dimensions available as cohort filters and as break-outs
# --------------------------------------------------------------------------
DIMENSIONS = {
    "province": {"column": "province", "type": "categorical",
                 "values": ["ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "TERR"],
                 "description": "Province of residence."},
    "rurality": {"column": "rurality", "type": "categorical",
                 "values": ["urban", "rural"],
                 "description": "Urban vs rural residence - the health-equity lens."},
    "insurance_type": {"column": "insurance_type", "type": "categorical",
                       "values": ["public", "private", "mixed", "uninsured"],
                       "description": "Payer channel. Drives formulary access."},
    "severity": {"column": "severity", "type": "categorical",
                 "values": ["mild", "moderate", "severe"],
                 "description": "Clinician-assigned disease severity."},
    "primary_condition": {"column": "primary_condition", "type": "categorical",
                          "values": ["atopic_dermatitis", "severe_asthma", "both"],
                          "description": "Primary Type 2 inflammatory condition."},
    "sex": {"column": "sex", "type": "categorical", "values": ["F", "M", "U"],
            "description": "Harmonised sex. Use `sex`, never `sex_raw`."},
    "age_band": {"column": "age_band", "type": "derived",
                 "values": ["0-11", "12-17", "18-39", "40-64", "65+"],
                 "expr": "CASE WHEN (2026 - birth_year) < 12 THEN '0-11' "
                         "WHEN (2026 - birth_year) < 18 THEN '12-17' "
                         "WHEN (2026 - birth_year) < 40 THEN '18-39' "
                         "WHEN (2026 - birth_year) < 65 THEN '40-64' ELSE '65+' END",
                 "description": "Age band as of the 2026 reference year."},
    "index_year": {"column": "index_year", "type": "derived",
                   "values": ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"],
                   "expr": "substr(index_dx_date, 1, 4)",
                   "description": "Calendar year of confirmed diagnosis."},
}

_ADV = "(r.drug_class LIKE 'biologic%' OR r.drug_class = 'jak')"

# --------------------------------------------------------------------------
# Metric registry
# --------------------------------------------------------------------------
METRICS = {
    "M01_time_to_diagnosis": {
        "label": "Time to confirmed diagnosis",
        "grain": "distribution",
        "unit": "days",
        "definition": "Days from the first claim carrying a Type 2 symptom code "
                      "to the first claim carrying a confirmed diagnosis code. "
                      "Patients with no confirmed diagnosis are excluded.",
        "decision_supported": "Where to place disease-awareness and referral-"
                              "pathway investment; sizing the diagnostic odyssey.",
        "owner": "Medical Affairs / Epidemiology",
        "critical_dq": ["completeness_index_dates", "plausibility_dates", "timeliness"],
        "required_sources": ["CLM_PRIV_PAYER", "PROV_ADMIN_QC"],
        "caveat": "Left-censored: symptoms occurring before enrolment_start are "
                  "invisible, so this is a floor, not a true onset-to-diagnosis time.",
        "sql": """
WITH cohort AS ({COHORT})
SELECT patient_id,
       julianday(index_dx_date) - julianday(first_symptom_date) AS value
FROM cohort
WHERE index_dx_date IS NOT NULL
  AND first_symptom_date IS NOT NULL
  AND julianday(index_dx_date) >= julianday(first_symptom_date)
""",
    },
    "M02_time_to_advanced_therapy": {
        "label": "Time from diagnosis to advanced therapy",
        "grain": "distribution",
        "unit": "days",
        "definition": "Days from confirmed diagnosis to the first dispensed "
                      "biologic or JAK inhibitor. Only patients who initiate are included.",
        "decision_supported": "Field-medical targeting; identifying where "
                              "escalation is slowest relative to guidelines.",
        "owner": "Commercial Analytics",
        "critical_dq": ["completeness_index_dates", "linkage_rate", "timeliness"],
        "required_sources": ["CLM_NATL_PBM", "CLM_PRIV_PAYER"],
        "caveat": "Conditioned on initiation - it does not describe the patients "
                  "who never escalate. Pair with M03 and M14.",
        "sql": """
WITH cohort AS ({COHORT}),
first_adv AS (
  SELECT r.patient_id, MIN(r.fill_date) AS d0
  FROM claim_pharmacy r JOIN cohort c ON c.patient_id = r.patient_id
  WHERE """ + _ADV + """
  GROUP BY r.patient_id
)
SELECT c.patient_id, julianday(f.d0) - julianday(c.index_dx_date) AS value
FROM cohort c JOIN first_adv f ON f.patient_id = c.patient_id
WHERE julianday(f.d0) >= julianday(c.index_dx_date)
""",
    },
    "M03_advanced_therapy_initiation_rate": {
        "label": "Advanced therapy initiation rate",
        "grain": "rate",
        "unit": "% of patients",
        "definition": "Share of the cohort with at least one dispensed biologic "
                      "or JAK inhibitor at any point in their enrolment window.",
        "decision_supported": "Market sizing and identification of under-treated segments.",
        "owner": "Commercial Analytics",
        "critical_dq": ["completeness_days_supply", "linkage_rate", "coverage"],
        "required_sources": ["CLM_NATL_PBM"],
        "caveat": "Dispensing is not administration; free-goods and patient "
                  "support programme volume is not visible in PBM claims.",
        "sql": """
WITH cohort AS ({COHORT})
SELECT
  (SELECT COUNT(DISTINCT r.patient_id)
     FROM claim_pharmacy r JOIN cohort c2 ON c2.patient_id = r.patient_id
    WHERE """ + _ADV + """) AS numerator,
  (SELECT COUNT(*) FROM cohort) AS denominator
""",
    },
    "M04_brand_share_new_starts": {
        "label": "SANOVIA share of new advanced-therapy starts",
        "grain": "series",
        "unit": "% of new starts, monthly",
        "definition": "Of all patients starting a biologic or JAK inhibitor in a "
                      "calendar month, the share whose start is SANOVIA. "
                      "Restricted to months from the September 2024 launch onward.",
        "decision_supported": "The core launch-tracking metric: is uptake on curve?",
        "owner": "Launch Excellence",
        "critical_dq": ["timeliness", "completeness_days_supply", "coverage"],
        "required_sources": ["CLM_NATL_PBM"],
        "caveat": "The two most recent months are systematically understated "
                  "because of pharmacy claim run-off; never read the last bar.",
        "sql": """
WITH cohort AS ({COHORT}),
starts AS (
  SELECT r.patient_id, r.drug_name, MIN(r.fill_date) AS start_date
  FROM claim_pharmacy r JOIN cohort c ON c.patient_id = r.patient_id
  WHERE """ + _ADV + """
  GROUP BY r.patient_id, r.drug_name
)
SELECT substr(start_date, 1, 7) AS period,
       SUM(CASE WHEN drug_name = 'SANOVIA' THEN 1 ELSE 0 END) AS numerator,
       COUNT(*) AS denominator
FROM starts
WHERE start_date >= '2024-09-01'
GROUP BY period
ORDER BY period
""",
    },
    "M05_persistence_12mo": {
        "label": "12-month persistence rate on advanced therapy",
        "grain": "rate",
        "unit": "% of initiators",
        "definition": "Of patients who initiated advanced therapy on or before "
                      "2025-06-30, the share with at least one further advanced-"
                      "therapy fill 300-390 days after their index fill.",
        "decision_supported": "Adherence-programme design and value-story evidence.",
        "owner": "Patient Support Programmes",
        "critical_dq": ["completeness_days_supply", "coverage", "timeliness"],
        "required_sources": ["CLM_NATL_PBM"],
        "caveat": "Initiators after 2025-06-30 are excluded to avoid right-"
                  "censoring bias; the denominator is therefore not the full cohort.",
        "sql": """
WITH cohort AS ({COHORT}),
idx AS (
  SELECT r.patient_id, MIN(r.fill_date) AS d0
  FROM claim_pharmacy r JOIN cohort c ON c.patient_id = r.patient_id
  WHERE """ + _ADV + """
  GROUP BY r.patient_id
  HAVING MIN(r.fill_date) <= '2025-06-30'
)
SELECT
  (SELECT COUNT(DISTINCT i.patient_id)
     FROM idx i JOIN claim_pharmacy r2 ON r2.patient_id = i.patient_id
    WHERE (r2.drug_class LIKE 'biologic%' OR r2.drug_class = 'jak')
      AND julianday(r2.fill_date) - julianday(i.d0) BETWEEN 300 AND 390) AS numerator,
  (SELECT COUNT(*) FROM idx) AS denominator
""",
    },
    "M06_pdc_adherence": {
        "label": "Proportion of days covered (PDC), first year",
        "grain": "distribution",
        "unit": "proportion 0-1",
        "definition": "Sum of days_supply dispensed in the 365 days from index "
                      "advanced-therapy fill, divided by 365 and capped at 1.0.",
        "decision_supported": "Quantifying the adherence gap the support programme must close.",
        "owner": "Patient Support Programmes",
        "critical_dq": ["completeness_days_supply"],
        "required_sources": ["CLM_NATL_PBM"],
        "caveat": "DIRECTLY exposed to defect DQ-01. Rows with NULL/0 days_supply "
                  "are treated as zero coverage, which biases PDC downward. This "
                  "metric is gated Amber until DQ-01 is remediated.",
        "sql": """
WITH cohort AS ({COHORT}),
idx AS (
  SELECT r.patient_id, MIN(r.fill_date) AS d0
  FROM claim_pharmacy r JOIN cohort c ON c.patient_id = r.patient_id
  WHERE """ + _ADV + """
  GROUP BY r.patient_id
  HAVING MIN(r.fill_date) <= '2025-06-30'
),
cov AS (
  SELECT i.patient_id, SUM(COALESCE(r.days_supply, 0)) AS ds
  FROM idx i JOIN claim_pharmacy r ON r.patient_id = i.patient_id
  WHERE (r.drug_class LIKE 'biologic%' OR r.drug_class = 'jak')
    AND julianday(r.fill_date) - julianday(i.d0) BETWEEN 0 AND 364
  GROUP BY i.patient_id
)
SELECT patient_id, MIN(1.0, ds / 365.0) AS value FROM cov
""",
    },
    "M07_specialist_involvement_rate": {
        "label": "Specialist involvement rate",
        "grain": "rate",
        "unit": "% of patients",
        "definition": "Share of the cohort with at least one specialist consult "
                      "claim (fee code A605) at any point in their enrolment window.",
        "decision_supported": "Referral-pathway strategy; where GPs manage alone.",
        "owner": "Medical Affairs",
        "critical_dq": ["conformance_codes", "coverage", "referential_integrity"],
        "required_sources": ["CLM_PRIV_PAYER", "PROV_ADMIN_QC"],
        "caveat": "Fee-code capture differs between the private payer and QC "
                  "provincial feeds; cross-province comparison is directional only.",
        "sql": """
WITH cohort AS ({COHORT})
SELECT
  (SELECT COUNT(DISTINCT m.patient_id)
     FROM claim_medical m JOIN cohort c2 ON c2.patient_id = m.patient_id
    WHERE m.proc_code = 'A605') AS numerator,
  (SELECT COUNT(*) FROM cohort) AS denominator
""",
    },
    "M08_ed_visits_per_100_patients": {
        "label": "ED visits per 100 patients",
        "grain": "rate",
        "unit": "visits per 100 patients",
        "definition": "Count of emergency department claims (fee code H101) "
                      "divided by cohort size, expressed per 100 patients.",
        "decision_supported": "Burden-of-illness and payer value story.",
        "owner": "Market Access / HEOR",
        "critical_dq": ["deduplication", "plausibility_dates", "coverage"],
        "required_sources": ["CLM_PRIV_PAYER", "PROV_ADMIN_QC"],
        "caveat": "Exposed to duplicate-claim defect DQ-06; the deduplicated "
                  "figure is the governed one.",
        "sql": """
WITH cohort AS ({COHORT})
SELECT
  (SELECT COUNT(DISTINCT m.claim_id)
     FROM claim_medical m JOIN cohort c2 ON c2.patient_id = m.patient_id
    WHERE m.proc_code = 'H101') AS numerator,
  (SELECT COUNT(*) FROM cohort) AS denominator
""",
        "scale": 100.0,
    },
    "M09_treatment_sequence": {
        "label": "Most common treatment sequences",
        "grain": "category",
        "unit": "% of patients",
        "definition": "Ordered distinct therapeutic classes dispensed to each "
                      "patient, concatenated in first-fill order.",
        "decision_supported": "Where SANOVIA actually sits in the real pathway "
                              "versus where the guideline says it should.",
        "owner": "Commercial Analytics",
        "critical_dq": ["completeness_days_supply", "coverage"],
        "required_sources": ["CLM_NATL_PBM"],
        "caveat": "Classes dispensed before enrolment_start are invisible, so "
                  "sequences are truncated on the left.",
        "sql": """
WITH cohort AS ({COHORT}),
o AS (
  SELECT r.patient_id, r.drug_class, MIN(r.fill_date) AS d
  FROM claim_pharmacy r JOIN cohort c ON c.patient_id = r.patient_id
  GROUP BY r.patient_id, r.drug_class
)
SELECT patient_id, GROUP_CONCAT(drug_class, ' > ') AS value
FROM (SELECT * FROM o ORDER BY patient_id, d)
GROUP BY patient_id
""",
    },
    "M10_switch_rate_12mo": {
        "label": "12-month advanced-therapy switch rate",
        "grain": "rate",
        "unit": "% of initiators",
        "definition": "Share of advanced-therapy initiators dispensed a second, "
                      "different advanced-therapy brand within 365 days of index.",
        "decision_supported": "Competitive dynamics and switch-capture opportunity.",
        "owner": "Commercial Analytics",
        "critical_dq": ["completeness_days_supply", "coverage"],
        "required_sources": ["CLM_NATL_PBM"],
        "caveat": "A dose-form change recorded under a different label would "
                  "be misread as a switch.",
        "sql": """
WITH cohort AS ({COHORT}),
idx AS (
  SELECT r.patient_id, MIN(r.fill_date) AS d0
  FROM claim_pharmacy r JOIN cohort c ON c.patient_id = r.patient_id
  WHERE """ + _ADV + """
  GROUP BY r.patient_id
  HAVING MIN(r.fill_date) <= '2025-06-30'
)
SELECT
  (SELECT COUNT(DISTINCT i.patient_id) FROM idx i
     JOIN claim_pharmacy a ON a.patient_id = i.patient_id AND a.fill_date = i.d0
     JOIN claim_pharmacy b ON b.patient_id = i.patient_id
    WHERE (b.drug_class LIKE 'biologic%' OR b.drug_class = 'jak')
      AND b.drug_name <> a.drug_name
      AND julianday(b.fill_date) - julianday(i.d0) BETWEEN 1 AND 365) AS numerator,
  (SELECT COUNT(*) FROM idx) AS denominator
""",
    },
    "M11_annual_cost_per_patient": {
        "label": "Direct medical cost per patient-year",
        "grain": "distribution",
        "unit": "CAD",
        "definition": "Total paid amount across medical and pharmacy claims per "
                      "patient, annualised over their enrolment window.",
        "decision_supported": "Payer value dossier and budget-impact modelling.",
        "owner": "Market Access / HEOR",
        "critical_dq": ["deduplication", "plausibility_dates", "coverage"],
        "required_sources": ["CLM_PRIV_PAYER", "CLM_NATL_PBM", "PROV_ADMIN_QC"],
        "caveat": "Paid amount, not list price, and excludes indirect costs "
                  "and out-of-pocket spend.",
        "sql": """
WITH cohort AS ({COHORT}),
yrs AS (
  SELECT patient_id,
         MAX(0.25, (julianday(enrollment_end) - julianday(enrollment_start)) / 365.25) AS py
  FROM cohort
),
spend AS (
  SELECT y.patient_id, y.py,
    COALESCE((SELECT SUM(m.paid_amount) FROM claim_medical m
               WHERE m.patient_id = y.patient_id), 0) +
    COALESCE((SELECT SUM(r.paid_amount) FROM claim_pharmacy r
               WHERE r.patient_id = y.patient_id), 0) AS total
  FROM yrs y
)
SELECT patient_id, total / py AS value FROM spend
""",
    },
    "M12_untreated_severe_gap": {
        "label": "Severe patients with no systemic or advanced therapy",
        "grain": "rate",
        "unit": "% of severe patients",
        "definition": "Share of patients recorded as severe who have no systemic "
                      "immunosuppressant, systemic corticosteroid, biologic or "
                      "JAK dispensing on record - the clinical white space.",
        "decision_supported": "The single largest unmet-need signal for launch "
                              "territory prioritisation.",
        "owner": "Medical Affairs / Launch Excellence",
        "critical_dq": ["coverage", "linkage_rate", "completeness_days_supply"],
        "required_sources": ["CLM_NATL_PBM"],
        "caveat": "Absence of a claim is not absence of treatment - samples, "
                  "hospital-supplied product and cash purchases are invisible. "
                  "Treat as an upper bound on true under-treatment.",
        "sql": """
WITH cohort AS (SELECT * FROM ({COHORT}) WHERE severity = 'severe')
SELECT
  (SELECT COUNT(*) FROM cohort c2
    WHERE NOT EXISTS (
      SELECT 1 FROM claim_pharmacy r
       WHERE r.patient_id = c2.patient_id
         AND (r.drug_class LIKE 'biologic%' OR r.drug_class IN
              ('jak', 'systemic_ist', 'systemic_cs')))) AS numerator,
  (SELECT COUNT(*) FROM cohort) AS denominator
""",
    },
    "M13_quality_of_life_dlqi": {
        "label": "Patient-reported quality of life (DLQI) at registry enrolment",
        "grain": "distribution",
        "unit": "DLQI points",
        "definition": "Dermatology Life Quality Index (0-30, higher is worse) "
                      "recorded at enrolment in the consented Type 2 registry. "
                      "Rows with withdrawn consent are excluded at the cohort layer.",
        "decision_supported": "The humanistic-burden chapter of the payer dossier "
                              "and the patient-voice narrative for launch.",
        "owner": "Medical Affairs / HEOR",
        "critical_dq": ["representativeness", "governance", "coverage"],
        "required_sources": ["REG_T2INFLAM"],
        "caveat": "The registry is a volunteer, specialist-referred, "
                  "predominantly urban population. This is the single least "
                  "generalisable asset in the product and is included here "
                  "precisely to demonstrate the Fitness-for-Use gate refusing it.",
        "sql": """
WITH cohort AS ({COHORT})
SELECT r.patient_id, r.pro_dlqi_score AS value
FROM registry_enrollment r JOIN cohort c ON c.patient_id = r.patient_id
WHERE r.consent_flag = 1 AND r.pro_dlqi_score IS NOT NULL
""",
    },
}

# --------------------------------------------------------------------------
# Business questions: the bridge from a launch decision to a governed metric.
# This is the BA artefact that makes the agent's plans auditable.
# --------------------------------------------------------------------------
BUSINESS_QUESTIONS = [
    {"id": "BQ-01", "question": "How long do patients wait for a confirmed diagnosis, "
     "and where is the wait worst?", "metric": "M01_time_to_diagnosis",
     "breakdown": "rurality", "decision": "Referral-pathway investment",
     "stakeholder": "Medical Affairs"},
    {"id": "BQ-02", "question": "Is SANOVIA uptake tracking to the launch curve?",
     "metric": "M04_brand_share_new_starts", "breakdown": None,
     "decision": "Launch course-correction", "stakeholder": "Launch Excellence"},
    {"id": "BQ-03", "question": "Which severe patients are receiving nothing at all?",
     "metric": "M12_untreated_severe_gap", "breakdown": "province",
     "decision": "Territory prioritisation", "stakeholder": "Launch Excellence"},
    {"id": "BQ-04", "question": "How adherent are patients in their first year?",
     "metric": "M06_pdc_adherence", "breakdown": None,
     "decision": "Support-programme design", "stakeholder": "Patient Support"},
    {"id": "BQ-05", "question": "Does payer channel change access to advanced therapy?",
     "metric": "M03_advanced_therapy_initiation_rate", "breakdown": "insurance_type",
     "decision": "Market access negotiation", "stakeholder": "Market Access"},
    {"id": "BQ-06", "question": "What does the real treatment pathway look like?",
     "metric": "M09_treatment_sequence", "breakdown": None,
     "decision": "Positioning and messaging", "stakeholder": "Commercial"},
    {"id": "BQ-07", "question": "What is the burden of illness we can reduce?",
     "metric": "M08_ed_visits_per_100_patients", "breakdown": "severity",
     "decision": "Payer value dossier", "stakeholder": "HEOR"},
    {"id": "BQ-08", "question": "Do patients stay on advanced therapy for a year?",
     "metric": "M05_persistence_12mo", "breakdown": "rurality",
     "decision": "Support-programme design", "stakeholder": "Patient Support"},
]


def metric(mid):
    if mid not in METRICS:
        raise KeyError(f"unknown metric '{mid}'. Known: {sorted(METRICS)}")
    return METRICS[mid]


def searchable_documents():
    """Flatten the semantic layer into retrievable documents for the RAG index.

    The agent retrieves over THESE, not over raw prose, which is what keeps its
    plans inside the governed vocabulary.
    """
    docs = []
    for mid, m in METRICS.items():
        docs.append({
            "doc_id": mid, "kind": "metric", "title": m["label"],
            "text": " ".join([
                m["label"], m["definition"], m["decision_supported"],
                "unit " + m["unit"], "owner " + m["owner"], "caveat " + m["caveat"],
                "sources " + " ".join(m["required_sources"]),
            ]),
            "meta": {"grain": m["grain"], "unit": m["unit"], "owner": m["owner"]},
        })
    for did, d in DIMENSIONS.items():
        docs.append({
            "doc_id": f"DIM_{did}", "kind": "dimension", "title": did,
            "text": f"dimension {did} {d['description']} values " + " ".join(d["values"]),
            "meta": {"values": d["values"]},
        })
    for tname, t in TABLES.items():
        cols = " ".join(f"{k} {v}" for k, v in t["key_columns"].items())
        docs.append({
            "doc_id": f"TBL_{tname}", "kind": "table", "title": tname,
            "text": f"table {tname} {t['grain']} {t['description']} {cols}",
            "meta": {"steward": t["steward"]},
        })
    for bq in BUSINESS_QUESTIONS:
        docs.append({
            "doc_id": bq["id"], "kind": "business_question", "title": bq["question"],
            "text": f"{bq['question']} decision {bq['decision']} "
                    f"stakeholder {bq['stakeholder']} metric {bq['metric']}",
            "meta": {"metric": bq["metric"], "breakdown": bq["breakdown"]},
        })
    return docs
