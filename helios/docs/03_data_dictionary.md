# Official data dictionary

Source: [Statistics Canada table 13-10-0905-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310090501).

Grain: one percentage estimate per reference year, geography, age, sex and governed indicator. These are published survey aggregates, not patient records.

| Field | Meaning |
|---|---|
| year | Official reference year, distinct from release or download date |
| geography | Province or Canada excluding territories |
| age / sex | Exact population dimensions from the source |
| indicator | Governed identifier linked to the official label |
| value | Published percentage, null when not releasable |
| low / high | Published bootstrap 95% confidence interval; never recomputed |
| *_status | Source quality symbols, preserved independently |
| *_vector | Statistics Canada series reference |
| quality | published, caution or unavailable; a display rule, not certification |

## Governed indicators

- `access`: Has a regular healthcare provider
- `diabetes`: Diabetes
- `blood_pressure`: High blood pressure
- `mental_health`: Perceived mental health, fair or poor
- `anxiety`: Anxiety disorder
- `mood`: Mood disorder
- `obesity`: Body mass index, adjusted self-reported, obese
- `smoking`: Current smoker, daily or occasional

## Population dimensions

- **year**: 2022; 2023; 2024
- **geography**: Alberta; British Columbia; Canada (excluding territories); Manitoba; New Brunswick; Newfoundland and Labrador; Nova Scotia; Ontario; Prince Edward Island; Quebec; Saskatchewan
- **age**: 18 to 34 years; 35 to 49 years; 50 to 64 years; 65 years and over; Total, 18 years and over
- **sex**: Both sexes; Females; Males
