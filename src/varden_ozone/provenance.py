"""Immutable-download and provenance-manifest primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast

import httpx

from varden_ozone.execution_guard import require_acquisition

_SECRET_PATTERN = re.compile(r"([?&](?:key|email)=)[^&]+", re.IGNORECASE)
_CONTENT_RANGE_PATTERN = re.compile(r"^bytes (\d+)-(\d+)/(\d+|\*)$")


def redact_url(url: str) -> str:
    """Remove API key and email query values before persistence or display."""
    return _SECRET_PATTERN.sub(r"\1REDACTED", url)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the lowercase SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_response(response: httpx.Response, handle: BinaryIO) -> int:
    byte_count = 0
    for chunk in response.iter_raw():
        handle.write(chunk)
        byte_count += len(chunk)
    return byte_count


@dataclass(frozen=True)
class PartialTransferMetadata:
    """Upstream validators binding a partial file to one remote version."""

    url: str
    upstream_last_modified: str | None
    upstream_etag: str | None


def _write_partial_metadata(path: Path, metadata: PartialTransferMetadata) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(asdict(metadata), handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _read_partial_metadata(path: Path) -> PartialTransferMetadata:
    try:
        with path.open(encoding="utf-8") as handle:
            return PartialTransferMetadata(**json.load(handle))
    except (FileNotFoundError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError(
            f"missing or invalid partial-transfer metadata: {path}"
        ) from exc


def _raise_for_status_redacted(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        safe_url = redact_url(str(response.request.url))
        raise RuntimeError(
            f"HTTP {response.status_code} while retrieving {safe_url}"
        ) from None


@dataclass(frozen=True)
class ProvenanceRecord:
    """One immutable source artifact and its retrieval metadata."""

    publisher: str
    dataset: str
    title: str
    url: str
    retrieved_at_utc: str
    filename: str
    bytes: int
    sha256: str
    upstream_last_modified: str | None
    upstream_etag: str | None
    upstream_content_length: int | None
    content_type: str | None
    http_status: int
    resumed_from_bytes: int
    use_conditions: str


def append_manifest(manifest: Path, record: ProvenanceRecord) -> None:
    """Append one canonical JSON record and fsync it to disk."""
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as handle:
        json.dump(asdict(record), handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_manifest(manifest: Path) -> list[ProvenanceRecord]:
    """Read and validate every JSON Lines record in a raw-data manifest."""
    if not manifest.exists():
        return []
    records: list[ProvenanceRecord] = []
    with manifest.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                payload = json.loads(line)
                records.append(ProvenanceRecord(**payload))
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(
                    f"invalid manifest record {manifest}:{line_number}"
                ) from exc
    return records


def verify_existing_artifact(destination: Path, manifest: Path) -> ProvenanceRecord:
    """Return the recorded artifact only when bytes and manifest still agree."""
    matches = [
        record
        for record in read_manifest(manifest)
        if record.filename == destination.name
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one manifest record for existing raw file {destination}; "
            f"found {len(matches)}"
        )
    record = matches[0]
    size = destination.stat().st_size
    if size != record.bytes:
        raise ValueError(
            f"size mismatch for immutable raw file {destination}: "
            f"manifest={record.bytes}, actual={size}"
        )
    digest = sha256_file(destination)
    if digest != record.sha256:
        raise ValueError(
            f"checksum mismatch for immutable raw file {destination}: "
            f"manifest={record.sha256}, actual={digest}"
        )
    return record


def download_immutable(
    *,
    client: httpx.Client,
    url: str,
    destination: Path,
    manifest: Path,
    publisher: str,
    dataset: str,
    title: str,
    use_conditions: str,
    params: dict[str, str] | None = None,
) -> ProvenanceRecord:
    """Stream a source file once, checksum it, and atomically install it.

    Existing valid destinations are reused without network activity. Partial
    transfers are resumed when the server honors HTTP Range. Query credentials
    are redacted from the manifest, and final raw files are never overwritten.
    """
    require_acquisition("immutable source acquisition")
    if destination.exists():
        return verify_existing_artifact(destination, manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(f"{destination.suffix}.part")
    partial_metadata_path = destination.with_suffix(
        f"{destination.suffix}.part.meta.json"
    )
    resumed_from = partial.stat().st_size if partial.exists() else 0
    headers: dict[str, str] = {}
    prior_metadata: PartialTransferMetadata | None = None
    if resumed_from:
        prior_metadata = _read_partial_metadata(partial_metadata_path)
        validator = (
            prior_metadata.upstream_etag or prior_metadata.upstream_last_modified
        )
        if not validator:
            raise ValueError(
                "cannot safely resume a partial file without an upstream validator"
            )
        headers = {"Range": f"bytes={resumed_from}-", "If-Range": validator}
    elif partial_metadata_path.exists():
        raise ValueError(f"orphaned partial-transfer metadata: {partial_metadata_path}")

    try:
        with client.stream("GET", url, params=params, headers=headers) as response:
            _raise_for_status_redacted(response)
            if resumed_from and response.status_code == 206:
                content_range = response.headers.get("content-range", "")
                match = _CONTENT_RANGE_PATTERN.fullmatch(content_range)
                if match is None or int(match.group(1)) != resumed_from:
                    raise ValueError(
                        "ranged response does not begin at the partial-file boundary"
                    )
                if int(match.group(2)) < int(match.group(1)):
                    raise ValueError("invalid HTTP Content-Range bounds")
                assert prior_metadata is not None
                response_url = redact_url(str(response.request.url))
                if response_url != prior_metadata.url:
                    raise ValueError("request URL changed during resumed transfer")
                current_etag = response.headers.get("etag")
                current_modified = response.headers.get("last-modified")
                if prior_metadata.upstream_etag and (
                    current_etag != prior_metadata.upstream_etag
                ):
                    raise ValueError("ETag changed during resumed transfer")
                if not prior_metadata.upstream_etag and (
                    current_modified != prior_metadata.upstream_last_modified
                ):
                    raise ValueError("Last-Modified changed during resumed transfer")
                mode = "ab"
            elif resumed_from and response.status_code == 200:
                mode = "wb"
                resumed_from = 0
            elif not resumed_from and response.status_code == 200:
                mode = "xb"
            else:
                raise ValueError(
                    f"unexpected HTTP status {response.status_code} for "
                    f"{redact_url(str(response.request.url))}"
                )
            current_metadata = PartialTransferMetadata(
                url=redact_url(str(response.request.url)),
                upstream_last_modified=response.headers.get("last-modified"),
                upstream_etag=response.headers.get("etag"),
            )
            _write_partial_metadata(partial_metadata_path, current_metadata)
            with partial.open(mode) as raw_handle:
                handle = cast(BinaryIO, raw_handle)
                transferred = _copy_response(response, handle)
                handle.flush()
                os.fsync(handle.fileno())
            byte_count = partial.stat().st_size
            response_length = response.headers.get("content-length")
            if response_length is not None and transferred != int(response_length):
                raise ValueError(
                    f"HTTP content-length mismatch for {current_metadata.url}: "
                    f"header={response_length}, transferred={transferred}"
                )
            total_length = byte_count
            content_range = response.headers.get("content-range", "")
            range_match = _CONTENT_RANGE_PATTERN.fullmatch(content_range)
            if range_match is not None and range_match.group(3) != "*":
                total_length = int(range_match.group(3))
            if byte_count != total_length:
                raise ValueError(
                    f"incomplete ranged transfer for {current_metadata.url}: "
                    f"expected={total_length}, actual={byte_count}"
                )
            record = ProvenanceRecord(
                publisher=publisher,
                dataset=dataset,
                title=title,
                url=redact_url(str(response.request.url)),
                retrieved_at_utc=datetime.now(UTC).isoformat(),
                filename=destination.name,
                bytes=byte_count,
                sha256=sha256_file(partial),
                upstream_last_modified=response.headers.get("last-modified"),
                upstream_etag=response.headers.get("etag"),
                upstream_content_length=total_length,
                content_type=response.headers.get("content-type"),
                http_status=response.status_code,
                resumed_from_bytes=resumed_from,
                use_conditions=use_conditions,
            )
        partial.replace(destination)
        append_manifest(manifest, record)
        partial_metadata_path.unlink(missing_ok=True)
        return record
    except httpx.HTTPError as exc:
        # Transport exceptions can retain the fully parameterized request.
        # Replace them with a credential-safe error before callers log them.
        request = exc.request
        safe_url = redact_url(str(request.url))
        raise RuntimeError(
            f"HTTP transfer failed while retrieving {safe_url}: {type(exc).__name__}"
        ) from None
    except BaseException:
        # Keep partial bytes for a safe retry. They are never treated as raw data.
        raise
