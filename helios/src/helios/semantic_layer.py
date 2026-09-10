"""Governed definitions for published Statistics Canada estimates."""
from .public_data import INDICATORS

METRICS = {key: {"label": label, "definition": label + ", published percentage estimate for the selected population.",
                 "decision_supported": "Descriptive population health and access comparison."}
           for key, label in INDICATORS.items()}
DIMENSIONS = {
    "geography": {"values": ["Canada (excluding territories)", "Newfoundland and Labrador", "Prince Edward Island", "Nova Scotia", "New Brunswick", "Quebec", "Ontario", "Manitoba", "Saskatchewan", "Alberta", "British Columbia"]},
    "age": {"values": ["Total, 18 years and over", "18 to 34 years", "35 to 49 years", "50 to 64 years", "65 years and over"]},
    "sex": {"values": ["Both sexes", "Males", "Females"]},
}
