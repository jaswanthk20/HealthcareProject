<!-- GENERATED FILE - do not edit by hand.
     Source: src/helios/semantic_layer.py + a live warehouse run.
     Regenerate: python docs/generate_docs.py -->

# HELIOS Data Dictionary

*Generated 2026-09-10 from semantic layer v1.2.0. Every definition below is the one the product actually computes.*

All data is synthetic. `SANOVIA` is a fictional brand.

---

## 1. Contracted sources

| Source | Type | Geography | Refresh | Publication lag | Consent basis | Licence expiry | Rows |
|---|---|---|---|---|---|---|---|
| `CLM_NATL_PBM` | pharmacy_claims | CA-ALL | 7d | **9d** | contractual_deidentified | 2027-03-31 | 305,097 |
| `CLM_PRIV_PAYER` | medical_claims | CA-ALL | 14d | **21d** | contractual_deidentified | 2026-12-31 | 404,845 |
| `EHR_AMBULATORY` | ehr | CA-ALL | 1d | **3d** | broad_consent | 2028-01-31 | 110,262 |
| `PROV_ADMIN_QC` | medical_claims | CA-QC | 30d | **62d** | data_sharing_agreement | 2027-06-30 | 76,997 |
| `REG_T2INFLAM` | registry | CA-ALL | 90d | **45d** | explicit_informed_consent | 2027-09-30 | 3,325 |

---

## 2. Tables

### `patient`

- **Grain**: one row per patient
- **Rows**: 40,000
- **Steward**: RWD Data Engineering
- **Privacy class**: de-identified / indirect identifiers present

De-identified patient spine with enrollment window, geography, payer type and clinician-assigned severity.

| Column | Type | Definition |
|---|---|---|
| `patient_id` | TEXT | Surrogate key. Never a real health card number. |
| `birth_year` | INTEGER | Year only - full DOB is suppressed at ingestion. |
| `sex` | TEXT | Harmonised M/F/U. |
| `sex_raw` | TEXT | Source-native coding; QC admin source uses 1/2. Do NOT use for analysis - demonstrates the conformance defect. |
| `province` | TEXT | Two-letter province code; TERR groups the territories. |
| `rurality` | TEXT | urban | rural, derived from postal FSA (synthetic here). |
| `insurance_type` | TEXT | public | private | mixed | uninsured. |
| `enrollment_start` | TEXT | First date of continuous data capture. |
| `enrollment_end` | TEXT | Last date of continuous data capture. |
| `index_dx_date` | TEXT | First claim carrying a confirmed diagnosis code. |
| `first_symptom_date` | TEXT | First claim carrying a Type 2 symptom code. |
| `severity` | TEXT | mild | moderate | severe. |
| `primary_condition` | TEXT | atopic_dermatitis | severe_asthma | both. |
| `source_id` | TEXT | - |

### `claim_medical`

- **Grain**: one row per medical claim line
- **Rows**: 481,842
- **Steward**: RWD Data Engineering
- **Privacy class**: de-identified

Adjudicated medical claims from private payer and provincial administrative sources.

| Column | Type | Definition |
|---|---|---|
| `claim_id` | TEXT | - |
| `patient_id` | TEXT | - |
| `service_date` | TEXT | Date of service. Subject to future-date defect DQ-02. |
| `provider_id` | TEXT | - |
| `dx_code` | TEXT | ICD-10-CA style diagnosis code (illustrative). |
| `proc_code` | TEXT | Fee code. A605 = specialist consult, H101 = ED visit. |
| `place_of_service` | TEXT | - |
| `paid_amount` | REAL | Amount paid in CAD. Not list price. |
| `source_id` | TEXT | - |
| `ingest_date` | TEXT | When the row landed in HELIOS - drives latency KPIs. |

### `claim_pharmacy`

- **Grain**: one row per dispensed prescription
- **Rows**: 305,097
- **Steward**: RWD Data Engineering
- **Privacy class**: de-identified

National PBM pharmacy dispensing records.

| Column | Type | Definition |
|---|---|---|
| `rx_id` | TEXT | - |
| `patient_id` | TEXT | - |
| `fill_date` | TEXT | Dispensing date. |
| `provider_id` | TEXT | - |
| `drug_name` | TEXT | Brand or molecule label. SANOVIA is the fictional launch brand used throughout this demo. |
| `drug_class` | TEXT | Therapeutic class. biologic_* and jak are advanced therapy. |
| `days_supply` | INTEGER | Days of therapy dispensed. NULL/0 on ~7% of rows (defect DQ-01) - materially affects PDC adherence. |
| `quantity` | REAL | - |
| `paid_amount` | REAL | - |
| `source_id` | TEXT | - |
| `ingest_date` | TEXT | - |

### `ehr_encounter`

- **Grain**: one row per ambulatory encounter
- **Rows**: 110,262
- **Steward**: Clinical Data Products
- **Privacy class**: de-identified, broad consent

Ambulatory EHR network - the only source with clinical severity scores and labs. Covers ~42% of the spine.

| Column | Type | Definition |
|---|---|---|
| `encounter_id` | TEXT | - |
| `patient_id` | TEXT | - |
| `encounter_date` | TEXT | - |
| `provider_id` | TEXT | - |
| `encounter_type` | TEXT | - |
| `easi_score` | REAL | Eczema Area and Severity Index (0-72). ~40% missing. |
| `eosinophil_count` | REAL | Blood eosinophils in 10^9/L. ~5% submitted in cells/uL instead (defect DQ-03). |
| `ige_level` | REAL | - |
| `fev1_pct_predicted` | REAL | Spirometry, asthma patients only. |
| `has_clinical_note` | INTEGER | - |
| `source_id` | TEXT | - |
| `ingest_date` | TEXT | - |

### `registry_enrollment`

- **Grain**: one row per registry enrolment
- **Rows**: 3,325
- **Steward**: Medical Affairs / Registry Operations
- **Privacy class**: explicit informed consent

Consented Type 2 inflammation patient registry. Rich PRO data but strongly selected - see DQ-08.

| Column | Type | Definition |
|---|---|---|
| `registry_row_id` | TEXT | - |
| `patient_id` | TEXT | - |
| `registry_name` | TEXT | - |
| `enroll_date` | TEXT | - |
| `severity_at_enroll` | TEXT | - |
| `biologic_naive` | INTEGER | - |
| `consent_flag` | INTEGER | 0 = consent withdrawn; rows MUST be excluded. |
| `pro_dlqi_score` | REAL | Dermatology Life Quality Index (0-30). |
| `source_id` | TEXT | - |
| `ingest_date` | TEXT | - |

### `provider`

- **Grain**: one row per prescriber
- **Rows**: 2,222
- **Steward**: RWD Data Engineering
- **Privacy class**: professional, non-patient

Prescriber reference dimension.

| Column | Type | Definition |
|---|---|---|
| `provider_id` | TEXT | - |
| `specialty` | TEXT | GP | DERM | RESP | ALLERGY | PEDS | IM |
| `province` | TEXT | - |
| `practice_setting` | TEXT | - |
| `annual_patient_volume` | INTEGER | - |
| `is_academic` | INTEGER | - |

### `source_metadata`

- **Grain**: one row per contracted data source
- **Rows**: 5
- **Steward**: RWD Data Sourcing & Contracts
- **Privacy class**: metadata only

Contract, cadence, lag, consent basis and licence expiry for each asset. Drives the timeliness and licence checks.

| Column | Type | Definition |
|---|---|---|
| `source_id` | TEXT | - |
| `source_name` | TEXT | - |
| `source_type` | TEXT | - |
| `refresh_cadence_days` | INTEGER | - |
| `publication_lag_days` | INTEGER | Days between service and availability. |
| `geography` | TEXT | - |
| `consent_basis` | TEXT | Legal basis for processing. |
| `license_expiry` | TEXT | Contract end date - insights past this cannot ship. |
| `last_refresh_date` | TEXT | - |
| `record_count` | INTEGER | - |

---

## 3. Governed dimensions

Cohort filters and break-outs may only use these. Anything else is rejected by the cohort compiler before a query is built.

| Dimension | Type | Permitted values | Definition |
|---|---|---|---|
| `province` | categorical | `ON`, `QC`, `BC`, `AB`, `MB`, `SK`, `NS`, `NB`, `NL`, `PE`, `TERR` | Province of residence. |
| `rurality` | categorical | `urban`, `rural` | Urban vs rural residence - the health-equity lens. |
| `insurance_type` | categorical | `public`, `private`, `mixed`, `uninsured` | Payer channel. Drives formulary access. |
| `severity` | categorical | `mild`, `moderate`, `severe` | Clinician-assigned disease severity. |
| `primary_condition` | categorical | `atopic_dermatitis`, `severe_asthma`, `both` | Primary Type 2 inflammatory condition. |
| `sex` | categorical | `F`, `M`, `U` | Harmonised sex. Use `sex`, never `sex_raw`. |
| `age_band` | derived | `0-11`, `12-17`, `18-39`, `40-64`, `65+` | Age band as of the 2026 reference year. |
| `index_year` | derived | `2019`, `2020`, `2021`, `2022`, `2023`, `2024`, `2025`, `2026` | Calendar year of confirmed diagnosis. |

---

## 4. Governed metrics

13 metrics. Each carries the decision it supports, its owner, the DQ dimensions it depends on, and the caveat that must travel with any published figure.

### `M01_time_to_diagnosis` - Time to confirmed diagnosis

| | |
|---|---|
| **Definition** | Days from the first claim carrying a Type 2 symptom code to the first claim carrying a confirmed diagnosis code. Patients with no confirmed diagnosis are excluded. |
| **Grain** | distribution |
| **Unit** | days |
| **Decision supported** | Where to place disease-awareness and referral-pathway investment; sizing the diagnostic odyssey. |
| **Business owner** | Medical Affairs / Epidemiology |
| **Required sources** | `CLM_PRIV_PAYER`, `PROV_ADMIN_QC` |
| **Critical DQ dimensions** | `completeness_index_dates`, `plausibility_dates`, `timeliness` |
| **Caveat (published with every figure)** | Left-censored: symptoms occurring before enrolment_start are invisible, so this is a floor, not a true onset-to-diagnosis time. |

### `M02_time_to_advanced_therapy` - Time from diagnosis to advanced therapy

| | |
|---|---|
| **Definition** | Days from confirmed diagnosis to the first dispensed biologic or JAK inhibitor. Only patients who initiate are included. |
| **Grain** | distribution |
| **Unit** | days |
| **Decision supported** | Field-medical targeting; identifying where escalation is slowest relative to guidelines. |
| **Business owner** | Commercial Analytics |
| **Required sources** | `CLM_NATL_PBM`, `CLM_PRIV_PAYER` |
| **Critical DQ dimensions** | `completeness_index_dates`, `linkage_rate`, `timeliness` |
| **Caveat (published with every figure)** | Conditioned on initiation - it does not describe the patients who never escalate. Pair with M03 and M14. |

### `M03_advanced_therapy_initiation_rate` - Advanced therapy initiation rate

| | |
|---|---|
| **Definition** | Share of the cohort with at least one dispensed biologic or JAK inhibitor at any point in their enrolment window. |
| **Grain** | rate |
| **Unit** | % of patients |
| **Decision supported** | Market sizing and identification of under-treated segments. |
| **Business owner** | Commercial Analytics |
| **Required sources** | `CLM_NATL_PBM` |
| **Critical DQ dimensions** | `completeness_days_supply`, `linkage_rate`, `coverage` |
| **Caveat (published with every figure)** | Dispensing is not administration; free-goods and patient support programme volume is not visible in PBM claims. |

### `M04_brand_share_new_starts` - SANOVIA share of new advanced-therapy starts

| | |
|---|---|
| **Definition** | Of all patients starting a biologic or JAK inhibitor in a calendar month, the share whose start is SANOVIA. Restricted to months from the September 2024 launch onward. |
| **Grain** | series |
| **Unit** | % of new starts, monthly |
| **Decision supported** | The core launch-tracking metric: is uptake on curve? |
| **Business owner** | Launch Excellence |
| **Required sources** | `CLM_NATL_PBM` |
| **Critical DQ dimensions** | `timeliness`, `completeness_days_supply`, `coverage` |
| **Caveat (published with every figure)** | The two most recent months are systematically understated because of pharmacy claim run-off; never read the last bar. |

### `M05_persistence_12mo` - 12-month persistence rate on advanced therapy

| | |
|---|---|
| **Definition** | Of patients who initiated advanced therapy on or before 2025-06-30, the share with at least one further advanced-therapy fill 300-390 days after their index fill. |
| **Grain** | rate |
| **Unit** | % of initiators |
| **Decision supported** | Adherence-programme design and value-story evidence. |
| **Business owner** | Patient Support Programmes |
| **Required sources** | `CLM_NATL_PBM` |
| **Critical DQ dimensions** | `completeness_days_supply`, `coverage`, `timeliness` |
| **Caveat (published with every figure)** | Initiators after 2025-06-30 are excluded to avoid right-censoring bias; the denominator is therefore not the full cohort. |

### `M06_pdc_adherence` - Proportion of days covered (PDC), first year

| | |
|---|---|
| **Definition** | Sum of days_supply dispensed in the 365 days from index advanced-therapy fill, divided by 365 and capped at 1.0. |
| **Grain** | distribution |
| **Unit** | proportion 0-1 |
| **Decision supported** | Quantifying the adherence gap the support programme must close. |
| **Business owner** | Patient Support Programmes |
| **Required sources** | `CLM_NATL_PBM` |
| **Critical DQ dimensions** | `completeness_days_supply` |
| **Caveat (published with every figure)** | DIRECTLY exposed to defect DQ-01. Rows with NULL/0 days_supply are treated as zero coverage, which biases PDC downward. This metric is gated Amber until DQ-01 is remediated. |

### `M07_specialist_involvement_rate` - Specialist involvement rate

| | |
|---|---|
| **Definition** | Share of the cohort with at least one specialist consult claim (fee code A605) at any point in their enrolment window. |
| **Grain** | rate |
| **Unit** | % of patients |
| **Decision supported** | Referral-pathway strategy; where GPs manage alone. |
| **Business owner** | Medical Affairs |
| **Required sources** | `CLM_PRIV_PAYER`, `PROV_ADMIN_QC` |
| **Critical DQ dimensions** | `conformance_codes`, `coverage`, `referential_integrity` |
| **Caveat (published with every figure)** | Fee-code capture differs between the private payer and QC provincial feeds; cross-province comparison is directional only. |

### `M08_ed_visits_per_100_patients` - ED visits per 100 patients

| | |
|---|---|
| **Definition** | Count of emergency department claims (fee code H101) divided by cohort size, expressed per 100 patients. |
| **Grain** | rate |
| **Unit** | visits per 100 patients |
| **Decision supported** | Burden-of-illness and payer value story. |
| **Business owner** | Market Access / HEOR |
| **Required sources** | `CLM_PRIV_PAYER`, `PROV_ADMIN_QC` |
| **Critical DQ dimensions** | `deduplication`, `plausibility_dates`, `coverage` |
| **Caveat (published with every figure)** | Exposed to duplicate-claim defect DQ-06; the deduplicated figure is the governed one. |

### `M09_treatment_sequence` - Most common treatment sequences

| | |
|---|---|
| **Definition** | Ordered distinct therapeutic classes dispensed to each patient, concatenated in first-fill order. |
| **Grain** | category |
| **Unit** | % of patients |
| **Decision supported** | Where SANOVIA actually sits in the real pathway versus where the guideline says it should. |
| **Business owner** | Commercial Analytics |
| **Required sources** | `CLM_NATL_PBM` |
| **Critical DQ dimensions** | `completeness_days_supply`, `coverage` |
| **Caveat (published with every figure)** | Classes dispensed before enrolment_start are invisible, so sequences are truncated on the left. |

### `M10_switch_rate_12mo` - 12-month advanced-therapy switch rate

| | |
|---|---|
| **Definition** | Share of advanced-therapy initiators dispensed a second, different advanced-therapy brand within 365 days of index. |
| **Grain** | rate |
| **Unit** | % of initiators |
| **Decision supported** | Competitive dynamics and switch-capture opportunity. |
| **Business owner** | Commercial Analytics |
| **Required sources** | `CLM_NATL_PBM` |
| **Critical DQ dimensions** | `completeness_days_supply`, `coverage` |
| **Caveat (published with every figure)** | A dose-form change recorded under a different label would be misread as a switch. |

### `M11_annual_cost_per_patient` - Direct medical cost per patient-year

| | |
|---|---|
| **Definition** | Total paid amount across medical and pharmacy claims per patient, annualised over their enrolment window. |
| **Grain** | distribution |
| **Unit** | CAD |
| **Decision supported** | Payer value dossier and budget-impact modelling. |
| **Business owner** | Market Access / HEOR |
| **Required sources** | `CLM_PRIV_PAYER`, `CLM_NATL_PBM`, `PROV_ADMIN_QC` |
| **Critical DQ dimensions** | `deduplication`, `plausibility_dates`, `coverage` |
| **Caveat (published with every figure)** | Paid amount, not list price, and excludes indirect costs and out-of-pocket spend. |

### `M12_untreated_severe_gap` - Severe patients with no systemic or advanced therapy

| | |
|---|---|
| **Definition** | Share of patients recorded as severe who have no systemic immunosuppressant, systemic corticosteroid, biologic or JAK dispensing on record - the clinical white space. |
| **Grain** | rate |
| **Unit** | % of severe patients |
| **Decision supported** | The single largest unmet-need signal for launch territory prioritisation. |
| **Business owner** | Medical Affairs / Launch Excellence |
| **Required sources** | `CLM_NATL_PBM` |
| **Critical DQ dimensions** | `coverage`, `linkage_rate`, `completeness_days_supply` |
| **Caveat (published with every figure)** | Absence of a claim is not absence of treatment - samples, hospital-supplied product and cash purchases are invisible. Treat as an upper bound on true under-treatment. |

### `M13_quality_of_life_dlqi` - Patient-reported quality of life (DLQI) at registry enrolment

| | |
|---|---|
| **Definition** | Dermatology Life Quality Index (0-30, higher is worse) recorded at enrolment in the consented Type 2 registry. Rows with withdrawn consent are excluded at the cohort layer. |
| **Grain** | distribution |
| **Unit** | DLQI points |
| **Decision supported** | The humanistic-burden chapter of the payer dossier and the patient-voice narrative for launch. |
| **Business owner** | Medical Affairs / HEOR |
| **Required sources** | `REG_T2INFLAM` |
| **Critical DQ dimensions** | `representativeness`, `governance`, `coverage` |
| **Caveat (published with every figure)** | The registry is a volunteer, specialist-referred, predominantly urban population. This is the single least generalisable asset in the product and is included here precisely to demonstrate the Fitness-for-Use gate refusing it. |

---

## 5. Registered business questions

The routing table between a launch decision and a governed metric. A question that is not on this list and does not match a metric definition is refused rather than approximated.

| ID | Question | Metric | Default break-out | Decision | Stakeholder |
|---|---|---|---|---|---|
| BQ-01 | How long do patients wait for a confirmed diagnosis, and where is the wait worst? | `M01_time_to_diagnosis` | rurality | Referral-pathway investment | Medical Affairs |
| BQ-02 | Is SANOVIA uptake tracking to the launch curve? | `M04_brand_share_new_starts` | - | Launch course-correction | Launch Excellence |
| BQ-03 | Which severe patients are receiving nothing at all? | `M12_untreated_severe_gap` | province | Territory prioritisation | Launch Excellence |
| BQ-04 | How adherent are patients in their first year? | `M06_pdc_adherence` | - | Support-programme design | Patient Support |
| BQ-05 | Does payer channel change access to advanced therapy? | `M03_advanced_therapy_initiation_rate` | insurance_type | Market access negotiation | Market Access |
| BQ-06 | What does the real treatment pathway look like? | `M09_treatment_sequence` | - | Positioning and messaging | Commercial |
| BQ-07 | What is the burden of illness we can reduce? | `M08_ed_visits_per_100_patients` | severity | Payer value dossier | HEOR |
| BQ-08 | Do patients stay on advanced therapy for a year? | `M05_persistence_12mo` | rurality | Support-programme design | Patient Support |

---

## 6. Privacy policy applied to every figure

- Minimum cell size: **11** patients.
- Primary suppression (P1): any cell with a denominator below the minimum is suppressed.
- Numerator suppression (P2): a non-zero numerator below the minimum is suppressed even when the denominator is large.
- Complementary suppression (P3): if exactly one cell in a break-out is suppressed, the next-smallest is suppressed too, so the first cannot be recovered by subtraction.
- Consent enforcement (P4): registry rows with `consent_flag = 0` are excluded at the cohort layer.
- Audit (P5): every suppression decision is logged with its cohort hash.
