
# Reproducibility scope

| Output class | Classification | Basis |
| --- | --- | --- |
| Final tables and figures | Reproducible from included material | Regenerated from included freeze/summaries in a clean temporary directory using the existing locked environment. |
| Manuscript numerical statements | Verifiable from included frozen results | Number traceability and reporting freeze are included. |
| Sensitivity and interval summaries | Verifiable from included frozen results | Final machine-readable synthesis records are included. |
| Full model and bootstrap results | Not independently reproduced from this repository alone | Curated source is included, but raw files and the processed panel are excluded and no clean end-to-end run was completed. |
| Acquisition-to-panel pipeline | Not independently reproducible from this repository alone | Upstream manifests and rules are included, but source downloads and the tested full pipeline are not. |

Fresh-environment validation details are recorded in
`FRESH_ENVIRONMENT_VALIDATION.json`. Full acquisition and the thousands of
scientific bootstrap fits were not rerun.
