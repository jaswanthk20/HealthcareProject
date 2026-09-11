# HELIOS - Canadian health indicators

A healthcare intelligence dashboard backed by **official published survey data**, downloaded directly from Statistics Canada. No generated patient records or simulated clinical outcomes are used.

**Private hosted dashboard:** https://helios-canadian-health.jkzzz20.chatgpt.site

**Portable dashboard:** open [helios_dashboard.html](dashboard/helios_dashboard.html) after downloading the repository. The HTML embeds a verified official-data snapshot and works locally. Its update button retrieves the latest validated repository snapshot when available.

## Source and scope

[Statistics Canada table 13-10-0905-01 - Health indicator statistics, annual estimates](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310090501), from the Canadian Community Health Survey. The source currently covers observations through **2024**, released **2025-08-06**. A download made today does not turn historical observations into real-time clinical data.

Eight governed indicators: regular healthcare-provider access, diabetes, high blood pressure, fair/poor mental health, anxiety disorder, mood disorder, obesity and current smoking. Explore Canada excluding territories and ten provinces, five adult age groups, three sex categories and reference years beginning in 2022.

Percentages and bootstrap confidence intervals are published estimates, copied directly from the source. They are not calculated from invented patients. Quality symbols E, F, x and unavailable values remain explicit. The regular-provider question changed in 2024; comparisons with earlier years require caution. The 2022 survey redesign is why this dashboard excludes earlier cycles.

## Run and refresh

Python 3.9+; standard library only. From the repository root:

```bash
python helios/run_all.py
python -m unittest discover -s helios/tests
python -m http.server 8000 --directory dist
```

Open http://localhost:8000. Each online run downloads the official archive and metadata, validates the data, rebuilds the dashboard and updates the generated documentation. If source content has not changed, published files stay unchanged. Failed downloads or validation exit non-zero; they never generate replacement observations.

```bash
python helios/run_all.py --offline
python helios/run_all.py --offline --ask "What percentage has diabetes in Ontario in 2024?"
```

Offline mode requires a previously downloaded official archive. Raw downloads are kept under `helios/data/official/` and ignored by Git. The old generated warehouse is no longer used.

## Automatic source updates

`.github/workflows/refresh-official-data.yml` checks the official table daily at 13:23 UTC and can be started manually. After validation and tests it commits only changed data, the rebuilt dashboard, and generated documentation. A separate workflow validates pull requests.

**Scheduled refresh activates after this change is merged into the default branch**, with GitHub Actions enabled and permission to write that branch. Branch protection can block automatic commits. The dashboard update button reads the default branch; before merge it retains its embedded official snapshot and reports that a newer snapshot is unavailable. No update check is described as a new survey release.

## Optional model planner

The default planner uses a controlled vocabulary without network access. A model may select an indicator and population; the answer still quotes a published cell.

```bash
export HELIOS_MODEL_ENDPOINT="https://your-model-service.example/v1/chat/completions"
export HELIOS_MODEL="your-model-id"
export HELIOS_MODEL_API_KEY="your-key"  # optional
python helios/run_all.py --offline --planner model --ask "What percentage has diabetes?"
```

PowerShell uses `$env:HELIOS_MODEL = "your-model-id"` and corresponding endpoint/key variables. The endpoint receives JSON with `model`, `messages`, `max_tokens` and `response_format: {type: "json_schema", json_schema: {name, schema}}`. It returns a JSON plan string in `choices[0].message.content`, with optional `usage.prompt_tokens` and `usage.completion_tokens`. The API key is sent as a Bearer token. Missing configuration or errors use the deterministic fallback. No patient records are sent. Live paid model services are not required or used by tests.

## What changed from the prototype

The generated patient/claims warehouse, fictional drug-launch measures, injected data defects, fabricated release results and patient-level metric engine were retired. Current documentation describes the public aggregate data product. Unsupported launch, treatment-pathway, rurality and payer questions are refused; their old figures are not relabelled as real data. Historic versions remain in Git history.

## Reuse and attribution

[Statistics Canada Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence). Attribution, reference years, source URLs, source release date, download timestamp, methodology notes and archive SHA-256 are embedded in the dashboard and data export. This product is not endorsed by Statistics Canada.
