# Business requirements — official healthcare data

## Purpose

Help healthcare analysts inspect published population-health and healthcare-access estimates for Canada and its provinces. The source is Statistics Canada table 13-10-0905-01, not clinical claims or a generated patient warehouse.

## Requirements

- Download official source data and metadata; never invent records or substitute generated observations after failure.
- Offer eight governed indicators with exact source geography, adult age and sex categories.
- Display reference year, source release date, source links, retrieval time and archive hash.
- Preserve source estimates, confidence intervals and quality flags. Missing/suppressed values remain null.
- Compare provinces and years descriptively; do not infer statistical significance or causal effects.
- Refuse unsupported questions and any attempt to target individual patients or prescribers.
- Refresh on publisher updates through a daily scheduled check, committing only validated changes.

## Scope boundary

This source does not support fictional brand share, diagnosis delay, payer access differences, prescription adherence, individual risk prediction or treatment pathways. Those prototype outputs were retired. Published survey data is not a real-time clinical feed or certification of fitness for a specific decision.

## Acceptance

The refresh succeeds on the official archive, every visible estimate traces to an official row, flagged estimates retain their restrictions, and repeated unchanged refreshes preserve the exported snapshot.
