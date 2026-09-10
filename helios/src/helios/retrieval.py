"""
Retrieval over the governed semantic layer.

This is the deliberate architectural choice in HELIOS: the RAG index does not
contain prose documents. It contains metric definitions, dimension value sets,
table contracts and registered business questions. The agent therefore
retrieves *the vocabulary it is allowed to answer in*, and a question that
retrieves nothing is a question the product cannot answer - which is exactly
what we want it to say.

Implementation is BM25 with a hand-maintained clinical synonym map. BM25 is
used rather than embeddings for three reasons that matter in a regulated
setting: it is deterministic, it is explainable to an auditor (you can show
which term matched), and it needs no model call, so evaluation runs are free
and reproducible.
"""

import math
import re
from collections import Counter

from . import semantic_layer as sl

# The controlled vocabulary. Maintained by the BA with Medical Affairs - this
# is a product artefact, not an implementation detail, and every entry traces
# to a real phrase a stakeholder used in a requirements workshop.
SYNONYMS = {
    "wait": ["time", "delay", "lag", "duration"],
    "waiting": ["time", "delay", "duration"],
    "diagnosed": ["diagnosis", "dx", "confirmed"],
    "dx": ["diagnosis"],
    "odyssey": ["diagnosis", "time", "delay"],
    "uptake": ["share", "new", "starts", "launch", "brand"],
    "launch": ["brand", "share", "new", "starts"],
    "adoption": ["share", "uptake", "starts"],
    "adherence": ["pdc", "covered", "days", "persistence"],
    "compliance": ["adherence", "pdc"],
    "persistent": ["persistence", "stay", "continue"],
    "dropout": ["persistence", "discontinuation"],
    "discontinuation": ["persistence"],
    "switching": ["switch", "competitive"],
    "biologic": ["advanced", "therapy", "biologic"],
    "biologics": ["advanced", "therapy"],
    "advanced": ["biologic", "jak", "therapy"],
    "untreated": ["gap", "white", "space", "no", "therapy", "unmet"],
    "unmet": ["gap", "untreated", "need"],
    "whitespace": ["gap", "untreated"],
    "burden": ["cost", "ed", "emergency", "utilisation", "utilization"],
    "cost": ["spend", "paid", "economic", "budget"],
    "er": ["ed", "emergency"],
    "hospital": ["ed", "emergency", "inpatient"],
    "referral": ["specialist", "consult"],
    "specialist": ["referral", "consult", "derm"],
    "pathway": ["sequence", "line", "treatment"],
    "journey": ["sequence", "pathway", "time"],
    "sequence": ["pathway", "line"],
    "quality": ["dlqi", "life", "pro", "patient", "reported"],
    "qol": ["dlqi", "quality", "life"],
    "rural": ["rurality", "urban", "equity", "geography"],
    "equity": ["rurality", "rural", "access", "disparity"],
    "disparity": ["equity", "gap", "rurality"],
    "payer": ["insurance", "public", "private", "formulary", "access"],
    "formulary": ["insurance", "payer", "access"],
    "province": ["geography", "region", "ontario", "quebec"],
    "ontario": ["province", "on"],
    "quebec": ["province", "qc"],
    "severe": ["severity", "severe"],
    "kids": ["age", "paediatric", "pediatric", "band"],
    "children": ["age", "paediatric", "band"],
    "eczema": ["atopic", "dermatitis", "ad"],
    "asthma": ["severe", "asthma", "respiratory"],
    "sanovia": ["brand", "launch", "share"],
}

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "of", "for", "to", "in", "on", "is", "are", "and", "or",
    "what", "how", "which", "do", "does", "did", "we", "our", "i", "me", "you",
    "by", "with", "at", "from", "that", "this", "it", "be", "as", "was", "were",
    "can", "could", "would", "should", "please", "show", "tell", "give",
}


def tokenize(text, expand=True):
    toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]
    if not expand:
        return toks
    out = list(toks)
    for t in toks:
        out.extend(SYNONYMS.get(t, []))
    return out


# A term in a metric's title is far more discriminating than the same term
# buried in its caveat. Without this weighting "12 month persistence rate"
# resolves to the switch-rate metric, because both mention "12", "month" and
# "rate" but only one is *titled* persistence.
TITLE_WEIGHT = 3


class BM25Index:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tf = []
        df = Counter()
        for d in docs:
            toks = tokenize(d["title"]) * TITLE_WEIGHT + tokenize(d["text"])
            c = Counter(toks)
            self.tf.append(c)
            for term in c:
                df[term] += 1
        self.n = len(docs)
        self.avgdl = sum(sum(c.values()) for c in self.tf) / max(self.n, 1)
        self.idf = {t: math.log(1 + (self.n - v + 0.5) / (v + 0.5)) for t, v in df.items()}

    def search(self, query, k=5, kind=None):
        q = tokenize(query)
        scored = []
        for i, d in enumerate(self.docs):
            if kind and d["kind"] != kind:
                continue
            c = self.tf[i]
            dl = sum(c.values()) or 1
            s, matched = 0.0, []
            for term in set(q):
                if term not in c:
                    continue
                freq = c[term]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                s += self.idf.get(term, 0.0) * freq * (self.k1 + 1) / denom
                matched.append(term)
            if s > 0:
                scored.append({"doc": d, "score": round(s, 3),
                               "matched_terms": sorted(matched)})
        scored.sort(key=lambda r: -r["score"])
        return scored[:k]


_INDEX = None


def index():
    global _INDEX
    if _INDEX is None:
        _INDEX = BM25Index(sl.searchable_documents())
    return _INDEX


def retrieve(question, k=6):
    return index().search(question, k=k)


# A question must engage enough of the governed vocabulary to be answerable.
# "What is the share price forecast?" matches "share" and nothing else; without
# a coverage floor the product would confidently answer it with brand share.
MIN_SCORE = 3.0
MIN_COVERAGE = 0.30

# Default break-out for a metric that has a registered business question. The
# rule: a registered question carries the break-out its stakeholder approved,
# and the user gets that view unless they ask for a different one.
_DEFAULT_BREAKDOWN = {bq["metric"]: bq["breakdown"]
                      for bq in sl.BUSINESS_QUESTIONS if bq["breakdown"]}


def coverage(question, matched_terms):
    """Share of the question's own content words that the document matched."""
    orig = set(tokenize(question, expand=False))
    if not orig:
        return 0.0
    return len(orig & set(matched_terms)) / len(orig)


def best_metric(question, match_text=None):
    """Resolve a natural-language question to a governed metric id.

    `match_text` lets the caller strip a break-out phrase ("by province") so a
    dimension name cannot outvote the metric the user actually asked about.
    """
    text = match_text if match_text is not None else question
    hits = index().search(text, k=8)
    # A registered business question wins only when it is the single best
    # match. A wider berth lets a stakeholder phrase hijack a question that
    # was really about a different metric.
    for h in hits[:1]:
        if h["doc"]["kind"] == "business_question":
            if h["score"] >= MIN_SCORE and coverage(text, h["matched_terms"]) >= MIN_COVERAGE:
                return (h["doc"]["meta"]["metric"], h["score"],
                        f"matched registered business question {h['doc']['doc_id']}",
                        h["doc"]["meta"].get("breakdown"))
    for h in hits:
        if h["doc"]["kind"] != "metric":
            continue
        cov = coverage(text, h["matched_terms"])
        if h["score"] < MIN_SCORE or cov < MIN_COVERAGE:
            return (None, h["score"],
                    f"best candidate {h['doc']['doc_id']} matched only "
                    f"{cov:.0%} of the question's terms (score {h['score']:.1f}), "
                    f"below the governed-vocabulary threshold", None)
        return (h["doc"]["doc_id"], h["score"],
                f"matched metric definition on terms {h['matched_terms']}",
                _DEFAULT_BREAKDOWN.get(h["doc"]["doc_id"]))
    return (None, 0.0, "no governed metric matched the question", None)


def strip_breakdown_phrase(question, dimension):
    """Remove the break-out request so it cannot skew metric selection."""
    if not dimension:
        return question
    out = re.sub(r"\b(broken\s+down\s+|break\s+down\s+|split\s+)?by\s+"
                 + dimension.replace("_", r"[\s_]") + r"\b", " ", question, flags=re.I)
    for alias in ("province", "region", "payer", "insurance", "severity",
                  "age", "sex", "geography"):
        out = re.sub(r"\b(broken\s+down\s+|break\s+down\s+|split\s+)?by\s+" + alias + r"\b",
                     " ", out, flags=re.I)
    return out.strip() or question


# Stakeholders say "Prince Edward Island", the warehouse stores "PE". Without
# this map the cohort silently stayed national while the answer claimed to be
# about PEI - a wrong answer that looks completely correct.
PROVINCE_ALIASES = {
    "ontario": "ON", "quebec": "QC", "québec": "QC",
    "british columbia": "BC", "alberta": "AB", "manitoba": "MB",
    "saskatchewan": "SK", "nova scotia": "NS", "new brunswick": "NB",
    "newfoundland": "NL", "newfoundland and labrador": "NL",
    "prince edward island": "PE", "pei": "PE",
    "yukon": "TERR", "nunavut": "TERR", "northwest territories": "TERR",
    "the territories": "TERR",
}

CONDITION_ALIASES = {
    "eczema": "atopic_dermatitis", "atopic dermatitis": "atopic_dermatitis",
    "atopic eczema": "atopic_dermatitis", "severe asthma": "severe_asthma",
}


def detect_dimension(question):
    """Find a break-out dimension and any single-value filters in the text."""
    q = question.lower()
    breakdown = None
    filters = {}

    for phrase, code in PROVINCE_ALIASES.items():
        if re.search(r"\b" + re.escape(phrase) + r"\b", q):
            filters.setdefault("province", [])
            if code not in filters["province"]:
                filters["province"].append(code)
    for phrase, val in CONDITION_ALIASES.items():
        if re.search(r"\b" + re.escape(phrase) + r"\b", q):
            filters.setdefault("primary_condition", [])
            if val not in filters["primary_condition"]:
                filters["primary_condition"].append(val)
    for dim, meta in sl.DIMENSIONS.items():
        if re.search(r"\bby\s+" + dim.replace("_", r"[\s_]"), q):
            breakdown = dim
        for val in meta["values"]:
            v = val.lower()
            if re.search(r"\b" + re.escape(v) + r"\b", q):
                filters.setdefault(dim, []).append(val)
    # natural phrasings the value list alone will not catch
    if re.search(r"\brural[\s-]*(vs|versus|and|compared)[\s-]*urban\b", q) or \
       re.search(r"\b(urban|rural)[\s-]*(vs|versus)\b", q):
        breakdown = "rurality"
        filters.pop("rurality", None)
    if re.search(r"\b(child|children|kid|kids|p[ae]ediatric|adolescent|teen|"
                 r"adult|adults|elderly|senior|seniors|older)\b", q):
        breakdown = breakdown or "age_band"
    for phrase, dim in [("by province", "province"), ("by region", "province"),
                        ("across provinces", "province"), ("by payer", "insurance_type"),
                        ("by insurance", "insurance_type"), ("by severity", "severity"),
                        ("by age", "age_band"), ("by sex", "sex"),
                        ("geograph", "province"), ("equity", "rurality")]:
        if phrase in q and breakdown is None:
            breakdown = dim
    if breakdown and breakdown in filters:
        filters.pop(breakdown)      # never filter to one value and break out by it
    return breakdown, filters
