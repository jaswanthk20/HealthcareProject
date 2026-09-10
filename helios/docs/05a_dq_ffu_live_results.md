<!-- GENERATED FILE - do not edit by hand.
     Source: src/helios/semantic_layer.py + a live warehouse run.
     Regenerate: python docs/generate_docs.py -->

# Appendix - Live Data Quality and Fitness-for-Use Results

*Generated 2026-09-10 from an actual run against the warehouse.*

**Overall DQ score: 47.0/100** (mean of per-dimension worst-case scores).

## A1. Check results

| Check | Dimension | Table | Observed | Score | Status | Severity | Owner |
|---|---|---|---|---|---|---|---|
| DQ-01 | `completeness_days_supply` | `claim_pharmacy` | 7.05 % of rows | 36.9 | **FAIL** | high | RWD Data Engineering |
| DQ-02 | `plausibility_dates` | `claim_medical` | 2.49 % of rows | 51.2 | **WARN** | high | RWD Data Engineering |
| DQ-03 | `plausibility_units` | `ehr_encounter` | 4.68 % of non-null labs | 44.3 | **FAIL** | high | Clinical Data Products |
| DQ-04 | `completeness_clinical` | `ehr_encounter` | 40.01 % of encounters | 50.0 | **FAIL** | medium | Clinical Data Products |
| DQ-05 | `timeliness` | `source_metadata` | 62 days | 28.9 | **FAIL** | high | RWD Data Sourcing & Contracts |
| DQ-06 | `deduplication` | `claim_medical` | 1.48 % of rows | 52.4 | **WARN** | high | RWD Data Engineering |
| DQ-07 | `conformance_codes` | `patient` | 19.61 % of rows | 35.2 | **FAIL** | medium | RWD Data Engineering |
| DQ-08 | `representativeness` | `registry_enrollment` | 0.413 ratio vs spine | 0.0 | **FAIL** | high | Medical Affairs / Registry Operations |
| DQ-09 | `plausibility_dates` | `claim_medical` | 1.2 % of rows | 41.0 | **FAIL** | medium | RWD Data Engineering |
| DQ-10 | `referential_integrity` | `claim_medical` | 2.97 % of rows | 67.1 | **WARN** | medium | RWD Data Engineering |
| DQ-11 | `linkage_rate` | `patient` | 100.0 % of patients | 100.0 | **PASS** | high | RWD Data Engineering |
| DQ-12 | `coverage` | `ehr_encounter` | 42.25 % of patients | 55.6 | **WARN** | medium | Clinical Data Products |
| DQ-13 | `governance` | `source_metadata` | 0 sources | 100.0 | **PASS** | high | RWD Data Sourcing & Contracts |
| DQ-14 | `completeness_index_dates` | `patient` | 0.0 % of patients | 100.0 | **PASS** | high | RWD Data Engineering |
| DQ-15 | `governance` | `registry_enrollment` | 55 rows | 0.0 | **FAIL** | critical | Privacy Office / Registry Operations |

## A2. Failing checks, business impact and remediation

### DQ-15 - Registry rows retained despite withdrawn consent

- **Observed**: 55 rows (green at 0, red at 1)
- **Rows affected**: 55
- **Severity**: critical
- **Business impact**: Processing data for a patient who has withdrawn consent is a privacy incident, reportable regardless of whether the row ever reached a report.
- **Remediation**: Add a consent-withdrawal purge job on the registry refresh and enforce consent_flag = 1 in the cohort layer.
- **Owner**: Privacy Office / Registry Operations

### DQ-08 - Registry rural share relative to the rural share of the patient spine

- **Observed**: 0.413 ratio vs spine (green at 0.85, red at 0.45)
- **Rows affected**: 3,325
- **Severity**: high
- **Business impact**: The registry systematically under-represents rural patients. Any PRO or quality-of-life finding drawn from it describes urban patients and must not be generalised.
- **Remediation**: Either weight registry analyses to the claims spine by rurality and severity, or restrict registry-derived claims to urban populations in the label. Weighting is preferred.
- **Owner**: Medical Affairs / Registry Operations

### DQ-05 - Worst publication lag across contracted sources against the 30-day SLA

- **Observed**: 62 days (green at 30.0, red at 75.0)
- **Rows affected**: 2
- **Severity**: high
- **Business impact**: Any metric that depends on the QC provincial feed is structurally two months stale, so QC cannot be compared like-for-like against other provinces in a monthly review.
- **Remediation**: Either re-contract for a 30-day feed or publish QC on a separate, explicitly lagged panel. Do not blend silently.
- **Owner**: RWD Data Sourcing & Contracts

### DQ-01 - Pharmacy claims with a missing or zero days_supply

- **Observed**: 7.05 % of rows (green at 2.0, red at 10.0)
- **Rows affected**: 21,506
- **Severity**: high
- **Business impact**: PDC adherence (M06) treats these rows as zero days of coverage, understating adherence and weakening the support-programme business case.
- **Remediation**: Impute days_supply from quantity x standard pack size for the 11 highest-volume molecules; escalate the residual to the PBM vendor as a contractual data-quality defect.
- **Owner**: RWD Data Engineering

### DQ-03 - Eosinophil counts implausible for 10^9/L (likely submitted in cells/uL)

- **Observed**: 4.68 % of non-null labs (green at 0.5, red at 8.0)
- **Rows affected**: 3,096
- **Severity**: high
- **Business impact**: Type 2 biomarker phenotyping silently mis-classifies these patients as eosinophilic, corrupting any biomarker-defined sub-cohort.
- **Remediation**: Apply a UCUM unit-harmonisation rule at ingestion and back-convert values above 20 by dividing by 1000.
- **Owner**: Clinical Data Products

### DQ-02 - Medical claims dated in the future

- **Observed**: 2.49 % of rows (green at 0.1, red at 5.0)
- **Rows affected**: 11,974
- **Severity**: high
- **Business impact**: Future-dated claims inflate the most recent periods of every trend, which is precisely the window launch leadership reads first.
- **Remediation**: Add a hard ingestion reject for service_date > ingest_date and quarantine the affected rows for vendor replay.
- **Owner**: RWD Data Engineering

### DQ-06 - Exact duplicate medical claim rows

- **Observed**: 1.48 % of rows (green at 0.1, red at 3.0)
- **Rows affected**: 7,110
- **Severity**: high
- **Business impact**: Duplicates inflate utilisation and cost metrics (M08, M11), which are the two numbers the payer dossier rests on.
- **Remediation**: Add a deterministic dedupe on the natural key (patient_id, service_date, proc_code, paid_amount) in the silver layer, and assert uniqueness in the pipeline tests.
- **Owner**: RWD Data Engineering

### DQ-07 - Patient rows whose source-native sex coding is outside the M/F/U value set

- **Observed**: 19.61 % of rows (green at 0.5, red at 30.0)
- **Rows affected**: 7,846
- **Severity**: medium
- **Business impact**: Any analyst who reaches for sex_raw instead of the harmonised sex column silently drops or mis-buckets every patient sourced from the QC provincial feed.
- **Remediation**: Harmonisation already exists in the `sex` column. Revoke read access to sex_raw outside the engineering role and mark it deprecated in the data dictionary.
- **Owner**: RWD Data Engineering

### DQ-09 - Claims dated before the patient's year of birth

- **Observed**: 1.2 % of rows (green at 0.05, red at 2.0)
- **Rows affected**: 5,806
- **Severity**: medium
- **Business impact**: A temporally impossible record anywhere in the asset undermines confidence in every date-based metric, which is most of the product.
- **Remediation**: Add a cross-entity plausibility assertion (service_date >= date_of_birth) to the pipeline test suite.
- **Owner**: RWD Data Engineering

### DQ-04 - Encounters for dermatology patients with no EASI severity score

- **Observed**: 40.01 % of encounters (green at 20.0, red at 60.0)
- **Rows affected**: 29,436
- **Severity**: medium
- **Business impact**: Severity-stratified effectiveness analyses can only be run on the minority of encounters that carry a score, and that minority skews to specialist care.
- **Remediation**: Negotiate structured EASI capture in the next EHR network contract cycle; in the interim derive proxy severity from treatment intensity and document the proxy in the dictionary.
- **Owner**: Clinical Data Products

### DQ-12 - Patients on the spine with any EHR encounter

- **Observed**: 42.25 % of patients (green at 60.0, red at 20.0)
- **Rows affected**: 16,899
- **Severity**: medium
- **Business impact**: Clinical detail exists for a minority of the spine. Any metric requiring labs or severity scores runs on a subset that is not representative of the whole.
- **Remediation**: Expand the EHR network contract, and always report EHR-derived metrics with their own coverage denominator.
- **Owner**: Clinical Data Products

### DQ-10 - Claims referencing a provider_id absent from the provider dimension

- **Observed**: 2.97 % of rows (green at 0.5, red at 8.0)
- **Rows affected**: 14,322
- **Severity**: medium
- **Business impact**: Specialty-based analyses (M07, field targeting) silently drop these claims, biasing specialist involvement downward.
- **Remediation**: Backfill the provider dimension from the full national registry rather than the active-prescriber subset.
- **Owner**: RWD Data Engineering

## A3. Dimension roll-up

| Dimension | Score | Status | Driven by |
|---|---|---|---|
| `representativeness` | 0.0 | FAIL | DQ-08 - Registry rural share relative to the rural share of the patient spine |
| `governance` | 0.0 | FAIL | DQ-15 - Registry rows retained despite withdrawn consent |
| `timeliness` | 28.9 | FAIL | DQ-05 - Worst publication lag across contracted sources against the 30-day SLA |
| `conformance_codes` | 35.2 | FAIL | DQ-07 - Patient rows whose source-native sex coding is outside the M/F/U value set |
| `completeness_days_supply` | 36.9 | FAIL | DQ-01 - Pharmacy claims with a missing or zero days_supply |
| `plausibility_dates` | 41.0 | FAIL | DQ-09 - Claims dated before the patient's year of birth |
| `plausibility_units` | 44.3 | FAIL | DQ-03 - Eosinophil counts implausible for 10^9/L (likely submitted in cells/uL) |
| `completeness_clinical` | 50.0 | FAIL | DQ-04 - Encounters for dermatology patients with no EASI severity score |
| `deduplication` | 52.4 | WARN | DQ-06 - Exact duplicate medical claim rows |
| `coverage` | 55.6 | WARN | DQ-12 - Patients on the spine with any EHR encounter |
| `referential_integrity` | 67.1 | WARN | DQ-10 - Claims referencing a provider_id absent from the provider dimension |
| `linkage_rate` | 100.0 | PASS | DQ-11 - Patients on the spine linkable to at least one pharmacy claim |
| `completeness_index_dates` | 100.0 | PASS | DQ-14 - Patients missing a confirmed diagnosis date or a first symptom date |

## A4. Fitness-for-Use verdict per metric

Scored against the full patient population. A narrower cohort scores differently, which is the entire point of scoring the question rather than the dataset.

| Metric | FFU | Band | Asset | Cohort | Governance | Permitted use |
|---|---|---|---|---|---|---|
| `M02_time_to_advanced_therapy` | 85.8 | **GREEN** | 76.3 | 100.0 | 100.0 | Decision-grade |
| `M03_advanced_therapy_initiation_rate` | 78.5 | **GREEN** | 64.2 | 100.0 | 100.0 | Decision-grade |
| `M12_untreated_severe_gap` | 78.5 | **GREEN** | 64.2 | 100.0 | 100.0 | Decision-grade |
| `M01_time_to_diagnosis` | 74.0 | **AMBER** | 56.6 | 100.0 | 100.0 | Directional only |
| `M07_specialist_involvement_rate` | 71.6 | **AMBER** | 52.6 | 100.0 | 100.0 | Directional only |
| `M08_ed_visits_per_100_patients` | 69.8 | **AMBER** | 49.7 | 100.0 | 100.0 | Directional only |
| `M11_annual_cost_per_patient` | 69.8 | **AMBER** | 49.7 | 100.0 | 100.0 | Directional only |
| `M09_treatment_sequence` | 67.8 | **AMBER** | 46.2 | 100.0 | 100.0 | Directional only |
| `M10_switch_rate_12mo` | 67.8 | **AMBER** | 46.2 | 100.0 | 100.0 | Directional only |
| `M04_brand_share_new_starts` | 64.3 | **AMBER** | 40.5 | 100.0 | 100.0 | Directional only |
| `M05_persistence_12mo` | 64.3 | **AMBER** | 40.5 | 100.0 | 100.0 | Directional only |
| `M06_pdc_adherence` | 62.1 | **AMBER** | 36.9 | 100.0 | 100.0 | Directional only |
| `M13_quality_of_life_dlqi` | 36.1 | **RED** | 18.5 | 100.0 | 0.0 | Not fit for this question |

## A5. Metrics currently blocked from publication

### `M13_quality_of_life_dlqi` - Patient-reported quality of life (DLQI) at registry enrolment

- V1 - representativeness scores 0/100, driven by DQ-08 (Registry rural share relative to the rural share of the patient spine)
- V1 - governance scores 0/100, driven by DQ-15 (Registry rows retained despite withdrawn consent)
- V2/V4 - DQ-15: Registry rows retained despite withdrawn consent (55 rows)

**Remediation (Medical Affairs / Registry Operations)**: Either weight registry analyses to the claims spine by rurality and severity, or restrict registry-derived claims to urban populations in the label. Weighting is preferred.

**Remediation (Privacy Office / Registry Operations)**: Add a consent-withdrawal purge job on the registry refresh and enforce consent_flag = 1 in the cohort layer.
