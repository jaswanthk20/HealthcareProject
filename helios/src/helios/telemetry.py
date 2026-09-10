"""
Telemetry for an AI-powered feature.

What gets logged is chosen to answer the four questions a product owner
actually asks about an AI feature in a regulated environment:

    Is it working?      intent distribution, refusal rate, verification rate
    Is it trusted?      FFU band mix, how often an answer is blocked and why
    Is it fast enough?  per-stage latency, not just total
    What does it cost?  tokens per answer, queries and rows scanned per answer

Every event carries the cohort_hash, so an answer that later turns out to be
wrong can be traced back to the exact patients and the exact metric version
that produced it. That traceability is the audit requirement, not a nice-to-have.
"""

import datetime
import json
import os
import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS agent_event (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, question TEXT, planner TEXT, intent TEXT,
  metric_id TEXT, cohort_hash TEXT, breakdown TEXT,
  ffu_score REAL, ffu_band TEXT, blocked INTEGER, block_reason TEXT,
  suppressed INTEGER,
  numeric_claims INTEGER, verified_claims INTEGER, groundedness REAL,
  ms_retrieval REAL, ms_plan REAL, ms_query REAL, ms_ffu REAL,
  ms_narrate REAL, ms_verify REAL, ms_total REAL,
  sql_queries INTEGER, rows_scanned INTEGER,
  input_tokens INTEGER, output_tokens INTEGER,
  validation_errors TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS dq_snapshot (
  ts TEXT, check_id TEXT, dimension TEXT, value REAL, score REAL, status TEXT
);
"""

DEFAULT_PATH = os.path.join("outputs", "telemetry.db")


class Telemetry:
    def __init__(self, path=DEFAULT_PATH):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(DDL)
        self.con.commit()

    def record(self, event):
        cols = [
            "ts", "question", "planner", "intent", "metric_id", "cohort_hash",
            "breakdown", "ffu_score", "ffu_band", "blocked", "block_reason",
            "suppressed", "numeric_claims", "verified_claims", "groundedness",
            "ms_retrieval", "ms_plan", "ms_query", "ms_ffu", "ms_narrate",
            "ms_verify", "ms_total", "sql_queries", "rows_scanned",
            "input_tokens", "output_tokens", "validation_errors", "error",
        ]
        event = dict(event)
        event.setdefault("ts", datetime.datetime.now(datetime.timezone.utc)
                         .isoformat(timespec="seconds"))
        if isinstance(event.get("validation_errors"), (list, tuple)):
            event["validation_errors"] = json.dumps(event["validation_errors"])
        self.con.execute(
            f"INSERT INTO agent_event ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})",
            [event.get(c) for c in cols])
        self.con.commit()

    def snapshot_dq(self, dq_results):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        self.con.executemany(
            "INSERT INTO dq_snapshot VALUES (?,?,?,?,?,?)",
            [(ts, r["check_id"], r["dimension"], r["value"], r["score"], r["status"])
             for r in dq_results])
        self.con.commit()

    # ------------------------------------------------------------ reporting
    def summary(self):
        row = self.con.execute("""
            SELECT COUNT(*) AS answers,
                   SUM(CASE WHEN intent='metric_query' THEN 1 ELSE 0 END) AS answered,
                   SUM(CASE WHEN intent='out_of_scope' THEN 1 ELSE 0 END) AS refused_scope,
                   SUM(CASE WHEN blocked=1 THEN 1 ELSE 0 END) AS blocked,
                   SUM(CASE WHEN suppressed=1 THEN 1 ELSE 0 END) AS suppressed,
                   ROUND(AVG(groundedness), 4) AS mean_groundedness,
                   SUM(numeric_claims) AS claims,
                   SUM(verified_claims) AS verified,
                   ROUND(AVG(ms_total), 1) AS mean_ms,
                   ROUND(AVG(rows_scanned), 0) AS mean_rows,
                   SUM(COALESCE(input_tokens,0)) AS in_tok,
                   SUM(COALESCE(output_tokens,0)) AS out_tok
              FROM agent_event""").fetchone()
        d = dict(row)
        p = self.con.execute("""
            SELECT ms_total FROM agent_event ORDER BY ms_total""").fetchall()
        if p:
            vals = [r["ms_total"] or 0 for r in p]
            d["p50_ms"] = round(vals[len(vals) // 2], 1)
            d["p95_ms"] = round(vals[min(len(vals) - 1, int(0.95 * len(vals)))], 1)
        d["verification_rate"] = (round(d["verified"] / d["claims"], 4)
                                  if d.get("claims") else None)
        return d

    def by_band(self):
        return [dict(r) for r in self.con.execute("""
            SELECT COALESCE(ffu_band,'n/a') AS band, COUNT(*) AS n
              FROM agent_event GROUP BY band ORDER BY n DESC""").fetchall()]

    def stage_latency(self):
        r = self.con.execute("""
            SELECT ROUND(AVG(ms_retrieval),1) AS retrieval,
                   ROUND(AVG(ms_plan),1) AS plan,
                   ROUND(AVG(ms_query),1) AS query,
                   ROUND(AVG(ms_ffu),1) AS ffu,
                   ROUND(AVG(ms_narrate),1) AS narrate,
                   ROUND(AVG(ms_verify),1) AS verify
              FROM agent_event""").fetchone()
        return dict(r) if r else {}

    def recent(self, n=20):
        return [dict(r) for r in self.con.execute(
            "SELECT * FROM agent_event ORDER BY event_id DESC LIMIT ?", (n,)).fetchall()]

    def close(self):
        self.con.close()
