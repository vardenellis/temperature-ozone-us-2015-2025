"""Apply deterministic reader-facing bibliography formatting to rendered HTML."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

EPA_KEYS = (
    "epa_formats",
    "epa2026_cy2025_certification",
    "ecfr_appendix_u",
    "epa_airdata_public_domain",
    "epa_airdata",
)
EPA_AUTHOR = "U.S. Environmental Protection Agency"
REFERENCE_CONTINUATION_KEY = "ecfr_appendix_u"
LOWERCASE_JOURNAL_KEY = "bao2025"
LOWERCASE_JOURNAL_NAME = "npj Clean Air"


def finalize(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for key in EPA_KEYS:
        if f'id="ref-{key}"' not in text:
            continue
        pattern = re.compile(
            rf'(<div id="ref-{re.escape(key)}" class="csl-entry" role="listitem">\s*)'
            r"(?:———|U\.S\. Environmental Protection Agency)\."
        )
        text, count = pattern.subn(rf"\1{EPA_AUTHOR}.", text, count=1)
        if count != 1:
            raise RuntimeError(f"could not normalize EPA bibliography author: {key}")
    if f'id="ref-{LOWERCASE_JOURNAL_KEY}"' in text:
        journal_entry = re.compile(
            rf'(<div id="ref-{LOWERCASE_JOURNAL_KEY}" '
            r'class="csl-entry" role="listitem">.*?)'
            r"(?:<span>)?(?:Npj|npj)(?:</span>)? Clean Air",
            flags=re.DOTALL,
        )
        text, count = journal_entry.subn(rf"\1{LOWERCASE_JOURNAL_NAME}", text, count=1)
        if count != 1:
            raise RuntimeError(
                "could not preserve official lowercase npj journal styling"
            )
    continuation_marker = f'id="ref-{REFERENCE_CONTINUATION_KEY}"'
    if continuation_marker in text:
        continuation = (
            "</div>\n"
            '<h3 class="references-continuation">References (continued)</h3>\n'
            '<div id="refs-continued" '
            'class="references csl-bib-body hanging-indent" '
            'data-entry-spacing="0" role="list">\n'
        )
        if continuation in text:
            raise RuntimeError("references continuation heading already present")
        text = text.replace(
            f"<div {continuation_marker}",
            f"{continuation}<div {continuation_marker}",
            1,
        )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    finalize(args.path)


if __name__ == "__main__":
    main()
