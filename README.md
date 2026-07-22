
# Temperature Distributions and Temperature-Standardized Ozone Change Across U.S. Monitoring Sites, 2015–2025

**Ellis Varden, Independent Researcher**

## Release status

This public repository is version 1.0.0 of the curated reproducibility
materials. The manuscript is a non-peer-reviewed preprint with DOI
[`10.5281/zenodo.21484069`](https://doi.org/10.5281/zenodo.21484069), published
on Zenodo on 2026-07-22 as version 1.0.1. Version 1.0.1 is an administrative
correction to three auxiliary package files; the manuscript, supplement,
tables, and figures are unchanged from version 1.0. No public correspondence
address is supplied. The software has no separate software DOI.

## Study scope

The study reports associational modeled differences in continuous maximum daily
8-hour average ozone (MDA8) across represented monitoring sites between 2015–2019 and
2021–2025. It does not claim causation, population-weighted personal exposure,
or formal categorical adjudication of the directional hypotheses.

## Package contents

- `manuscript/`: curated manuscript and supplement sources, neutral PDF renders,
  references, traceability, final tables, figures, source data, and generators.
  `figure_inventory.json` is the publication authority; the byte-identical
  `figure_manifest.json` alias is retained for generator compatibility.
- `outputs/analysis/final_synthesis/`: public-sanitized reporting freeze, final synthesis
  summaries, hypothesis evidence, citation inventory, and completed audits.
- `src/` and `analysis_scripts/`: curated successful acquisition, analysis,
  sensitivity, and bootstrap implementation. Failed binary-model fitting and
  internal report-generation code are excluded.
- `config/`: frozen analytical configuration used by the table/figure tools.
- `source_manifests/`: upstream retrieval metadata and checksums, not source data.
- `environment/`: the tested table/figure rendering dependency set.
- Root audit and release documents: scope, status, metadata, inventory,
  privacy findings, and package checksums.

## Read the publication

- [View or download the manuscript PDF](manuscript/manuscript.pdf?raw=1)
- [View or download the supplement PDF](manuscript/supplement.pdf?raw=1)

These raw/download links remain available when GitHub's inline PDF preview is
unavailable.

## Inputs not distributed

Raw EPA/NOAA downloads, interim files, and the processed analytical panel are
not included. Internal handoffs, prompts, recovery material, attempt logs,
checkpoints, caches, secrets, private accounts, and private Git history are also
excluded.

## Source reconstruction

See [Source-data retrieval instructions](SOURCE_DATA_RETRIEVAL.md). The official-source manifests identify the
frozen upstream files. Acquisition-to-analysis reconstruction has not been
validated in a clean environment during this packaging stage. This package does
not promise one-command reconstruction.

## Verify included outputs

From the repository root, first verify
[the package checksums](PUBLIC_RELEASE_CHECKSUMS.sha256). With Python 3.12 and
the packages in `environment/requirements-render.txt`, run:

```bash
python manuscript/tables/generate_tables.py
python manuscript/figure_data/build_figure_data.py
for script in manuscript/figures/generate_figure_*.py; do
  MPLBACKEND=Agg python "$script"
done
```

These commands regenerate publication tables and figures from included frozen
results. They do not fit models or require the processed panel.

## Package self-check

Create an isolated Python 3.12 environment, install the package and its test
extra, and run the public package-integrity tests with the no-data guard:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
VARDEN_NO_DATA_ACCESS=1 python -m pytest -q tests/test_public_package.py
```

## Reproducibility scope

See [Reproducibility scope](REPRODUCIBILITY_SCOPE.md). Final values are verifiable from included frozen
machine-readable results; tables and figures are regenerable from included
material. Curated analytical source is included, but a clean end-to-end run was
not performed and the excluded inputs must first be reconstructed.

## Citation

Software metadata are in [CITATION.cff](CITATION.cff). The manuscript DOI is
[`10.5281/zenodo.21484069`](https://doi.org/10.5281/zenodo.21484069); the
Zenodo manuscript record is published as version 1.0.1. The unchanged
scientific PDFs display the predecessor version DOI,
[`10.5281/zenodo.21434897`](https://doi.org/10.5281/zenodo.21434897).
All seven traced citation placeholders were resolved from
the author-specified verified sources; the standing safeguard against future
unsupported literature claims remains active.

## Licensing

The MIT License applies to project software. CC BY 4.0 applies separately to
the manuscript, supplement, final tables, and final figures. Neither license
applies to third-party data or publications. See the [MIT License](LICENSE),
[content-license notice](CONTENT_LICENSE_NOTICE.md), and
[code-license decision](CODE_LICENSE_DECISION.md).

## AI assistance

See [AI assistance](AI_ASSISTANCE.md). Prompts and conversation records are not included.

## Current publication state

See [release status](RELEASE_STATUS.md) and the [changelog](CHANGELOG.md).

## Contact

No public correspondence email or postal address is supplied for version 1.0.1.
Questions about the reproducibility materials may be raised through this
repository's issue tracker.
