"""Validate aggregate population selections, without constructing patient records."""
from .semantic_layer import DIMENSIONS
SPEC_VERSION = "2.0.0"

class CohortError(ValueError):
    pass

class CohortSpec:
    def __init__(self, filters=None):
        self.filters = filters or {}
        for dim, values in self.filters.items():
            if dim not in DIMENSIONS or not isinstance(values, list) or any(v not in DIMENSIONS[dim]["values"] for v in values):
                raise CohortError("Unknown population filter")
