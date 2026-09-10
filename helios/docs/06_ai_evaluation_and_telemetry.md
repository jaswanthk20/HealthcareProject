# Planning, evaluation and provenance

The deterministic planner matches an explicit indicator vocabulary and published population names. The optional configurable model endpoint returns a governed plan, never a figure. Invalid or unsupported selections are refused. Model failures use the deterministic fallback and record an exception type without exposing credential details.

Answers quote the selected published estimate and its source confidence interval. They name the population, year and source. The dashboard uses a local controlled-vocabulary lookup and the current visible filters; it does not call a paid model.

Tests cover official-source ingestion, source-row agreement, suppressed and missing cells, caution flags, confidence-interval protection, invalid flags/ranges, duplicate keys, unsupported questions, population selection, refresh stability, and model success/fallback behavior. Old prototype release-gate numbers are not carried forward as evidence for this product.

The public export stores source provenance rather than a patient-query telemetry database: table, URLs, source release date, observation years, archive SHA-256 and retrieval time. Source methodology notes are preserved. No patient identifiers or question history are stored by the dashboard.
