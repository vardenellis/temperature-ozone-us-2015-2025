# EPA 2025 reporting, completeness, and certification audit

**Status:** RESOLVED for the acquired 2025 snapshot; the publication-time
upstream-revision check remains PROVISIONAL. This audit is outcome-blind. It
uses dates, record-identification fields, observation counts, ozone-season
metadata, and certification labels, but does not summarize ozone
concentrations or join ozone to weather.

## Source snapshot

The official EPA AirData inventory identifies both
`daily_44201_2025.zip` and `annual_conc_by_monitor_2025.zip` as created on
2026-06-25. The [AirData download page](https://aqs.epa.gov/aqsweb/airdata/download_files.html)
reports 381,023 rows for the 2025 daily ozone file and 65,709 rows for the 2025
annual concentration-by-monitor file, each "As of 2026-06-25." EPA describes
the June bulk-file refresh as capturing complete data for the prior year. Here,
"complete" describes the scheduled reporting snapshot; it does not mean that
every monitor record has completed annual certification or that EPA cannot
later revise AQS data.

The immutable local artifacts were retrieved on 2026-07-15 UTC (2026-07-14 in
the project time zone) from official EPA HTTPS endpoints:

| Artifact | Bytes | SHA-256 | AirData created | HTTP last modified |
|---|---:|---|---|---|
| `daily_44201_2025.zip` | 4,560,934 | `0ba74dbf2f35882a9273468edf9a443274590fe71770b98aab3c427311ca069f` | 2026-06-25 | 2026-07-13 |
| `annual_conc_by_monitor_2025.zip` | 3,785,819 | `7af948b3dcaf2d214e7d8fdcfb8ab7b4b6dd9865a43ead6f1e21955bcc326cb8` | 2026-06-25 | 2026-07-13 |

The AirData-created date comes from the acquired official `file_list.csv`; the
HTTP date comes from the response metadata in the immutable manifest. The
latest `Date of Last Change` among records used in this audit was 2026-06-25.
These three dates describe different layers of provenance and are therefore
retained separately. The AirData-created snapshot is 176 days after the end of
the 2025 study year; that lag supports a mature reporting snapshot but does not
establish universal certification or prevent later revision.

## Reporting and certification timing

[40 CFR 58.16(b)](https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-58/subpart-B/section-58.16)
requires routine ambient-air data for each quarter to reach AQS within 90 days
after the quarter ends. The ordinary deadline for 2025 fourth-quarter data was
therefore 2026-03-31. [40 CFR 58.15(a)](https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-58/subpart-B/section-58.15)
requires the annual certification letter for the previous calendar year by May
1, making 2026-05-01 the ordinary certification deadline for 2025 data. The
acquired June 25 snapshot follows both deadlines.

Certification is a distinct process. The official
[AirData file-format documentation](https://aqs.epa.gov/aqsweb/airdata/FileFormats.html)
defines `Certification Indicator` as the submitter/EPA certification status of
an annual monitor summary. EPA also cautions outside users that data may remain
under review before the certification deadline and explains that later changes
can reset a certification flag. Consequently, availability in the June bulk
file is evidence of reporting maturity, not evidence that every 2025 monitor
record is certified or immutable upstream.

## Apparent site-season availability

The implemented `assess_epa_2025_completeness` audit applied the following
prespecified, value-blind procedure to `daily_44201_2025.zip`:

1. Retain the 48 contiguous states and the District of Columbia.
2. Identify parameter 44201 records with sample duration
   `8-HR RUN AVG BEGIN HOUR`, pollutant standard `Ozone 8-hour 2015`, and unit
   `Parts per million`.
3. Retain the frozen event policy (`None` or `Included`).
4. Count a monitor-date as complete when `Observation Count >= 13`.
5. Form a site-date availability set by taking the union of qualifying
   monitor-date records at each AQS site. This union is only an availability
   diagnostic; it is not the final Appendix U site-hour reconstruction and does
   not inspect `1st Max Value`.
6. Divide qualifying site dates within the site's official 2025 AQS ozone
   season by the number of calendar days in that season. Site-, county-, and
   state-specific rows from the acquired official `ozone_seasons.csv` are
   applied in that order.

The input contained 381,023 daily rows. Of these, 378,799 were in the
contiguous-domain definition, 378,702 also met the target record and event
rules, and 370,017 monitor-date records also met the 13-window count rule.
After unioning monitor dates, 1,202 sites had at least one qualifying date in
2025. Their apparent required-season coverage was:

| Coverage diagnostic | Sites | Fraction of 1,202 sites |
|---|---:|---:|
| At least 75% | 1,135 | 94.426% |
| At least 90% | 1,043 | 86.772% |
| Below 75% | 67 | 5.574% |
| Below 90% | 159 | 13.228% |

The median site-season fraction was 0.975510. The minimum was 0.000000; two
sites had qualifying dates elsewhere in 2025 but none within the season in the
official season table. Those records are retained as a diagnostic warning and
must not be treated as season-complete. These figures measure apparent data
availability, not regulatory design-value completeness and not certification.

## Annual monitor certification indicators

The annual audit retained contiguous-domain records for the same parameter,
duration, standard, and unit, with `Events Included` or `No Events`. It found
1,243 records, each corresponding to a distinct site-parameter-POC monitor key;
no key was duplicated after these filters.

| Certification indicator | Monitor records | Fraction of 1,243 |
|---|---:|---:|
| Certified | 800 | 64.360% |
| Requested but not yet concurred | 350 | 28.158% |
| Certification not required | 84 | 6.758% |
| Certified - QA issues identified | 8 | 0.644% |
| Was Certified but data changed | 1 | 0.080% |

The categories are reported as EPA supplied them. In particular, "requested
but not yet concurred" is not recoded as either certified or invalid, and
"certification not required" is not interpreted as a quality judgment.

## Inclusion recommendation

**PROVISIONAL recommendation:** retain 2025 within the prespecified 2015–2025
confirmatory scope, but do not describe the year as universally certified or
final. Before constructing the panel, apply the same outcome-blind site-season
retention rule used for every study year and carry annual certification status
into the validation report. The one changed-after-certification record and all
pending-concurrence records require explicit QA accounting; certification
status alone should not be used to select monitors after outcomes are viewed.

The acquired June snapshot is late enough to pass the ordinary quarterly
reporting and annual-certification deadlines, and its availability coverage
does not justify excluding 2025 wholesale. Before a public release, recheck the
official AirData inventory without inspecting results. If EPA has revised any
2025 artifact, acquire the new bytes as a separate immutable snapshot, compare
manifests, and rerun construction and validation from the beginning. Any change
to this rule after outcome inspection must be recorded as a deviation.
