# HELIOS — KPI Tree & Insight-to-Decision Ledger

---

## 1. KPI tree

Every governed metric ties to a launch objective. A metric with no objective
above it is a metric nobody has to act on, and it gets retired.

```
LAUNCH OBJECTIVE  Get the right patients to the right therapy, sooner
│
├── O1  Shorten the path to diagnosis
│     ├── KPI-01  Median time to confirmed diagnosis          M01   161 days
│     └── KPI-07  Rural / urban diagnostic gap                M01   1.51x
│
├── O2  Get eligible patients onto advanced therapy
│     ├── KPI-02  Advanced therapy initiation rate            M03   9.8%
│     ├── KPI-03  Time from diagnosis to advanced therapy     M02   255 days
│     ├── KPI-08  Untreated severe population                 M12   39.2%
│     └── KPI-11  Payer-channel access gap                    M03   2.6x
│
├── O3  Win share of new starts
│     ├── KPI-04  SANOVIA share of new starts                 M04   trend
│     └── KPI-09  12-month switch rate                        M10   18.1%
│
├── O4  Keep patients on therapy
│     ├── KPI-05  12-month persistence                        M05   47.8%
│     └── KPI-06  First-year PDC adherence                    M06   0.66
│
└── O5  Prove the value we reduce
      ├── KPI-10  ED visits per 100 patients                  M08   58.3
      └── KPI-12  Direct medical cost per patient-year        M11   $505
```

*Values are from the current synthetic run and are illustrative.*

## 2. KPI definitions

| KPI | Metric | Current | FFU band | Objective | Owner |
|---|---|---|---|---|---|
| KPI-01 | M01 | 161 days (IQR 104–243) | AMBER | O1 | Medical Affairs |
| KPI-02 | M03 | 9.8% | GREEN | O2 | Commercial Analytics |
| KPI-03 | M02 | 255 days (IQR 137–363) | GREEN | O2 | Commercial Analytics |
| KPI-04 | M04 | see trend | AMBER | O3 | Launch Excellence |
| KPI-05 | M05 | 47.8% | AMBER | O4 | Patient Support |
| KPI-06 | M06 | 0.66 | AMBER | O4 | Patient Support |
| KPI-07 | M01 by rurality | 227 vs 150 days (**1.51×**) | AMBER | O1 | Medical Affairs |
| KPI-08 | M12 | 39.2% | GREEN | O2 | Launch Excellence |
| KPI-09 | M10 | 18.1% | AMBER | O3 | Commercial Analytics |
| KPI-10 | M08 | 58.3 per 100 | AMBER | O5 | HEOR |
| KPI-11 | M03 by payer | 10.0% public vs 3.8% uninsured | GREEN | O2 | Market Access |
| KPI-12 | M11 | $505 / patient-year | AMBER | O5 | HEOR |

---

## 3. Insight-to-decision ledger

The artefact that closes the loop. An insight that does not change a decision
is analytics theatre; an insight that changes a decision but is not written
down cannot be reviewed when the data turns out to be wrong.

Every row carries the cohort hash, so the figure behind the decision can be
re-executed months later.

| # | Insight | Metric · cohort hash | Band | Decision taken | Owner | Review |
|---|---|---|---|---|---|---|
| L-01 | Rural patients wait **227 days** to confirmed diagnosis vs **150** urban — a **1.51×** gap on n=7,507 vs 32,493 | `M01` · `CH-E3DEB3245B07` / `CH-B7FDE1B4F5AB` | AMBER | Redirect Q1 disease-awareness spend to the six highest-gap provinces; brief field medical on GP referral pathways | Medical Affairs | +1 quarter |
| L-02 | **39.2%** of severe patients (n=7,044) have no systemic or advanced therapy on record; the gradient runs from **37.4%** (AB) to **50.0%** (PE) | `M12` · `CH-2CD6C63C8673` | GREEN | Prioritise territory expansion into Atlantic Canada and the Prairies ahead of urban Ontario | Launch Excellence | +2 quarters |
| L-03 | Uninsured patients initiate advanced therapy at **3.8%** vs **10.0%** public — a **2.6×** access gap | `M03` · `CH-…insurance_type` | GREEN | Expand patient-support affordability programme; add to payer negotiation dossier | Market Access | +1 quarter |
| L-04 | First-year PDC is **0.66**, but the figure is depressed by DQ-01 (7.05% of fills missing `days_supply`) | `M06` · `CH-A98871FFD11F` | AMBER | **No decision taken.** Remediation HEL-61 raised; re-review once DQ-01 ≤ 2% | Patient Support | On remediation |
| L-05 | Registry-derived quality of life **cannot be published**: registry covers rural patients at 0.41× the spine, and 55 rows were retained after consent withdrawal | `M13` · blocked | RED | Payer dossier humanistic-burden chapter deferred; HEL-62 weighting and HEL-65 purge raised | HEOR + Privacy | On remediation |
| L-06 | Brand share of new starts is rising, but the two most recent months are understated by pharmacy claim run-off | `M04` · `CH-A98871FFD11F` | AMBER | Monthly review reads the **trailing 3-month average**, never the last bar | Launch Excellence | Standing |
| L-07 | QC is structurally 62 days stale versus other provinces | `DQ-05` | n/a | QC excluded from month-on-month provincial comparisons until re-contracted (HEL-66) | Data Sourcing | +1 quarter |

### 3.1 L-04 and L-05 are the important rows

Two of seven ledger entries record a **decision not to decide**. That is the
framework working as designed: the alternative — an adherence figure quoted in
a business case while a known 7% data defect biases it downward, or a
quality-of-life claim drawn from a population that under-represents rural
patients by 59% — is precisely how analytics loses credibility.

"We cannot answer this yet, here is what would have to change, here is who
owns it" is a deliverable.

---

## 4. Product operating KPIs

Measuring the product itself, not the launch.

| KPI | Definition | Current | Target |
|---|---|---|---|
| Answer rate | Answered ÷ asked | ~69% | 60–80% |
| Groundedness | Verified claims ÷ total claims | 1.00 | ≥ 0.99 |
| Safety violations | Individual-level questions answered | 0 | 0 |
| p95 latency | End-to-end | ~1.35 s | < 3 s |
| Citation coverage | Published figures carrying a cohort hash | 100% | 100% |
| Band coverage | Published figures carrying an FFU band | 100% | 100% |
| RED-band metrics | Count blocked from publication | 1 of 13 | Trend down |
| Refusal→registration | Refusals converted into new governed metrics | — | ≥ 1 / sprint |
| Ledger entries | Decisions traced to a cited insight | 7 | ≥ 20 over 2 quarters |

---

## 5. Monthly launch review — proposed agenda

The reason the product exists is to change what this meeting spends time on.

| Time | Item | Source |
|---|---|---|
| 0–5 min | Trust check: DQ score, band mix, anything newly RED | Dashboard, Data Quality tab |
| 5–15 min | KPI tree against plan, Green and Amber only | Dashboard, Launch tab |
| 15–30 min | One deep dive, live, via the agent | Agent tab |
| 30–40 min | Ledger review: decisions due for outcome review | This document, §3 |
| 40–50 min | Remediation backlog and what it would unblock | Doc 02, §8 |

The first item is deliberately first. Starting a review by agreeing what the
data can currently support removes the forty minutes previously spent
discovering mid-meeting that two people are quoting different numbers.
