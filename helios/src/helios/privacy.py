"""
Privacy-by-construction guardrails.

The design decision that matters here: suppression is applied by the *metric
engine*, not by the dashboard. A number that would breach the small-cell policy
is never produced, so it can never be screenshotted out of a chart, pasted into
a deck, or quoted by the AI agent. There is no path around it.

Policy implemented (configurable in config/settings.json):
  P1  Primary suppression   - any cell with denominator < MIN_CELL is suppressed.
  P2  Numerator suppression - a non-zero numerator < MIN_CELL is suppressed even
                              when the denominator is large (a rate of 3/900 still
                              identifies three people in a small geography).
  P3  Complementary suppression - if exactly one cell in a break-out is
                              suppressed, the next-smallest cell is suppressed
                              too, otherwise the first can be recovered by
                              subtraction from the total.
  P4  Consent enforcement   - registry rows with consent_flag = 0 are excluded
                              at the cohort layer, never at the report layer.
  P5  Audit                 - every suppression decision is logged with the
                              cohort hash so a regulator can reconstruct why a
                              cell is blank.
"""

import datetime

MIN_CELL = 11          # patients; Canadian health-data convention for public release
SUPPRESSED = "SUPPRESSED"

_audit = []


def audit_log():
    return list(_audit)


def clear_audit():
    _audit.clear()


def _record(rule, detail, cohort_hash):
    _audit.append({
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "rule": rule, "detail": detail, "cohort_hash": cohort_hash,
    })


def check_cell(numerator, denominator, cohort_hash="-", min_cell=MIN_CELL):
    """Return (ok, reason). Applies P1 and P2."""
    if denominator is None or denominator < min_cell:
        _record("P1_primary", f"denominator={denominator} < {min_cell}", cohort_hash)
        return False, f"cohort of {denominator} is below the minimum cell size of {min_cell}"
    if numerator is not None and 0 < numerator < min_cell:
        _record("P2_numerator", f"numerator={numerator} < {min_cell}", cohort_hash)
        return False, f"numerator below the minimum cell size of {min_cell}"
    return True, None


def apply_complementary(results, min_cell=MIN_CELL):
    """P3. `results` is a list of dicts each with 'group', 'suppressed', 'n'.

    Mutates and returns the list. If exactly one group is suppressed, suppress
    the smallest surviving group as well.
    """
    suppressed = [r for r in results if r.get("suppressed")]
    if len(suppressed) != 1:
        return results
    survivors = [r for r in results if not r.get("suppressed")]
    if not survivors:
        return results
    victim = min(survivors, key=lambda r: r.get("n") or 0)
    victim["suppressed"] = True
    victim["suppression_reason"] = (
        "complementary suppression - reporting this cell would allow the "
        "suppressed cell to be recovered by subtraction"
    )
    _record("P3_complementary", f"group={victim.get('group')}", victim.get("cohort_hash", "-"))
    return results


# --------------------------------------------------------------------------
# Free-text safety: the agent narrates, so narration gets scrubbed too.
# --------------------------------------------------------------------------
import re  # noqa: E402

_PATTERNS = [
    (re.compile(r"\bPT\d{7}\b"), "[PATIENT_ID_REDACTED]"),
    (re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{3}\b"), "[NUMBER_REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b[A-Z]\d[A-Z][ -]?\d[A-Z]\d\b"), "[POSTAL_CODE_REDACTED]"),
]


def scrub(text, cohort_hash="-"):
    """Remove anything that looks like a direct or indirect identifier."""
    out = text
    for pat, repl in _PATTERNS:
        out, n = pat.subn(repl, out)
        if n:
            _record("P5_scrub", f"{n} match(es) for {pat.pattern}", cohort_hash)
    return out
