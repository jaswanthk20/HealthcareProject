# HELIOS — Process Flows & Architecture

Diagrams are Mermaid and render in Confluence, GitHub and the published
dashboard.

---

## 1. End-to-end data and decision flow

```mermaid
flowchart LR
  subgraph SRC["Contracted sources"]
    A1["PBM pharmacy claims<br/>lag 9d"]
    A2["Private payer medical<br/>lag 21d"]
    A3["QC provincial admin<br/>lag 62d"]
    A4["Ambulatory EHR<br/>lag 3d"]
    A5["Consented registry<br/>lag 45d"]
  end

  subgraph PLAT["HELIOS platform"]
    B["Patient spine<br/>linkage + harmonisation"]
    C["Data quality engine<br/>15 checks / 13 dimensions"]
    D["Semantic layer<br/>13 metrics, 8 dimensions"]
    E["Cohort compiler<br/>parameterised, hashed"]
    F["Metric engine<br/>+ small-cell suppression"]
    G["Fitness-for-Use gate<br/>question-scoped"]
  end

  subgraph OUT["Consumption"]
    H["Insight agent<br/>NL question in"]
    I["Launch dashboard"]
    J["Insight-to-decision ledger"]
  end

  A1 & A2 & A3 & A4 & A5 --> B --> C
  C --> G
  B --> E --> F --> G
  D --> E
  D --> H
  G --> H --> J
  G --> I --> J
```

---

## 2. The agent request pipeline — every gate that can stop an answer

```mermaid
flowchart TD
  Q["Stakeholder question"] --> G0{"Gate 0<br/>Scope guard"}
  G0 -->|"individual-level<br/>or off-purpose"| R1["REFUSE<br/>categorical"]
  G0 -->|ok| RET["Retrieve governed<br/>semantic layer (BM25)"]
  RET --> PLAN["Plan<br/>metric + cohort + break-out"]
  PLAN --> G1{"Gate 1<br/>Bound to a<br/>governed metric?"}
  G1 -->|no| R2["REFUSE<br/>out of scope + how to register it"]
  G1 -->|yes| VAL["Validate plan<br/>drop ungoverned values"]
  VAL --> SQL["Compile parameterised SQL<br/>cohort_hash assigned"]
  SQL --> EXEC["Execute (read-only)"]
  EXEC --> SUP{"Privacy<br/>cell ≥ minimum?"}
  SUP -->|no| SUPP["SUPPRESS cell<br/>+ complementary suppression"]
  SUP -->|yes| G2
  SUPP --> G2{"Gate 2<br/>Fitness-for-Use<br/>for THIS question"}
  G2 -->|RED| R3["REFUSE<br/>not fit + named remediation"]
  G2 -->|GREEN / AMBER| NAR["Narrate from<br/>executed values only"]
  NAR --> SCRUB["Scrub identifiers"]
  SCRUB --> G3{"Gate 3<br/>Every number traced<br/>to an executed query?"}
  G3 -->|no| R4["BLOCK<br/>unverified claim + log"]
  G3 -->|yes| ANS["ANSWER<br/>+ band + citations + caveat"]
  R1 & R2 & R3 & R4 & ANS --> TEL["Telemetry<br/>with cohort hash"]

  style R1 fill:#7f1d1d,color:#fff
  style R2 fill:#7f1d1d,color:#fff
  style R3 fill:#7f1d1d,color:#fff
  style R4 fill:#7f1d1d,color:#fff
  style ANS fill:#14532d,color:#fff
```

**The point of the diagram:** four of the five terminal states are refusals.
That ratio is deliberate. A product that answers everything is a product that
answers some things wrongly.

---

## 3. Fitness-for-Use scoring

```mermaid
flowchart TD
  M["Metric + Cohort<br/>(one business question)"] --> A["Asset quality 60%<br/>only the DQ dimensions<br/>this metric depends on"]
  M --> B["Cohort sufficiency 25%<br/>denominator vs the grain's<br/>stability floor"]
  M --> C["Governance 15%<br/>licence, consent,<br/>source availability"]
  A --> S["Weighted score"]
  B --> S
  C --> S
  S --> V{"Veto rules"}
  V -->|"V1 critical dimension < 25"| RED["RED — blocked"]
  V -->|"V2 critical governance failure<br/>in a source this metric reads"| RED
  V -->|"V3 denominator below minimum cell"| RED
  V -->|"V4 licence expired"| RED
  V -->|none| BAND{"Score"}
  BAND -->|"≥ 75"| GREEN["GREEN<br/>decision-grade"]
  BAND -->|"50–74"| AMBER["AMBER<br/>directional, caveat attached"]
  BAND -->|"< 50"| RED

  style GREEN fill:#14532d,color:#fff
  style AMBER fill:#78350f,color:#fff
  style RED fill:#7f1d1d,color:#fff
```

**Why vetoes rather than a pure weighted score:** some failures are not
tradeable against a good average. A consent breach is not offset by excellent
completeness. A score alone would let it be.

---

## 4. Requirements traceability

```mermaid
flowchart LR
  SH["Stakeholder need"] --> BQ["Business question<br/>BQ-01…BQ-08"]
  BQ --> MET["Governed metric<br/>M01…M13"]
  MET --> DQ["Critical DQ dimensions"]
  DQ --> FFU["FFU band"]
  FFU --> INS["Published insight<br/>+ cohort hash"]
  INS --> DEC["Logged decision<br/>+ KPI"]
  DEC -.->|"outcome review"| SH

  style INS fill:#1e3a5f,color:#fff
  style DEC fill:#1e3a5f,color:#fff
```

Both ends are machine-readable, so the chain can be walked in either
direction — from a decision back to the patients behind it, or from a data
defect forward to every decision it touches. The second direction is the one
that matters when a defect is found late.

---

## 5. Governance: what happens when a check fails

```mermaid
sequenceDiagram
  participant DQ as DQ engine
  participant FFU as FFU gate
  participant BA as Business Analyst
  participant ENG as Data Engineering
  participant PO as Product Owner
  participant PRIV as Privacy Office

  DQ->>DQ: Nightly run, 15 checks
  DQ->>FFU: Dimension scores
  FFU->>FFU: Re-score every metric × cohort
  alt Band degrades to RED
    FFU->>PO: Metric blocked from publication
    PO->>BA: Assess decision exposure
    BA->>BA: Which live insights used this metric?
    BA->>ENG: Raise remediation with impact + owner
    ENG->>DQ: Fix, re-run
  else Critical governance failure
    FFU->>PRIV: Incident raised (e.g. consent withdrawal)
    PRIV->>ENG: Purge required within SLA
    PRIV->>PO: Confirm no published insight is affected
  else Licence within 90 days of expiry
    FFU->>PO: Renewal warning
    PO->>BA: Confirm which metrics lose their source
  end
```

---

## 6. Sprint operating rhythm

```mermaid
flowchart LR
  A["Stakeholder<br/>question intake"] --> B["BA: is this a<br/>registered question?"]
  B -->|yes| C["Answer via agent<br/>minutes"]
  B -->|no| D["Refinement:<br/>new metric?"]
  D --> E["BA writes definition,<br/>caveat, decision, owner"]
  E --> F["Engineering writes SQL"]
  F --> G["BA adds ≥2 golden cases"]
  G --> H["Release gate"]
  H -->|pass| I["Ship + regenerate<br/>dictionary"]
  H -->|fail| D
  I --> C
```

The loop that matters is `B → D → E`: an unanswerable question is not a
failure, it is the intake mechanism for the next metric. The refusal text
tells the user exactly that.
