"""Conservative matching over official indicator labels and population dimensions."""
import re
from . import semantic_layer as sl

ALIASES = {
    "access": ["healthcare provider", "regular provider", "family doctor", "access to care"],
    "diabetes": ["diabetes", "diabetic"],
    "blood_pressure": ["blood pressure", "hypertension"],
    "mental_health": ["mental health"],
    "anxiety": ["anxiety"], "mood": ["mood disorder"],
    "obesity": ["obesity", "obese"], "smoking": ["smoking", "smoker", "smokers"],
}

def detect_dimension(question):
    q = question.lower()
    filters = {}
    for dim, spec in sl.DIMENSIONS.items():
        values = [v for v in spec["values"] if re.search(r"\b" + re.escape(v.lower()) + r"\b", q)]
        if values:
            filters[dim] = values
    if re.search(r"\b(women|female)\b", q): filters["sex"] = ["Females"]
    elif re.search(r"\b(men|male)\b", q): filters["sex"] = ["Males"]
    breakdown = "geography" if re.search(r"by province|across provinces|provinces compare", q) else None
    return breakdown, filters

def strip_breakdown_phrase(question, breakdown):
    return question

def best_metric(question, match_text=None):
    q = question.lower()
    matches = [key for key, words in ALIASES.items() if any(re.search(r"\b"+re.escape(w)+r"\b",q) for w in words)]
    if len(matches) != 1:
        return None, 0, "Choose exactly one governed indicator", None
    return matches[0], 1, "Matched the governed indicator vocabulary", None

def retrieve(question, k=6):
    mid, _, _, _ = best_metric(question)
    keys = [mid] if mid else list(sl.METRICS)[:k]
    return [{"doc": {"kind": "metric", "doc_id": key, "title": sl.METRICS[key]["label"]}} for key in keys]
