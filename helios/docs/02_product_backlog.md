# Product backlog and acceptance

| Capability | Acceptance criterion |
|---|---|
| Official ingestion | Import the publisher's ZIP and metadata without generated records |
| Schema checks | Missing columns, unknown flags, invalid units, duplicate keys and invalid bounds fail validation |
| Quality display | E is caution; F/x/unavailable values do not render as numbers |
| Population selection | Match exact year, geography, age and sex; no weighted averaging of provinces |
| Trends | Show published annual cells from 2022; surface the 2024 provider-question change |
| Provenance | Source URL, release date, observation year, retrieval time and SHA-256 are visible |
| Questions | Answer from governed cells or explicitly refuse unsupported requests |
| Refresh | Check daily after merge; commit data changes only after tests pass |

Future source additions require separate provenance, licence review, supported metrics and tests. No patient-level data integration or clinical prediction is included in this release.
