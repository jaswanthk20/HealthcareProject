"""
HELIOS - Synthetic Real-World Data Generator
=============================================
Generates a linked, longitudinal RWD environment for a fictional Type 2
inflammation (atopic dermatitis / severe asthma) franchise in Canada.

NOTHING HERE IS REAL. No real patient, provider, payer or product data is used.
The fictional launch brand is "SANOVIA" (an IL-4R-class biologic, invented).

The generator deliberately injects the data-quality defects that real RWD
assets exhibit, so the DQ / Fitness-for-Use engine has something true to find:

  D1  days_supply missing or zero on ~7% of pharmacy claims
  D2  ~2.5% service dates in the future (data-entry / ETL defect)
  D3  ~5% eosinophil counts submitted in the wrong unit (x1000)
  D4  ~40% lab missingness in EHR (normal for ambulatory EHR)
  D5  one source (PROV_ADMIN_QC) has a 62-day publication lag (staleness)
  D6  ~1.5% exact duplicate claim rows
  D7  sex coded inconsistently across sources (M/F vs 1/2 vs U)
  D8  registry under-covers rural patients (representativeness / selection bias)
  D9  ~1.2% of encounters dated before the patient birth year (plausibility)
  D10 ~3% orphan claims referencing a provider_id not in the provider table

Usage:  python data/generator/generate_rwd.py --out data/helios.db --patients 12000
"""

import argparse
import csv
import math
import os
import random
import sqlite3
from datetime import date, timedelta

SEED = 20260910
STUDY_START = date(2019, 1, 1)
STUDY_END = date(2026, 6, 30)
LAUNCH_DATE = date(2024, 9, 1)          # SANOVIA (fictional) Canadian launch
TODAY = date(2026, 9, 10)

PROVINCES = [
    ("ON", 0.386, 0.14), ("QC", 0.226, 0.19), ("BC", 0.135, 0.13),
    ("AB", 0.116, 0.16), ("MB", 0.036, 0.27), ("SK", 0.031, 0.33),
    ("NS", 0.026, 0.42), ("NB", 0.021, 0.48), ("NL", 0.013, 0.41),
    ("PE", 0.004, 0.53), ("TERR", 0.006, 0.68),
]  # (code, population share, rural share)

SOURCES = [
    # source_id, name, type, refresh_days, lag_days, geography, consent_basis, license_expiry
    ("CLM_NATL_PBM", "National PBM Pharmacy Claims", "pharmacy_claims", 7, 9,
     "CA-ALL", "contractual_deidentified", "2027-03-31"),
    ("CLM_PRIV_PAYER", "Private Payer Medical Claims", "medical_claims", 14, 21,
     "CA-ALL", "contractual_deidentified", "2026-12-31"),
    ("PROV_ADMIN_QC", "Provincial Administrative Claims (QC)", "medical_claims", 30, 62,
     "CA-QC", "data_sharing_agreement", "2027-06-30"),
    ("EHR_AMBULATORY", "Ambulatory EHR Network", "ehr", 1, 3,
     "CA-ALL", "broad_consent", "2028-01-31"),
    ("REG_T2INFLAM", "Type 2 Inflammation Patient Registry", "registry", 90, 45,
     "CA-ALL", "explicit_informed_consent", "2027-09-30"),
]

# --- Clinical vocabulary (ICD-10-CA style, illustrative) --------------------
DX_SYMPTOM = ["L29.9", "R06.02", "J45.909", "L20.84", "R05"]
DX_AD_CONFIRMED = ["L20.89", "L20.9", "L20.81"]
DX_ASTHMA_SEVERE = ["J45.50", "J45.51", "J45.52"]
DX_COMORBID = ["J30.1", "J33.9", "K21.9", "F32.9", "G47.00", "J31.0"]

PROC_CODES = {
    "office_visit": "A005", "specialist_consult": "A605", "allergy_test": "G202",
    "spirometry": "J301", "phototherapy": "G470", "ed_visit": "H101",
    "inpatient_day": "C002", "biologic_admin": "G372",
}

DRUGS = [
    # drug_name, class, line, days_supply, monthly_cost, is_launch_brand
    ("TOPICAL_CORTICOSTEROID", "topical_cs", 1, 30, 42.0, 0),
    ("TOPICAL_CALCINEURIN_INH", "topical_tci", 1, 30, 96.0, 0),
    ("ORAL_CORTICOSTEROID", "systemic_cs", 2, 14, 18.0, 0),
    ("CYCLOSPORINE", "systemic_ist", 2, 30, 180.0, 0),
    ("METHOTREXATE", "systemic_ist", 2, 30, 55.0, 0),
    ("ICS_LABA_COMBO", "inhaled_controller", 1, 30, 120.0, 0),
    ("DUPILUMAB_CLASS_A", "biologic_il4r", 3, 28, 1750.0, 0),
    ("SANOVIA", "biologic_il4r", 3, 28, 1690.0, 1),          # fictional launch brand
    ("BIOLOGIC_IL13", "biologic_il13", 3, 28, 1820.0, 0),
    ("BIOLOGIC_IL5", "biologic_il5", 3, 28, 1610.0, 0),
    ("JAK_INHIBITOR_ORAL", "jak", 3, 30, 1450.0, 0),
]

SPECIALTIES = [("GP", 0.52), ("DERM", 0.18), ("RESP", 0.12),
               ("ALLERGY", 0.09), ("PEDS", 0.06), ("IM", 0.03)]


def wchoice(rng, pairs):
    r = rng.random()
    acc = 0.0
    for item in pairs:
        acc += item[1]
        if r <= acc:
            return item[0]
    return pairs[-1][0]


def rand_date(rng, start, end):
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, max(delta, 1)))


DDL = """
CREATE TABLE source_metadata (
  source_id TEXT PRIMARY KEY, source_name TEXT, source_type TEXT,
  refresh_cadence_days INTEGER, publication_lag_days INTEGER,
  geography TEXT, consent_basis TEXT, license_expiry TEXT,
  last_refresh_date TEXT, record_count INTEGER
);

CREATE TABLE provider (
  provider_id TEXT PRIMARY KEY, specialty TEXT, province TEXT,
  practice_setting TEXT, annual_patient_volume INTEGER, is_academic INTEGER
);

CREATE TABLE patient (
  patient_id TEXT PRIMARY KEY, birth_year INTEGER, sex TEXT, sex_raw TEXT,
  province TEXT, rurality TEXT, insurance_type TEXT,
  enrollment_start TEXT, enrollment_end TEXT,
  index_dx_date TEXT, first_symptom_date TEXT,
  severity TEXT, primary_condition TEXT, source_id TEXT
);

CREATE TABLE claim_medical (
  claim_id TEXT, patient_id TEXT, service_date TEXT, provider_id TEXT,
  dx_code TEXT, proc_code TEXT, place_of_service TEXT,
  paid_amount REAL, source_id TEXT, ingest_date TEXT
);

CREATE TABLE claim_pharmacy (
  rx_id TEXT, patient_id TEXT, fill_date TEXT, provider_id TEXT,
  drug_name TEXT, drug_class TEXT, days_supply INTEGER, quantity REAL,
  paid_amount REAL, source_id TEXT, ingest_date TEXT
);

CREATE TABLE ehr_encounter (
  encounter_id TEXT, patient_id TEXT, encounter_date TEXT, provider_id TEXT,
  encounter_type TEXT, easi_score REAL, eosinophil_count REAL, ige_level REAL,
  fev1_pct_predicted REAL, has_clinical_note INTEGER, source_id TEXT, ingest_date TEXT
);

CREATE TABLE registry_enrollment (
  registry_row_id TEXT, patient_id TEXT, registry_name TEXT, enroll_date TEXT,
  severity_at_enroll TEXT, biologic_naive INTEGER, consent_flag INTEGER,
  pro_dlqi_score REAL, source_id TEXT, ingest_date TEXT
);

CREATE INDEX ix_cm_pat ON claim_medical(patient_id);
CREATE INDEX ix_cm_dt  ON claim_medical(service_date);
CREATE INDEX ix_cp_pat ON claim_pharmacy(patient_id);
CREATE INDEX ix_cp_dt  ON claim_pharmacy(fill_date);
CREATE INDEX ix_cp_drug ON claim_pharmacy(drug_name);
CREATE INDEX ix_eh_pat ON ehr_encounter(patient_id);
CREATE INDEX ix_rg_pat ON registry_enrollment(patient_id);

-- Cohort filtering happens on every single query, and a break-out runs the
-- metric once per dimension value, so these carry the interactive latency.
CREATE INDEX ix_pt_prov ON patient(province);
CREATE INDEX ix_pt_sev  ON patient(severity);
CREATE INDEX ix_pt_rur  ON patient(rurality);
CREATE INDEX ix_pt_ins  ON patient(insurance_type);
CREATE INDEX ix_pt_cond ON patient(primary_condition);
CREATE INDEX ix_pt_dx   ON patient(index_dx_date);

-- Covering indexes for the advanced-therapy and utilisation predicates.
CREATE INDEX ix_cp_class_pat ON claim_pharmacy(drug_class, patient_id, fill_date);
CREATE INDEX ix_cm_proc_pat  ON claim_medical(proc_code, patient_id);
"""

TABLES = ["patient", "claim_medical", "claim_pharmacy", "ehr_encounter",
          "registry_enrollment", "provider", "source_metadata"]


def build(n_patients, out_path, csv_dir=None):
    rng = random.Random(SEED)
    if os.path.exists(out_path):
        os.remove(out_path)
    con = sqlite3.connect(out_path)
    con.executescript(DDL)

    # ------------------------------------------------------------ providers
    providers = []
    n_prov = max(400, n_patients // 18)
    for i in range(n_prov):
        spec = wchoice(rng, SPECIALTIES)
        prov = wchoice(rng, [(p[0], p[1]) for p in PROVINCES])
        setting = rng.choices(["community", "hospital", "academic"], [0.66, 0.24, 0.10])[0]
        providers.append((f"PRV{i:06d}", spec, prov, setting,
                          max(50, int(rng.gauss(1400, 520))), 1 if setting == "academic" else 0))
    con.executemany("INSERT INTO provider VALUES (?,?,?,?,?,?)", providers)
    prov_by_province = {}
    for p in providers:
        prov_by_province.setdefault(p[2], []).append(p)

    patients, med, rx, enc, reg = [], [], [], [], []
    ctr = {"m": 0, "r": 0, "e": 0, "g": 0}
    rural_share = {p[0]: p[2] for p in PROVINCES}

    for i in range(n_patients):
        pid = f"PT{i:07d}"
        province = wchoice(rng, [(p[0], p[1]) for p in PROVINCES])
        rurality = "rural" if rng.random() < rural_share[province] else "urban"

        primary = rng.choices(["atopic_dermatitis", "severe_asthma", "both"],
                              [0.55, 0.33, 0.12])[0]
        birth_year = int(rng.triangular(1945, 2020, 1985))
        sex_true = rng.choices(["F", "M"], [0.54, 0.46])[0]

        src_pat = rng.choices(["CLM_PRIV_PAYER", "PROV_ADMIN_QC", "EHR_AMBULATORY"],
                              [0.55, 0.20, 0.25])[0]
        if src_pat == "PROV_ADMIN_QC":                       # D7 conformance defect
            sex_raw = "2" if sex_true == "F" else "1"
        elif rng.random() < 0.03:
            sex_raw = "U"
        else:
            sex_raw = sex_true

        enroll_start = rand_date(rng, STUDY_START, date(2024, 6, 30))
        enroll_end = min(STUDY_END, enroll_start + timedelta(days=rng.randint(365, 2400)))
        severity = rng.choices(["mild", "moderate", "severe"], [0.46, 0.36, 0.18])[0]

        # ---- diagnostic odyssey: first symptom -> confirmed diagnosis ------
        first_symptom = rand_date(rng, enroll_start, min(enroll_end, date(2025, 6, 30)))
        base_lag = {"mild": 120, "moderate": 210, "severe": 260}[severity]
        if rurality == "rural":
            base_lag *= 1.55
        if province in ("MB", "SK", "NL", "NB", "PE", "TERR"):
            base_lag *= 1.18
        dx_lag = max(7, int(rng.gauss(base_lag, base_lag * 0.42)))
        index_dx = min(first_symptom + timedelta(days=dx_lag), enroll_end)

        insurance = rng.choices(["public", "private", "mixed", "uninsured"],
                                [0.44, 0.38, 0.15, 0.03])[0]

        patients.append((pid, birth_year, sex_true, sex_raw, province, rurality,
                         insurance, enroll_start.isoformat(), enroll_end.isoformat(),
                         index_dx.isoformat(), first_symptom.isoformat(),
                         severity, primary, src_pat))

        plist = prov_by_province.get(province) or providers
        usual_prov = rng.choice(plist)

        # ---- medical claims ------------------------------------------------
        n_visits = int(max(2, rng.gauss({"mild": 6, "moderate": 13, "severe": 26}[severity], 5)))
        for _ in range(n_visits):
            svc = rand_date(rng, first_symptom, enroll_end)
            if svc < index_dx:
                dx = rng.choice(DX_SYMPTOM)
            elif primary == "severe_asthma":
                dx = rng.choice(DX_ASTHMA_SEVERE + DX_COMORBID)
            else:
                dx = rng.choice(DX_AD_CONFIRMED + DX_COMORBID)

            spec_p = 0.34 if rurality == "urban" else 0.19   # rural specialist access gap
            pr = rng.choice(plist) if rng.random() < spec_p else usual_prov
            if severity == "severe" and rng.random() < 0.13:
                proc, pos, paid = PROC_CODES["ed_visit"], "ED", rng.uniform(340, 980)
            elif severity == "severe" and rng.random() < 0.05:
                proc, pos, paid = PROC_CODES["inpatient_day"], "INPATIENT", rng.uniform(1900, 6400)
            else:
                proc = PROC_CODES["specialist_consult"] if pr[1] != "GP" else PROC_CODES["office_visit"]
                pos, paid = "OFFICE", rng.uniform(38, 165)

            src = "PROV_ADMIN_QC" if province == "QC" and rng.random() < 0.7 else "CLM_PRIV_PAYER"
            lag = 62 if src == "PROV_ADMIN_QC" else 21       # D5 staleness
            if rng.random() < 0.025:                          # D2 future dates
                svc = TODAY + timedelta(days=rng.randint(5, 400))
            if rng.random() < 0.012:                          # D9 pre-birth encounters
                svc = date(birth_year - rng.randint(1, 4), rng.randint(1, 12), 15)
            prov_ref = pr[0] if rng.random() > 0.03 else f"PRV9{rng.randint(10000, 99999)}"  # D10

            ctr["m"] += 1
            row = (f"CM{ctr['m']:09d}", pid, svc.isoformat(), prov_ref, dx, proc, pos,
                   round(paid, 2), src, (svc + timedelta(days=lag)).isoformat())
            med.append(row)
            if rng.random() < 0.015:                          # D6 duplicates
                med.append(row)

        # ---- treatment sequencing / pharmacy claims -------------------------
        def dispense(drug_name, start_dt, n_fills):
            """Emit a run of fills for one drug starting at start_dt."""
            spec = next(d for d in DRUGS if d[0] == drug_name)
            dclass, dsup, cost = spec[1], spec[3], spec[4]
            fill_dt = start_dt
            for _ in range(max(1, n_fills)):
                if fill_dt > enroll_end:
                    break
                ds = dsup
                if rng.random() < 0.07:                       # D1 days_supply defect
                    ds = 0 if rng.random() < 0.55 else None
                ctr["r"] += 1
                rx.append((f"RX{ctr['r']:09d}", pid, fill_dt.isoformat(), usual_prov[0],
                           drug_name, dclass, ds, float(rng.choice([1, 1, 1, 2, 3])),
                           round(cost * rng.uniform(0.85, 1.15), 2), "CLM_NATL_PBM",
                           (fill_dt + timedelta(days=9)).isoformat()))
                fill_dt += timedelta(days=dsup + int(abs(rng.gauss(3, 9))))  # adherence gap
            return fill_dt

        def pick_advanced(start_dt):
            """Brand choice as a function of time since the fictional launch."""
            if start_dt < LAUNCH_DATE:
                share = 0.0
            else:
                months = (start_dt - LAUNCH_DATE).days / 30.44
                share = 0.34 * (1 - math.exp(-months / 7.5))
                if rurality == "rural":
                    share *= 0.62
                if insurance == "public":
                    share *= 0.74                 # public formulary listing lag
            if rng.random() < share:
                return "SANOVIA"
            return rng.choices(
                ["DUPILUMAB_CLASS_A", "BIOLOGIC_IL13", "BIOLOGIC_IL5", "JAK_INHIBITOR_ORAL"],
                [0.46, 0.21, 0.19, 0.14])[0]

        # First line starts at diagnosis
        first_line = "ICS_LABA_COMBO" if primary == "severe_asthma" else "TOPICAL_CORTICOSTEROID"
        dispense(first_line, index_dx,
                 int(rng.gauss({"mild": 4, "moderate": 8, "severe": 12}[severity], 3)))

        # Second line: systemic escalation, much more likely when severe
        if severity in ("moderate", "severe"):
            p_systemic = 0.86 if severity == "severe" else 0.52
            if rng.random() < p_systemic:
                second = rng.choices(["ORAL_CORTICOSTEROID", "METHOTREXATE", "CYCLOSPORINE"],
                                     [0.48, 0.34, 0.18])[0]
            else:
                second = "TOPICAL_CALCINEURIN_INH"
            second_start = index_dx + timedelta(days=int(abs(rng.gauss(150, 90))) + 20)
            if second_start <= enroll_end:
                dispense(second, second_start,
                         int(rng.gauss({"mild": 3, "moderate": 6, "severe": 9}[severity], 3)))

        # Advanced therapy: timed off the diagnosis date, not chained off prior
        # lines, so escalation is not artificially pushed past the data window.
        escalates = False
        p_bio = {"mild": 0.03, "moderate": 0.19, "severe": 0.58}[severity]
        if insurance == "uninsured":
            p_bio *= 0.35
        if rurality == "rural":
            p_bio *= 0.78
        if rng.random() < p_bio:
            adv_start = index_dx + timedelta(days=max(45, int(rng.gauss(300, 170))))
            if adv_start <= enroll_end:
                escalates = True
                drug1 = pick_advanced(adv_start)
                n1 = int(rng.gauss(12.5 if drug1 == "SANOVIA" else 11, 4))
                # ~20% switch to a different advanced therapy within the year
                if rng.random() < 0.20:
                    switch_day = rng.randint(110, 330)
                    n1 = max(1, switch_day // 31)
                    dispense(drug1, adv_start, n1)
                    sw_start = adv_start + timedelta(days=switch_day)
                    if sw_start <= enroll_end:
                        drug2 = pick_advanced(sw_start)
                        while drug2 == drug1:
                            drug2 = pick_advanced(sw_start)
                        dispense(drug2, sw_start, int(rng.gauss(10, 4)))
                else:
                    dispense(drug1, adv_start, n1)

        # ---- EHR encounters --------------------------------------------------
        if rng.random() < 0.42:
            for _ in range(int(max(1, rng.gauss(7, 3)))):
                edt = rand_date(rng, index_dx, enroll_end)
                easi = None
                if primary != "severe_asthma" and rng.random() > 0.40:      # D4
                    base = {"mild": 6, "moderate": 15, "severe": 26}[severity]
                    easi = round(max(0, rng.gauss(base, 5)), 1)
                eos = None
                if rng.random() > 0.40:
                    eos = round(abs(rng.gauss(0.42, 0.25)), 3)
                    if rng.random() < 0.05:                                  # D3 unit error
                        eos = round(eos * 1000, 1)
                ige = round(abs(rng.gauss(310, 240)), 1) if rng.random() > 0.55 else None
                fev1 = None
                if primary in ("severe_asthma", "both") and rng.random() > 0.35:
                    fev1 = round(rng.gauss({"mild": 84, "moderate": 71, "severe": 58}[severity], 9), 1)
                ctr["e"] += 1
                enc.append((f"EN{ctr['e']:09d}", pid, edt.isoformat(), usual_prov[0],
                            rng.choice(["ambulatory", "follow_up", "telehealth", "urgent"]),
                            easi, eos, ige, fev1, 1 if rng.random() < 0.78 else 0,
                            "EHR_AMBULATORY", (edt + timedelta(days=3)).isoformat()))

        # ---- registry (D8: under-covers rural + mild) -------------------------
        p_reg = {"severe": 0.22, "moderate": 0.11, "mild": 0.035}[severity]
        if rurality == "rural":
            p_reg *= 0.38                                     # deliberate selection bias
        if rng.random() < p_reg:
            rdt = rand_date(rng, index_dx, enroll_end)
            ctr["g"] += 1
            reg.append((f"RG{ctr['g']:08d}", pid, "REG_T2INFLAM", rdt.isoformat(),
                        severity, 0 if escalates else 1,
                        1 if rng.random() < 0.985 else 0,
                        round(max(0, rng.gauss({"mild": 5, "moderate": 11, "severe": 19}[severity], 4)), 1),
                        "REG_T2INFLAM", (rdt + timedelta(days=45)).isoformat()))

    con.executemany("INSERT INTO patient VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", patients)
    con.executemany("INSERT INTO claim_medical VALUES (?,?,?,?,?,?,?,?,?,?)", med)
    con.executemany("INSERT INTO claim_pharmacy VALUES (?,?,?,?,?,?,?,?,?,?,?)", rx)
    con.executemany("INSERT INTO ehr_encounter VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", enc)
    con.executemany("INSERT INTO registry_enrollment VALUES (?,?,?,?,?,?,?,?,?,?)", reg)

    counts = {"CLM_NATL_PBM": len(rx), "EHR_AMBULATORY": len(enc), "REG_T2INFLAM": len(reg),
              "CLM_PRIV_PAYER": sum(1 for r in med if r[8] == "CLM_PRIV_PAYER"),
              "PROV_ADMIN_QC": sum(1 for r in med if r[8] == "PROV_ADMIN_QC")}
    con.executemany("INSERT INTO source_metadata VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [(s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7],
                      (TODAY - timedelta(days=s[4])).isoformat(), counts.get(s[0], 0))
                     for s in SOURCES])
    con.commit()

    if csv_dir:
        os.makedirs(csv_dir, exist_ok=True)
        for t in TABLES:
            cur = con.execute(f"SELECT * FROM {t}")
            with open(os.path.join(csv_dir, f"{t}.csv"), "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow([d[0] for d in cur.description])
                w.writerows(cur.fetchall())

    stats = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    con.close()
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/helios.db")
    ap.add_argument("--patients", type=int, default=12000)
    ap.add_argument("--csv", default=None, help="also export CSV extracts to this dir")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    s = build(a.patients, a.out, a.csv)
    print(f"[generator] wrote {a.out}")
    for k, v in s.items():
        print(f"  {k:22s} {v:>9,}")
