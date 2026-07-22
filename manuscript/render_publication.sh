#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
python=${PYTHON:-python3}
doi="10.5281/zenodo.21434897"
metadata_tool="manuscript/apply_pdf_metadata.py"
if [[ ! -f "$metadata_tool" ]]; then
  metadata_tool="scripts/apply_pdf_metadata.py"
fi
chrome=${CHROME_BIN:-}
if [[ -z "$chrome" ]]; then
  for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "$candidate" >/dev/null 2>&1; then
      chrome=$(command -v "$candidate")
      break
    fi
  done
fi
if [[ -z "$chrome" ]]; then
  echo "No Chromium-compatible renderer found; set CHROME_BIN." >&2
  exit 1
fi

for stem in manuscript supplement; do
  if [[ "$stem" == "manuscript" ]]; then
    title="Temperature Distributions and Temperature-Standardized Ozone Change Across U.S. Monitoring Sites, 2015–2025"
  else
    title="Supplement to: Temperature Distributions and Temperature-Standardized Ozone Change Across U.S. Monitoring Sites, 2015–2025"
  fi
  pandoc "manuscript/${stem}.md" \
    --standalone \
    --citeproc \
    --bibliography manuscript/references.bib \
    --resource-path manuscript \
    --embed-resources \
    --css manuscript/publication.css \
    --metadata pagetitle="$title" \
    --output "manuscript/${stem}.html"
  "$python" scripts/finalize_publication_html.py "manuscript/${stem}.html"
  "$chrome" \
    --headless \
    --no-sandbox \
    --disable-gpu \
    --no-pdf-header-footer \
    --print-to-pdf="${root}/manuscript/${stem}.pdf" \
    "file://${root}/manuscript/${stem}.html"
  "$python" "$metadata_tool" \
    "manuscript/${stem}.pdf" --doi "$doi" --kind "$stem"
done
