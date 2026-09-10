# HELIOS — Privacy, Regulatory & Security Controls

Scope: data privacy (PIPEDA / provincial health privacy law / GDPR where EU
data is in scope), GxP data integrity (ALCOA+), SOX where figures feed
financial reporting, and cybersecurity controls for an AI-enabled product.

> Synthetic data throughout. This documents the control design, which is what
> transfers to a real deployment.

---

## 1. Control principle

**Controls sit where the data is produced, not where it is displayed.**

A suppression rule enforced in a dashboard is not a control — it is a
convention, and it is bypassed the moment someone exports to Excel, hits the
API, or asks the agent the same question a different way. Every control below
is enforced in the engine, so every consumption path inherits it.

---

## 2. Data privacy controls

| ID | Control | Implementation | Evidence |
|---|---|---|---|
| P1 | Primary small-cell suppression | Denominator < 11 → suppressed before a value is computed | `privacy.check_cell`; guardrail test 4 |
| P2 | Numerator suppression | Non-zero numerator < 11 suppressed even at a large denominator | `privacy.check_cell` |
| P3 | Complementary suppression | One suppressed cell in a break-out → next-smallest also suppressed | `privacy.apply_complementary` |
| P4 | Consent enforcement | `consent_flag = 0` excluded at the cohort layer, not the report layer | M13 SQL; DQ-15 |
| P5 | Suppression audit | Every decision logged with rule id, detail, cohort hash, UTC timestamp | `privacy.audit_log()` |
| P6 | Identifier scrubbing | Patient ids, postal codes, emails, long numerics removed from generated text | `privacy.scrub`; guardrail test 6 |
| P7 | Categorical scope guard | Individual-level questions refused before planning, regardless of data | `llm.scope_violation`; G16–G19 |
| P8 | Data minimisation | Year of birth only; no full DOB; no direct identifiers ingested | `patient` schema |
| P9 | Purpose limitation | Metric registry defines permitted purposes; no ad-hoc SQL path for users | `semantic_layer` |
| P10 | Re-identification prohibition | Explicit refusal pattern; contractual basis cited in the response | `OUT_OF_SCOPE_PATTERNS` |

### 2.1 P2 in particular

P2 is the control teams most often omit. A rate of 3/900 has a comfortable
denominator and still identifies three people in a small geography. Reviewing
the denominator alone is not sufficient, and the numerator check is what makes
break-outs safe to publish at all.

### 2.2 P3 in particular

If a break-out has eleven provinces and exactly one is suppressed, the
suppressed value is recoverable by subtracting the ten published cells from
the published total. P3 suppresses a second cell to break the arithmetic.
Suppressing the smallest survivor minimises the information lost.

---

## 3. GxP data integrity — ALCOA+

| Principle | How HELIOS satisfies it |
|---|---|
| **Attributable** | Every telemetry event records the question, planner, metric and cohort hash |
| **Legible** | Metric definitions are human-readable prose alongside their SQL; the dictionary is generated from them |
| **Contemporaneous** | Events are written at execution with a UTC timestamp; DQ snapshots are timestamped per run |
| **Original** | Source rows are never mutated — the warehouse is read-only at the access layer (`ReadOnlyViolation`) |
| **Accurate** | Numeric verification blocks any published figure not traceable to an executed query |
| **Complete** | Refusals and blocks are logged as first-class events, not discarded |
| **Consistent** | A cohort hash re-executes to the same value; the semantic layer is version-stamped |
| **Enduring** | Telemetry and DQ snapshots persist independently of the warehouse |
| **Available** | Any published figure can be reconstructed from metric id + cohort hash + layer version |

**Computer System Validation.** The golden set and the adversarial suite are
the executable evidence for IQ/OQ/PQ: requirements trace to acceptance
criteria (doc 02), criteria trace to automated cases, cases run in the release
gate. A validation pack is assembled from artefacts the team already
maintains, rather than written separately and allowed to go stale.

---

## 4. SOX considerations

Where HELIOS figures inform revenue forecasting or accruals:

| Risk | Control |
|---|---|
| Unauthorised change to a metric definition | Definitions are version-controlled code; changes require review and a regenerated dictionary |
| Figure cannot be reproduced at audit | Cohort hash + metric id + layer version reproduce it exactly |
| Undisclosed data limitation in a reported figure | Caveat text is mandatory metadata and travels with the figure |
| Stale source presented as current | DQ-05 timeliness; publication lag published beside every source |
| Use of an out-of-contract source | DQ-13 licence horizon; FFU veto V4 blocks publication |

---

## 5. Cybersecurity controls for the AI feature

| Threat | Control | Evidence |
|---|---|---|
| Prompt injection to exfiltrate data | Model emits a closed plan object; every field validated against an enum; no model output reaches a SQL string | Guardrail test 3 |
| SQL injection through question text | Cohort compiler binds all values as parameters; ungoverned values raise `CohortError` | Guardrail test 2 |
| Destructive query | Read-only guard rejects write statements at the access layer | `db.ReadOnlyViolation` |
| Data exfiltration via break-out fan-out | Small-cell policy applies per cell; complementary suppression prevents recovery | P1–P3 |
| Model unavailability / degraded output | Deterministic planner as default and fallback; failure recorded, never silent | `ClaudePlanner` fallback |
| Excessive resource consumption | Row limits on every query; queries and rows scanned recorded per answer | `Warehouse.query` |
| Secrets in code | Credentials resolved from the environment; nothing hardcoded | `llm.ClaudePlanner` |

### 5.1 Why "the model never writes SQL" is the load-bearing control

Every other guardrail is defence in depth. This one is structural: if the
model cannot express a query, there is no query for an attacker to influence.
The plan object has five fields, three of which are closed enums drawn from
the semantic layer, and the remaining two are free text used only for display.
The attack surface is the enum, and the enum is thirteen metric names.

---

## 6. Roles

| Role | Accountable for |
|---|---|
| Data Privacy Officer | Minimum cell size policy; consent enforcement; incident response |
| RWD Data Sourcing & Contracts | Licence validity; consent basis per source; renewal before expiry |
| Metric business owner | Definition, caveat, permitted-use judgement for their metric |
| RWD & HI Product Owner | Release gate decision; remediation prioritisation |
| **Business Analyst** | Requirement traceability; business impact and remediation on every DQ check; golden-set maintenance; **exposure assessment when a metric degrades** |
| Data Engineering | Pipeline controls; remediation delivery; read-only enforcement |
| Quality / CSV | Validation pack; periodic review |

---

## 7. Incident response — worked example

**DQ-15 detects 55 registry rows retained after consent withdrawal.**

| Step | Action | Owner | Timing |
|---|---|---|---|
| 1 | Check fails at critical severity; FFU veto V2 fires | Platform | Automatic, nightly |
| 2 | Every registry-derived metric blocked from publication | Platform | Immediate |
| 3 | Privacy incident raised | Privacy Office | Same day |
| 4 | **Exposure assessment: which published insights used a registry metric?** — answered from cohort hashes in telemetry | **BA** | Same day |
| 5 | Purge job executed; withdrawal honoured | Data Engineering | Per SLA |
| 6 | Re-run confirms zero retained rows; veto clears | Platform | Next run |
| 7 | Withdrawal purge added to every registry refresh | Data Engineering | Sprint |
| 8 | Golden case added asserting the block | BA | Sprint |

Step 4 is the one that is hard without design for it. "Which decisions rest on
this data?" is only answerable because every published figure carries a cohort
hash and every answer is logged. **Traceability is not documentation overhead;
it is the thing that makes an incident bounded.**

Note that in the live run this breach correctly blocks `M13` and correctly
leaves the twelve claims-derived metrics running — an incident should stop the
affected work, not all work.
