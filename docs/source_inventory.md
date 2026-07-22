# Verified source inventory

**Verification/acquisition date:** 2026-07-14. Pages and endpoints below were
opened or checked against publisher documentation. Official bulk artifacts were
then acquired without alteration. File-level URLs, retrieval timestamps, sizes,
SHA-256 values, Last-Modified headers, ETags, content metadata, and resume status
are recorded in the immutable agency JSONL manifests rather than copied by hand
into this document.

## Official data and regulatory documentation

| ID | Publisher | Dataset/document | Exact URL or pattern | Version / update observed | Use in project | Use conditions |
|---|---|---|---|---|---|---|
| EPA-AIRDATA | U.S. EPA | AirData pre-generated files | https://aqs.epa.gov/aqsweb/airdata/download_files.html | Page showed files updated 2026-06-25 | Authoritative index; national daily ozone, site, and monitor files | EPA states AQS ambient monitoring data are public domain. |
| EPA-DAILY | U.S. EPA | Daily ozone summary, parameter 44201 | `https://aqs.epa.gov/aqsweb/airdata/daily_44201_{YYYY}.zip`, YYYY 2015–2025 | Index observed 2026-07-14 | Monitor-level validation reference for the reconstructed site record | Public domain; archive exact files and checksums. |
| EPA-HOURLY | U.S. EPA | Hourly ozone observations, parameter 44201 | `https://aqs.epa.gov/aqsweb/airdata/hourly_44201_{YYYY}.zip`, YYYY 2015–2025 | Index observed 2026-07-14 | Primary source for Appendix U site-record reconstruction | Public domain; archive exact files and checksums. |
| EPA-ANNUAL | U.S. EPA | Annual concentration summaries by monitor | `https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_{YYYY}.zip`, YYYY 2015–2025 | Index observed 2026-07-14 | Outcome-blind valid/required-day, completeness, certification, and update-date checks | Public domain; archive exact files and checksums. |
| EPA-SITES | U.S. EPA | AQS site listing | https://aqs.epa.gov/aqsweb/airdata/aqs_sites.zip | Dynamic listing | Site coordinates, elevation, operations, GMT offset | Public domain. |
| EPA-MONITORS | U.S. EPA | AQS monitor listing | https://aqs.epa.gov/aqsweb/airdata/aqs_monitors.zip | Dynamic listing | POC, monitor classifications, method summary, primary flags | Public domain. |
| EPA-FILE-LIST | U.S. EPA | AirData bulk-file update inventory | https://aqs.epa.gov/aqsweb/airdata/file_list.csv | Acquired 2026-07-14 | Upstream file names, sizes, and update metadata | Public domain. |
| EPA-SEASONS | U.S. EPA | AQS ozone monitoring seasons reference | https://aqs.epa.gov/aqsweb/documents/codetables/ozone_seasons.csv | Acquired 2026-07-14 | State/county/site-specific season start and end, including DC and split-jurisdiction specificity | Government documentation. |
| EPA-QUALIFIERS | U.S. EPA | AQS sample qualifier reference | https://aqs.epa.gov/aqsweb/documents/codetables/qualifiers.csv | Acquired 2026-07-14 local / 2026-07-15 UTC | Qualifier code/type validation; shows why nonblank does not uniformly mean invalid | Government documentation. |
| EPA-METHODS | U.S. EPA | AQS criteria-pollutant sampling methods | https://aqs.epa.gov/aqsweb/documents/codetables/methods_criteria.csv | Acquired 2026-07-14 local / 2026-07-15 UTC | Ozone Method Code, Method Type, FRM/FEM, and unit validation | Government documentation. |
| EPA-FORMAT | U.S. EPA | AirData Download Files Documentation | https://aqs.epa.gov/aqsweb/airdata/FileFormats.html | Version 3.0.0, 2015-12-01 | Field definitions and duplicate mechanisms | Government documentation. |
| EPA-PARAM | U.S. EPA | AQS Parameters code table | https://aqs.epa.gov/aqsweb/documents/codetables/parameters.html | Table dated 2026-07-09 | Verifies ozone `44201`, standard ppm, valid status | Government documentation. |
| EPA-DURATION | U.S. EPA | AQS Durations code table | https://aqs.epa.gov/aqsweb/documents/codetables/durations.html | Table dated 2026-07-09 | Verifies `W` = calculated begin-hour 8-hour running average | Government documentation. |
| EPA-STANDARD | U.S. EPA | AQS Pollutant Standards code table | https://aqs.epa.gov/aqsweb/documents/codetables/pollutant_standards.html | Table observed 2026-07-14 | Verifies 2015 standard label, daily metric, ppm, 0.070 | Government documentation. |
| EPA-DICTIONARY | U.S. EPA | AQS Data Dictionary | https://aqs.epa.gov/aqsweb/documents/AQS_Data_Dictionary.html | Current page observed 2026-07-14 | AQS field meanings and algorithms | Government documentation. |
| EPA-API | U.S. EPA | AQS Data API documentation/OpenAPI | https://aqs.epa.gov/aqsweb/documents/data_api.html | Current page observed 2026-07-14 | Key-based alternate/validation workflow; dailyData/byState | Requires registered email/key; API limits/terms apply; secrets never logged. |
| EPA-NAAQS | U.S. EPA | NAAQS table | https://www.epa.gov/criteria-air-pollutants/naaqs-table | Updated page observed 2026-07-14 | Verifies 0.070 ppm and three-year fourth-highest form | Government documentation. |
| CFR-U | eCFR / U.S. EPA | 40 CFR part 50 Appendix U | https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-50/appendix-Appendix%20U%20to%20Part%2050 | Up to date 2026-07-10 when opened | Site collocation, local time, MDA8 validity, completeness, NAAQS interpretation | Authoritative but unofficial continuously updated eCFR text. |
| CFR-D | eCFR / U.S. EPA | 40 CFR part 58 Appendix D | https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-58/appendix-Appendix%20D%20to%20Part%2058 | Current page observed 2026-07-14 | State/AQCR ozone monitoring seasons | Authoritative but unofficial continuously updated eCFR text. |
| EPA-PUBLIC | U.S. EPA | AirData permission FAQ | https://www.epa.gov/outdoor-air-quality-data/do-i-need-request-permission-use-monitoring-data-and-graphics-airdata | Updated 2025-08-11 | Confirms AQS ambient data are public domain | Free use; cite source and avoid implied endorsement. |
| NOAA-ROOT | NOAA/NCEI | GHCN-Daily bulk directory | https://www.ncei.noaa.gov/pub/data/ghcn/daily/ | Live index observed 2026-07-14 | Authoritative bulk root and metadata | Retain source terms/citation. |
| NOAA-YEAR | NOAA/NCEI | GHCN-Daily yearly CSV gzip | `https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_year/{YYYY}.csv.gz`, YYYY 2015–2025 | Yearly files are updated for period of record | Primary TMAX source | U.S. subset; cite NOAA/NCEI and dataset DOI. |
| NOAA-README | NOAA/NCEI | GHCN-Daily README | https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt | Version 3.34 observed; live file | Units, flags, station/inventory layouts, citation | Source-specific restrictions can exist; U.S. subset planned. |
| NOAA-YEAR-README | NOAA/NCEI | by-year format README | https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_year/readme-by_year.txt | File observed 2026-07-14 | Eight-column yearly record layout | Government documentation. |
| NOAA-STATION-README | NOAA/NCEI | by-station format README | https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme-by_station.txt | Acquired 2026-07-14 | Supplemental station-oriented format description used for schema comparison | Government documentation. |
| NOAA-VERSION | NOAA/NCEI | GHCN-Daily version file | https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-version.txt | Acquired `3.34-upd-2026071318` | Freeze exact acquired version | Live file; archive/checksum at acquisition. |
| NOAA-STATIONS | NOAA/NCEI | GHCN station metadata | https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt | Live metadata | Coordinates, elevation, state, names, network flags | Retain acquired version/checksum. |
| NOAA-INVENTORY | NOAA/NCEI | GHCN element inventory | https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-inventory.txt | Live metadata | TMAX period-of-record eligibility | Retain acquired version/checksum. |
| NOAA-DOC | NOAA/NCEI | GHCN-Daily documentation PDF | https://www.ncei.noaa.gov/pub/data/cdo/documentation/GHCND_documentation.pdf | Official documentation opened 2026-07-14 | Dataset description and access/use notes | U.S. data used; document source conditions. |
| NOAA-REGION | NOAA/NCEI | Climate at a Glance region catalog | https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/regional/time-series | Region IDs/names observed 2026-07-14 | NOAA nine-region definition/crosswalk source | Government information; cite NOAA. |
| LIT-WELLS-2021 | Wells et al. | Meteorologically adjusted U.S. ozone trends | https://doi.org/10.1016/j.atmosenv.2021.118234 | DOI/publisher metadata verified 2026-07-15 | Targeted novelty review; national monitor-based meteorological adjustment | Original research; see `docs/literature_review.md`. |
| LIT-JHUN-2015 | Jhun et al. | U.S. weather penalty analysis | https://doi.org/10.1088/1748-9326/10/8/084009 | DOI/publisher metadata verified 2026-07-15 | Targeted novelty review; site-level weather-adjusted trends | Original research; see `docs/literature_review.md`. |
| LIT-MOUSAVINEZHAD-2023 | Mousavinezhad et al. | CONUS climate-region ozone trends | https://doi.org/10.1016/j.atmosenv.2023.119693 | DOI/publisher metadata verified 2026-07-15 | Targeted novelty review; regional monitor analysis | Original research; see `docs/literature_review.md`. |

## Access strategy

### EPA

Primary acquisition is the national no-key AirData bulk archive because it is
the documented machine-readable source and avoids thousands of API calls. The
schema probe resolved that daily summaries expose monitor/POC records; a daily
archive does not itself perform Appendix U primary-first collocation. Therefore
hourly archives are the construction source, daily archives are monitor-level
validation references, and annual monitor summaries provide reporting and
certification diagnostics. The implemented alternate API plan uses
`dailyData/byState`, one state-year per response, with `AQS_API_EMAIL` and
`AQS_API_KEY` read from environment variables. The key and email are redacted
from persisted URLs. API mode is suitable for validation or constrained
re-extraction, not the preferred national build.

### NOAA

Primary acquisition is `by_year` GHCN-Daily bulk CSV gzip plus station,
inventory, states, version, and README files. It requires no token. TMAX is
accepted only when the value is not the documented missing sentinel, QFLAG is
blank, and SFLAG is a documented nonblank source code; flags and observation
time remain in the audit trail. The much larger all-station tarball is
unnecessary. NOAA's CDO API is not needed for the planned build and therefore
introduces no secret requirement.

## Acquired inventory and role separation

- EPA manifest: 39 records—11 daily, 11 hourly, and 11 annual archives plus six
  metadata/reference files. Exact bytes and checksums are in
  `data/raw/epa/manifest.jsonl`.
- NOAA manifest: 18 records—11 yearly archives plus seven metadata/format files.
  Exact bytes and checksums are in `data/raw/noaa/manifest.jsonl`.
- No 2026 yearly observation archive is in the planned or acquired
  confirmatory inventory.

The raw directories and manifests are ignored by Git. Release documentation
will publish a checksum inventory without placing the large raw artifacts in
the repository.

## Acquisition-time required metadata

For every downloaded file, `manifest.jsonl` contains publisher, dataset, title,
exact redacted request URL, UTC retrieval timestamp, filename, bytes, SHA-256,
upstream Last-Modified, upstream ETag, upstream content length, content type,
HTTP status, resumed-byte count, and use-conditions note. Existing files are
reused only when one manifest record, size, and checksum all agree. HTTP,
checksum, schema, decompression, or source-year failures stop validation.
