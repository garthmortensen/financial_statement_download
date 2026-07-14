"""
Shared helpers for the download manifest (corpus/manifest.yml).

The manifest is PROGRAM-OWNED: scripts append an entry for every document they
download. Do not hand-edit it. User-edited inputs live in config.yml,
corpus/banks.yml, and corpus/sources.yml.

Manifest entry schema (documents: list):
    source:   SEC EDGAR | website
    name:     human-readable document name
    category: 10-K | 10-Q | IR | ...
    filetype: htm | pdf | ...
    link:     original URL
    method:   API | Manual
    pulled:   quarterly run id (e.g. 2026Q3) or "legacy" for pre-manifest pulls
    path:     local path to the downloaded file/directory
"""

from datetime import date
from pathlib import Path

import yaml

MANIFEST_FILE = "corpus/manifest.yml"


def current_run_id(today: date | None = None) -> str:
    """Quarterly run label, e.g. '2026Q3' — one storage directory per quarterly pull."""
    if today is None:
        today = date.today()
    quarter = (today.month - 1) // 3 + 1
    return f"{today.year}Q{quarter}"


def load_manifest(path: str = MANIFEST_FILE) -> list[dict]:
    """Return the list of manifest entries (empty list if no manifest exists yet)."""
    manifest_path = Path(path)
    if not manifest_path.exists():
        return []
    with open(manifest_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "documents" not in data or data["documents"] is None:
        return []
    return data["documents"]


def append_entries(entries: list[dict], path: str = MANIFEST_FILE) -> None:
    """Append entries to the manifest (read -> extend -> full rewrite)."""
    if not entries:
        return
    documents = load_manifest(path)
    for entry in entries:
        documents.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"documents": documents}, f, sort_keys=False, allow_unicode=True)
    print(f"Manifest: appended {len(entries)} entries ({len(documents)} total) -> {path}")


def manifest_links(documents: list[dict]) -> set[str]:
    """Set of all links already recorded in the manifest (dedupe key for downloads)."""
    links = set()
    for entry in documents:
        link = entry.get("link")
        if link:
            links.add(link)
    return links


def sec_accessions(documents: list[dict]) -> dict[tuple[str, str], set[str]]:
    """Map (ticker_or_cik, form) -> accession numbers already downloaded.

    Parsed from each SEC entry's path, which always ends with
    .../sec-edgar-filings/<TICKER>/<FORM>/<accession>."""
    accessions: dict[tuple[str, str], set[str]] = {}
    for entry in documents:
        if entry.get("source") != "SEC EDGAR":
            continue
        entry_path = entry.get("path")
        if not entry_path:
            continue
        parts = Path(entry_path).parts
        if len(parts) < 3 or "sec-edgar-filings" not in parts:
            continue
        accession = parts[-1]
        form = parts[-2]
        ticker = parts[-3]
        key = (ticker, form)
        if key not in accessions:
            accessions[key] = set()
        accessions[key].add(accession)
    return accessions
