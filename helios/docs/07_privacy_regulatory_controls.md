# Privacy and source controls

Only official public aggregate survey statistics are ingested. There are no patient, clinician, prescription or claim records in this product. Source suppression and unreliability flags are preserved; blocked estimates and associated intervals are not shown as numbers.

The dashboard is descriptive population-health reporting, not a clinical decision system, medical device assessment or evidence of regulatory compliance. It does not establish a treatment recommendation, identify an individual, infer prescription behavior or claim that publication implies fitness for every use.

Use the Statistics Canada Open Licence and preserve attribution. The product must not imply official endorsement. Source credentials are unnecessary; optional model credentials come only from environment variables. No secrets are committed, and errors do not export endpoint or key details.

On download or validation failure, the pipeline exits non-zero and does not fabricate a replacement. The previously verified dashboard remains available with its original source dates. Source changes must pass validation and tests before being committed.
