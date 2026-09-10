"""
Numeric claim verification.

The control that makes a generated narrative safe to publish.

Whatever writes the prose - a template today, a language model tomorrow - the
verifier treats the finished text as untrusted. It extracts every number in the
text and requires each one to trace to a value that was actually returned by an
executed, cited query. A number that cannot be traced is a hallucination by
definition, and the answer is blocked rather than shipped with a caveat.

This runs after generation and before display, so swapping the deterministic
narrator for an LLM narrator does not weaken the guarantee.
"""

import re

# Numbers as they appear in prose: 1,234  45.9%  $1,234  0.62  255
_NUMBER = re.compile(r"""
    (?<![\w/])
    (?P<dollar>\$)?
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*(?P<pct>%)?
""", re.VERBOSE)

# Numbers that are structurally part of the answer, not data claims.
_ALWAYS_OK = set(range(1900, 2101))          # calendar years

# Spans that are not data claims and must be masked before extraction.
#
# The important category is the third one: text quoted verbatim from the
# governed semantic layer. A metric named "12-month persistence rate" or
# "ED visits per 100 patients" carries digits that are part of its NAME, and a
# caveat may cite a check id like DQ-06. Those are governed, version-controlled
# strings, not generated claims, so flagging them was a false positive - which
# is exactly what the golden set caught.
_MASKED = [
    re.compile(r"\d{4}-\d{2}(?:-\d{2})?"),          # ISO periods: 2026-06
    re.compile(r"95%\s*CI"),                         # the policy confidence level
    re.compile(r"\b(?:DQ|BQ|CH|V)-[0-9A-F]+\b"),     # check / question / cohort ids
    re.compile(r"\bM\d{2}_[a-z0-9_]+\b"),            # metric ids
]


def _masked_spans(text, static_text=()):
    spans = []
    for pat in _MASKED:
        spans.extend((m.start(), m.end()) for m in pat.finditer(text))
    # Verbatim governed strings: metric labels, units, caveats, policy wording.
    for frag in static_text:
        if not frag or not isinstance(frag, str):
            continue
        # Short fragments are only masked when they carry a digit, so a
        # governed label like "65+" is covered while a bare "ON" or "CAD"
        # never widens the mask beyond what it needs to.
        if len(frag) < 4 and not any(ch.isdigit() for ch in frag):
            continue
        if len(frag) < 2:
            continue
        start = 0
        while True:
            i = text.find(frag, start)
            if i < 0:
                break
            spans.append((i, i + len(frag)))
            start = i + 1
    return spans


def _in_span(pos, spans):
    return any(a <= pos < b for a, b in spans)


def _floats_from_result(res):
    """Every value the caller is entitled to state, given this result."""
    out = []

    def add(v, unit=None):
        if v is None:
            return
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        out.append(f)
        out.append(round(f, 1))
        out.append(round(f))
        # a proportion may legitimately be quoted as a percentage
        if 0.0 <= f <= 1.0:
            out.extend([f * 100, round(f * 100, 1), round(f * 100)])

    add(res.value)
    add(res.n)
    add(res.numerator)
    add(res.denominator)
    if res.ci:
        for c in res.ci:
            add(c)
    if res.spread:
        for s in res.spread:
            add(s)
    for p in (res.series or []):
        add(p.get("value"))
        add(p.get("n"))
        add(p.get("numerator"))
    for c in (res.categories or []):
        add(c.get("n"))
        add(c.get("pct"))
    return out


def extract_numbers(text, static_text=()):
    spans = _masked_spans(text, static_text)
    found = []
    for m in _NUMBER.finditer(text):
        if _in_span(m.start("num"), spans):
            continue                      # inside a date or the "95% CI" label
        raw = m.group("num").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        found.append({"text": m.group(0).strip(), "value": val,
                      "is_pct": bool(m.group("pct")),
                      "is_currency": bool(m.group("dollar")),
                      "start": m.start()})
    return found


def _matches(claim, allowed, tol_abs=0.06, tol_rel=0.006):
    for a in allowed:
        if abs(claim - a) <= max(tol_abs, tol_rel * abs(a)):
            return True
    return False


def verify(text, results, extra_allowed=(), static_text=()):
    """Check every number in `text` against the executed results.

    results        list of MetricResult objects actually computed and cited
    extra_allowed  values the narrator legitimately introduces that are not
                   metric outputs (a cohort size, a count of break-out groups),
                   each of which must itself come from an executed query.
    static_text    strings quoted verbatim from the governed semantic layer
                   (metric labels, units, caveats). Digits inside these are
                   part of a governed name, not a claim about the data.

    Returns a dict with groundedness = verified / total.
    """
    allowed = []
    for r in results:
        allowed.extend(_floats_from_result(r))
    for v in extra_allowed:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        allowed.extend([f, round(f, 1), round(f)])

    claims = extract_numbers(text, static_text)
    verified, violations = [], []
    for c in claims:
        val = c["value"]
        if val.is_integer() and int(val) in _ALWAYS_OK:
            verified.append(c)
            continue
        if _matches(val, allowed):
            verified.append(c)
        else:
            violations.append(c)

    total = len(claims)
    return {
        "total_claims": total,
        "verified_claims": len(verified),
        "groundedness": round(len(verified) / total, 4) if total else 1.0,
        "violations": [{"text": v["text"], "value": v["value"]} for v in violations],
        "passed": not violations,
        "allowed_value_count": len(set(allowed)),
    }
