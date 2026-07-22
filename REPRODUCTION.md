
# Reproduction instructions

## Included-artifact reproduction

Use Python 3.12 with `environment/requirements-render.txt`. From the repository
root, run the table and figure commands listed in `README.md`, then verify the
generated files against `PUBLIC_RELEASE_CHECKSUMS.sha256`.

This tested path reads only included final-synthesis JSON/CSV files and the
frozen configuration. It does not access ozone outcomes, fit a model, or run a
bootstrap.

## Full analytical reproduction

Full analysis is not independently executable from this repository because raw
official-source files and the processed panel are excluded. Reconstruct those
inputs under `SOURCE_DATA_RETRIEVAL.md` before attempting analytical fitting.
The clean acquisition-to-analysis workflow has not been validated here, so no
single-command claim is made.
