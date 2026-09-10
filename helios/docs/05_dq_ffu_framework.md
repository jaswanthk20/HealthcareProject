# Data quality and fitness for use

The display labels are **published**, **caution**, and **unavailable**. They describe source availability and statistical warnings, not a score or clinical certification.

- Blank source flag: show the percentage with its published confidence interval.
- E: show with caution.
- F: too unreliable to publish; show no number.
- x: confidentiality suppression; show no number.
- .. or ...: unavailable/not applicable; never convert to zero.
- Missing interval bounds: caution. Never construct replacement bounds.
- When an estimate is suppressed, withhold interval values as well.

Validation rejects incompatible schemas, unknown flags, duplicate keys, invalid percentage units/ranges and reversed confidence intervals. No defects are deliberately injected.

Use national figures supplied by the publisher. Provincial estimates cannot be averaged to reconstruct Canada. Adult age bands and sex categories may overlap totals and must not be added. Weighted population estimates are not sample sizes.

For descriptive population monitoring, consider the confidence intervals, source notes and survey methodology. The 2022 redesign and 2024 regular-provider question revision constrain comparisons. These data cannot establish causal effects or clinical suitability.
