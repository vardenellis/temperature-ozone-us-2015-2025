
# Source-data retrieval instructions

## Data excluded from this repository

The repository contains no raw EPA or NOAA download and no processed analytical
panel. `source_manifests/` contains the frozen upstream URLs, retrieval
metadata, byte sizes, and SHA-256 checksums only.

## Reconstruction boundary

An authorized user must retrieve the exact official EPA AQS/AirData and NOAA
NCEI GHCN-Daily inputs identified by the manifests, verify their checksums, and
apply the frozen rules documented in `config/analysis.yml`,
`preregistration/`, and `docs/`. Official sources can change after retrieval;
checksum mismatch must stop reconstruction rather than silently substitute a
new file.

This repository does not provide or promise a one-command data rebuild. Network
retrieval and a clean acquisition-to-analysis run were not executed during
release packaging. The processed panel identity expected by the reporting
freeze is SHA-256
`3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0`.
Redistribution of that panel remains a separate author decision.
