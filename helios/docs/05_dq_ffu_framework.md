# HELIOS — Data Quality & Fitness-for-Use Framework

**Companion:** `05a_dq_ffu_live_results.md` holds the current numbers and is
regenerated from a live run. This document is the framework; that one is the
measurement.

---

## 1. The idea this framework exists to correct

Most data-quality tooling answers **"is this dataset good?"** That question has
no useful answer, because quality is not a property of data. It is a property
of the relationship between data and a decision.

Two examples from this product:

- The ambulatory EHR is **40% missing** on EASI severity scores. For a
  biomarker-stratified sub-analysis that is disqualifying. For the monthly
  brand-share trend, which never touches a lab value, it is **completely
  irrelevant** — and a global quality score would have flagged the trend red
  for no reason.
- The patient registry has excellent completeness, tight conformance and rich
  patient-reported outcomes. It also covers rural patients at **0.41×** the
  rate of the claims spine. A global score rates it highly. It is nonetheless
  **unusable** for any national quality-of-life claim.

So HELIOS never scores a dataset. It scores a **(metric × cohort) pair** — a
specific business question — and returns a verdict on what that answer may be
used for.

---

## 2. Quality dimensions

Built on the Kahn harmonised terminology (Conformance, Completeness,
Plausibility), extended with the operational and governance dimensions that
actually decide whether an RWD asset can carry a launch decision.

| Dimension | Question it answers | Checks |
|---|---|---|
| `conformance_codes` | Do values match their agreed value set? | DQ-07 |
| `completeness_days_supply` | Are the fields a metric depends on populated? | DQ-01 |
| `completeness_index_dates` | Can we place patients on a timeline at all? | DQ-14 |
| `completeness_clinical` | Is clinical detail present where the analysis needs it? | DQ-04 |
| `plausibility_dates` | Are records temporally possible? | DQ-02, DQ-09 |
| `plausibility_units` | Are clinical values in the units they claim? | DQ-03 |
| `deduplication` | Is each real-world event counted once? | DQ-06 |
| `timeliness` | Is the data recent enough for the decision cadence? | DQ-05 |
| `coverage` | What share of the population does this asset see? | DQ-12 |
| `linkage_rate` | Can patients be joined across assets? | DQ-11 |
| `referential_integrity` | Do foreign keys resolve? | DQ-10 |
| `representativeness` | Does the sample look like the population? | DQ-08 |
| `governance` | May we lawfully use it, today? | DQ-13, DQ-15 |

**Roll-up rule:** within a dimension, **worst case** — a single broken check is
not averaged away by healthy siblings in the same dimension.

## 3. What makes a check useful

A check that reports a red number and nothing else creates work without
direction. Every check in `dq.py` carries five business-authored fields
alongside the measurement:

| Field | Written by | Purpose |
|---|---|---|
| `business_impact` | BA, with the metric owner | States the consequence in decision language, not data language |
| `remediation` | BA, with Engineering | A specific action, not "improve data quality" |
| `owner` | BA | A named accountable function |
| `severity` | BA, with Privacy where relevant | Drives veto behaviour |
| `green` / `red` | BA, with Engineering | Thresholds are a business judgement, not a statistical one |

**Worked example — DQ-01.**

> *Measurement:* 7.05% of pharmacy claims have a missing or zero `days_supply`.
> *Business impact:* PDC adherence (M06) treats those rows as zero days of
> coverage, understating adherence and weakening the support-programme
> business case.
> *Remediation:* Impute from quantity × standard pack size for the 11
> highest-volume molecules; escalate the residual to the PBM vendor as a
> contractual defect.
> *Owner:* RWD Data Engineering. *Backlog:* HEL-61.

That is a check a Product Owner can prioritise from. "Completeness: 93%" is not.

### 3.1 Thresholds are calibrated, and the calibration is recorded

Initial thresholds ran too tight: on the first full run **every** metric came
back RED, which is operationally identical to having no gate at all — people
route around a system that always says no. Thresholds were re-set against
published RWD norms (for example, ambulatory EHR coverage of a claims spine of
30–50% is normal and not a defect) and the current spread is 3 Green, 9 Amber,
1 Red. **A gate that never passes and a gate that always passes are the same
gate.** Threshold changes are version-controlled and reviewed with the metric
owner.

---

## 4. Fitness-for-Use scoring

### 4.1 Composition

| Component | Weight | What it measures |
|---|---|---|
| Asset quality | 60% | Mean of the DQ dimensions **this metric declares** in `critical_dq`. Dimensions the metric does not use are excluded entirely. |
| Cohort sufficiency | 25% | Is the denominator large enough for this grain? Does the cohort inherit a known bias? |
| Governance | 15% | Licence validity, consent basis, source availability — **scoped to the sources this metric reads**. |

### 4.2 Veto rules

A weighted score alone would let a serious failure be offset by a good
average. These override it:

| Rule | Trigger | Result |
|---|---|---|
| V1 | Any declared critical dimension scores below 25 | RED |
| V2 | Critical-severity governance failure **in a source this metric reads** | RED + blocked |
| V3 | Denominator below the minimum cell size | RED + blocked |
| V4 | A required source's licence has expired | RED + blocked |

**V2's scoping was a defect fix.** The first implementation let any critical
governance failure veto every metric — a consent-withdrawal breach in the
registry blocked pharmacy-claims metrics that never touch registry data. The
`TABLE_SOURCES` map now scopes the veto to affected sources. The breach still
surfaces as a platform-level privacy incident; it just no longer blocks
unrelated work.

### 4.3 Bands and permitted use

| Band | Score | Permitted use |
|---|---|---|
| **GREEN** | ≥ 75 | Decision-grade. May be quoted directly in a governance forum. |
| **AMBER** | 50–74 | Directional only. Must be published with its caveat attached and must not be the sole basis for an investment decision. |
| **RED** | < 50 or vetoed | Not fit for this question. Publication blocked until the named remediation lands. |

The permitted-use sentence is printed **with the answer**, not in a footnote.
Risk R-02 (users treating Amber as decision-grade) is a presentation problem
before it is a data problem.

---

## 5. The framework working — three cases from the live run

### 5.1 The same defect, two verdicts

`DQ-08` (registry rural coverage at 0.41× the spine) scores 0/100.

- **M13** quality of life *declares* `representativeness` as critical → V1 veto → **RED, blocked**.
- **M04** brand share does not declare it and never reads the registry → **unaffected, AMBER at 64.3**.

One defect. Two correct, opposite verdicts. That is the whole thesis.

### 5.2 A metric that is Amber for exactly one reason

**M06** PDC adherence depends on a single dimension, `completeness_days_supply`,
which scores 36.9 because of DQ-01. FFU 62.1 → **AMBER**. The caveat written
into the metric registry says so in advance:

> *"DIRECTLY exposed to defect DQ-01. Rows with NULL/0 days_supply are treated
> as zero coverage, which biases PDC downward. This metric is gated Amber
> until DQ-01 is remediated."*

The remediation (HEL-61) has a named owner and a predicted effect: DQ-01 to
≤ 2%, M06 to Green. **The framework produces its own roadmap.**

### 5.3 Fitness collapsing on cohort, not on asset

**M05** persistence is Amber nationally. Asked for a single small province, the
asset quality is unchanged but the denominator collapses below the minimum
cell size → V3 veto → **RED, blocked**, and the small-cell policy suppresses
the underlying figure independently. Same metric, same data, different
question, correctly different answer.

---

## 6. Operating model

| Activity | Cadence | Owner |
|---|---|---|
| DQ suite execution + telemetry snapshot | Nightly | Platform |
| FFU re-scoring of every metric × standard cohort | Nightly | Platform |
| Band-change review (any metric degrading a band) | Weekly | BA + Product Owner |
| Threshold review | Quarterly | BA + metric owners |
| Remediation prioritisation into the sprint backlog | Per sprint | Product Owner |
| Critical governance failure | Immediate | Privacy Office |
| Exposure assessment when a metric degrades | On event | BA — *which published insights used this metric?* |

That last row is the one teams forget. When a defect is found, the question is
not only "fix the data" but **"which decisions have already been made on it?"**
The cohort hash on every published figure is what makes that answerable.
