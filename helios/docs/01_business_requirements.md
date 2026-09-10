# HELIOS — Business Requirements Document

**Product line:** Digital Real-World Data & Healthcare Intelligence (RWD & HI)
**Product:** HELIOS — Healthcare Evidence & Launch Intelligence Operating System
**Author:** RWD & HI Business Analyst
**Version:** 1.3 · Status: Approved for build · Reference case: R2870471

> All data, brands and organisations in this document are synthetic.
> **SANOVIA** is an invented IL-4R-class biologic used as the launch brand.

---

## 1. The problem, stated as the business feels it

A launch review happens monthly. Ten people in a room, each with a deck. The
brand lead has an uptake number from the PBM extract. Market access has a
different uptake number because they filtered to reimbursed lives. Medical
Affairs has a time-to-diagnosis figure from a registry analysis nobody can
re-run. Somebody asks "which of these is right?" and the honest answer is
that all three are correct answers to three different questions that were
never written down.

The cost is not the analyst time. It is that **the meeting spends its first
forty minutes reconciling numbers instead of making a decision**, and that
when a decision does get made, nobody can later reconstruct which data it
rested on.

Three failures sit underneath this:

| # | Failure | What it looks like in the room |
|---|---|---|
| F1 | **No governed definition.** "Uptake", "persistence", "new patient" mean different things per team. | Three uptake numbers, none reproducible. |
| F2 | **Data quality is assessed globally, not per question.** A dataset is "good" or "bad" in the abstract. | A 40% lab-missingness rate blocks a launch trend it has no bearing on, while a genuinely unusable registry figure sails into a payer deck. |
| F3 | **No traceability from a number to the patients behind it.** | Six months later nobody can re-run the figure that justified the investment. |

## 2. Why an AI product, and where AI must *not* be trusted

The team wants natural-language access — "just ask it". That is the right
interface and the wrong place to put the trust boundary.

A language model is excellent at **understanding what a stakeholder means**
and unreliable at **producing a number**. HELIOS is built on that split:

- The model may **choose a governed metric and a cohort**. It is a router.
- The model may **never emit SQL, and never state a figure.** Every number is
  computed by executing a version-controlled SQL definition, and every number
  in the final text is re-checked against those executed results before display.

This is what makes the product safe to point at patient data, and it is the
design decision the rest of this document follows from.

## 3. Stakeholders

| Stakeholder | What they need | The question they open with | Success for them |
|---|---|---|---|
| Launch Excellence Lead | Is uptake on curve, and where is it not? | "Are we tracking to plan?" | Course-corrects in-month rather than next quarter |
| Medical Affairs Director | Where is the diagnostic and referral pathway failing patients? | "How long are people waiting?" | Targets field-medical effort at the worst-served geographies |
| Market Access Lead | Does payer channel gate access? | "Is public formulary lag real and how big?" | Evidence-backed negotiation position |
| HEOR Lead | What burden can we credibly claim we reduce? | "What does this cost the system today?" | Defensible dossier figures with stated limitations |
| Patient Support Lead | Where does adherence actually break? | "Do patients stay on therapy?" | Programme designed against a real drop-off point |
| Data Privacy Officer | Can a figure re-identify anyone? | "Prove the small-cell policy is enforced." | Suppression provable at the engine, not the report |
| Product Owner (RWD & HI) | Is the AI feature good enough to ship? | "What is your groundedness on the golden set?" | A release gate with numbers, not vibes |

### 3.1 Signals taken from requirement workshops

Verbatim points that shaped scope. Each maps to a requirement.

- *"I don't need it to be clever, I need it to be the same number twice."* → FR-02, FR-08
- *"If the data can't answer it, I would much rather it said so."* → FR-06, FR-07
- *"The last tool gave me a confident number from 4 patients."* → FR-09
- *"Don't make me read a data-quality report to find out if I can use a chart."* → FR-05
- *"Legal will ask where this came from. I need an answer that isn't 'the system said so'."* → FR-08
- *"Half our questions are really about rural access and nobody ever looks at it."* → FR-04, KPI-07

## 4. Scope

### In scope (v1)
1. A governed semantic layer: metric definitions, dimensions, table contracts, registered business questions.
2. A natural-language insight agent restricted to that layer.
3. A data-quality engine across conformance, completeness, plausibility, timeliness, coverage, linkage, referential integrity, representativeness and governance.
4. **Question-scoped Fitness-for-Use scoring** with a publication gate.
5. Privacy-by-construction: small-cell suppression inside the metric engine.
6. Numeric-claim verification on all generated text.
7. Telemetry and an evaluation suite with an automated release gate.
8. A launch-intelligence dashboard.

### Explicitly out of scope (v1)
- Prescriber-level targeting or ranking — governed separately, refused categorically.
- Patient-level output of any kind.
- Individual patient prediction (clinical decision support — different regulatory basis).
- Promotional content generation.
- Write-back to source systems.
- Causal inference or comparative-effectiveness claims. HELIOS describes; it does not conclude.

## 5. Functional requirements

| ID | Requirement | Priority | Verified by |
|---|---|---|---|
| FR-01 | Ingest and link claims, EHR and registry data into a patient spine with documented lineage. | Must | `generate_rwd.py`, DQ-11 linkage |
| FR-02 | Every metric has exactly one governed definition, an owner, a decision it supports and a caveat. | Must | `semantic_layer.py`, generated dictionary |
| FR-03 | Users ask in natural language; the system resolves to a governed metric and cohort. | Must | Golden set G01–G14 |
| FR-04 | Any result can be broken out by any governed dimension, with each cell independently citable. | Must | `compute_by`, G03/G23/G25/G26 |
| FR-05 | Every answer carries a Fitness-for-Use band scoped to that question, with permitted use stated in plain language. | Must | `ffu.py`, G15 |
| FR-06 | The system refuses when no governed metric fits, and says what would have to change. | Must | G20, G21 |
| FR-07 | The system refuses categorically for individual-level questions, regardless of data availability. | Must | G16–G19, guardrail test 5 |
| FR-08 | Every figure carries a cohort hash that re-executes to the same number. | Must | `cohort.hash()`, citations |
| FR-09 | No cell below the minimum size is ever released; complementary suppression prevents recovery by subtraction. | Must | `privacy.py`, guardrail test 4 |
| FR-10 | Every number in generated text is verified against executed results before display; failures block. | Must | `verifier.py`, guardrail test 1 |
| FR-11 | Telemetry captures intent, latency by stage, groundedness, band mix, cost and cohort hash. | Must | `telemetry.py` |
| FR-12 | A golden-set evaluation gates release on routing, refusal, safety, groundedness and latency. | Must | `evals.py` |
| FR-13 | Data dictionary is generated from the semantic layer, never hand-maintained. | Should | `generate_docs.py` |
| FR-14 | Licence expiry and consent withdrawal block publication from the affected source. | Must | DQ-13, DQ-15, FFU veto V2/V4 |
| FR-15 | Planner is swappable between a deterministic engine and an LLM without changing guarantees. | Should | `llm.py` |

## 6. Non-functional requirements

| ID | Requirement | Target | Measured |
|---|---|---|---|
| NFR-01 | Interactive latency for a single-metric question | p95 < 3 s | p95 ≈ 1.3–1.5 s |
| NFR-02 | Groundedness of published numeric claims | ≥ 0.99 | 1.00 on the golden set |
| NFR-03 | Safety violations (individual-level question answered) | 0 | 0 |
| NFR-04 | Reproducibility: same cohort hash returns the same value | 100% | Deterministic by construction |
| NFR-05 | Zero third-party runtime dependencies for the core | stdlib only | Met |
| NFR-06 | Degrade gracefully when the model is unavailable | Fall back to deterministic planner | `ClaudePlanner` fallback path |

## 7. Assumptions

1. Source data arrives de-identified; HELIOS never receives direct identifiers.
2. Minimum cell size of 11 patients is the agreed release policy and is configurable per market.
3. Dispensing is a proxy for treatment; free goods and hospital-supplied product are not visible.
4. The claims spine, not the registry, is the reference population for representativeness.
5. Severity is clinician-assigned where present and proxied by treatment intensity where absent.

## 8. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | A confident, wrong number reaches a governance forum | Medium | High | Numeric verification blocks display; FFU gate blocks unfit questions |
| R-02 | Users treat Amber figures as decision-grade | High | Medium | Permitted use printed with every answer, not buried in a footnote |
| R-03 | Small-cell recovery by subtraction across break-outs | Medium | High | Complementary suppression (P3) |
| R-04 | Registry selection bias generalised to the whole population | High | High | DQ-08 vetoes registry-derived metrics until weighted |
| R-05 | Prompt injection reaches the query layer | Low | High | Model emits a closed plan object, never SQL; all values bound |
| R-06 | Metric definitions drift from documentation | High | Medium | Dictionary generated from code |
| R-07 | Licence lapses and insights must be withdrawn | Medium | High | DQ-13 with a 90-day horizon; FFU veto V4 |
| R-08 | Model latency or outage breaks the product | Medium | Medium | Deterministic planner is the default and the fallback |

## 9. Success measures

| Measure | Baseline | Target (2 quarters) |
|---|---|---|
| Time from question asked to cited answer | 3–10 working days | < 1 minute |
| Reconciliation time at monthly launch review | ~40 min | < 5 min |
| Share of published figures carrying a cohort hash | 0% | 100% |
| Share of published figures carrying an FFU band | 0% | 100% |
| Decisions logged in the insight-to-decision ledger | 0 | ≥ 20 |
| Golden-set groundedness | n/a | ≥ 0.99 sustained |

## 10. Traceability

`Stakeholder need → Business question (BQ-nn) → Governed metric (Mnn) → DQ dimensions → FFU band → Decision (KPI-nn)`

Both ends are machine-readable: business questions live in
`semantic_layer.BUSINESS_QUESTIONS`, decisions in the insight ledger
(doc 08). The chain is walkable in either direction, which is what an audit
actually asks for.
