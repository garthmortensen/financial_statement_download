"""
Download SEC filings (10-K, 10-Q, ...) via EDGAR for the banks in corpus/banks.yml.

Designed to be run once per quarter: each run stores its downloads in a separate
subdirectory named after the current quarter (e.g. <output_dir>/2026Q3/), and
accessions already recorded in corpus/manifest.yml are skipped, so each pull
contains only the filings that are new since the last run. Every downloaded
filing is appended to the manifest.

To save disk space, only the primary document of each filing is kept:
full-submission.txt is deleted after download.

Usage:
    python corpus/downloader_sec.py             # all banks from corpus/banks.yml
    python corpus/downloader_sec.py JPM BAC     # only specific tickers/CIKs

Files land in <output_dir>/<run_id>/sec-edgar-filings/<TICKER>/<FORM>/<accession>/
The `sec-edgar-downloader` library handles rate limiting (10 req/s cap);
transient failures are retried with exponential backoff via tenacity.
"""

import os
import sys
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
from sec_edgar_downloader import Downloader
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from manifest_utils import append_entries, current_run_id, load_manifest, sec_accessions

load_dotenv()

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


class TransientHTTPError(Exception):
    """HTTP 429 / 5xx — worth retrying with backoff."""


RETRY_KWARGS = {
    "retry": retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout, TransientHTTPError)
    ),
    "wait": wait_exponential_jitter(initial=1, max=60),
    "stop": stop_after_attempt(5),
    "reraise": True,
}


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_banks(banks_file: str) -> list[dict]:
    with open(banks_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["banks"]


def bank_identifier(bank: dict) -> str:
    """Ticker if the bank has one, otherwise its zero-padded CIK."""
    ticker = bank.get("ticker")
    if ticker:
        return str(ticker).upper()
    return str(bank["cik"])


@retry(**RETRY_KWARGS)
def _get_submissions(cik: str, user_agent: str) -> dict:
    url = SUBMISSIONS_URL.format(cik=cik)
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=30)
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TransientHTTPError(f"HTTP {resp.status_code} for {url}")
    resp.raise_for_status()
    return resp.json()


@retry(**RETRY_KWARGS)
def _fetch_form(dl: Downloader, identifier: str, form: str, limit: int, skip: set[str]) -> int:
    return dl.get(
        form,
        identifier,
        limit=limit,
        download_details=True,
        accession_numbers_to_skip=skip or None,
    )


def fetch_filing_metadata(
    dl: Downloader, identifier: str, forms: dict[str, int]
) -> dict[str, dict]:
    """Map accession number -> manifest fields for the bank's recent filings.

    Note: only covers the "recent" submissions window (~1000 filings); filings
    older than that get a minimal fallback manifest entry instead."""
    if identifier.isdigit():
        cik = identifier
    else:
        cik = dl.ticker_to_cik_mapping[identifier]
    data = _get_submissions(cik, dl.user_agent)
    company_name = data["name"]
    recent = data["filings"]["recent"]

    metadata = {}
    for form, accession, primary_doc, report_date in zip(
        recent["form"],
        recent["accessionNumber"],
        recent["primaryDocument"],
        recent["reportDate"],
    ):
        if form not in forms:
            continue
        acc_no_dash = accession.replace("-", "")
        link = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{acc_no_dash}/{primary_doc}"
        )
        filetype = Path(primary_doc).suffix.lstrip(".") or "htm"
        metadata[accession] = {
            "source": "SEC EDGAR",
            "name": f"{company_name} {report_date}",
            "category": form,
            "filetype": filetype,
            "link": link,
            "method": "API",
        }
    return metadata


def prune_full_submission(accession_dir: Path) -> None:
    """Keep only the primary document; the full submission (all exhibits, XBRL)
    can be tens of MB per filing."""
    full_submission = accession_dir / "full-submission.txt"
    primary_document = accession_dir / "primary-document.html"
    if full_submission.exists() and primary_document.exists():
        full_submission.unlink()


def record_new_filings(
    run_dir: Path,
    identifier: str,
    form: str,
    known: set[str],
    metadata: dict[str, dict],
    run_id: str,
) -> list[dict]:
    """Build manifest entries for accessions downloaded into this run's directory."""
    filings_dir = run_dir / "sec-edgar-filings" / identifier / form
    entries = []
    if not filings_dir.is_dir():
        return entries

    for accession_dir in sorted(filings_dir.iterdir()):
        if not accession_dir.is_dir():
            continue
        accession = accession_dir.name
        if accession in known:
            continue
        prune_full_submission(accession_dir)
        if accession in metadata:
            entry = dict(metadata[accession])
        else:
            entry = {
                "source": "SEC EDGAR",
                "name": f"{identifier} {form} {accession}",
                "category": form,
                "filetype": "htm",
                "link": "",
                "method": "API",
            }
        entry["pulled"] = run_id
        entry["path"] = str(accession_dir)
        entries.append(entry)
    return entries


def download_filings(cfg: dict, banks: list[dict]) -> int:
    """Pull new filings for each bank into this quarter's run directory.
    Returns the number of failures."""
    sec_cfg = cfg["sec"]
    manifest_file = cfg["manifest_file"]

    user_name = os.environ["SEC_USER_NAME"]
    user_email = os.environ["SEC_USER_EMAIL"]

    run_id = current_run_id()
    run_dir = Path(sec_cfg["output_dir"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"Storing this pull in {run_dir}")

    dl = Downloader(user_name, user_email, run_dir)
    forms: dict[str, int] = sec_cfg["forms"]

    known = sec_accessions(load_manifest(manifest_file))

    new_entries = []
    failures = []
    for bank in banks:
        identifier = bank_identifier(bank)
        try:
            metadata = fetch_filing_metadata(dl, identifier, forms)
        except Exception as exc:
            print(f"  FAILED metadata for {identifier}: {exc}")
            failures.append(identifier)
            continue

        for form, limit in forms.items():
            skip = known.get((identifier, form), set())
            print(f"Fetching up to {limit} new {form}(s) for {identifier} "
                  f"({len(skip)} already in manifest) ...")
            try:
                count = _fetch_form(dl, identifier, form, limit, skip)
            except Exception as exc:
                print(f"  FAILED: {exc}")
                failures.append(f"{identifier} {form}")
                continue
            entries = record_new_filings(run_dir, identifier, form, skip, metadata, run_id)
            new_entries.extend(entries)
            print(f"  OK  {count} new -> {run_dir / 'sec-edgar-filings' / identifier / form}")

    append_entries(new_entries, manifest_file)

    if failures:
        print(f"\n{len(failures)} failure(s): {', '.join(failures)}")
    return len(failures)


def select_banks(banks: list[dict], identifiers: list[str]) -> list[dict]:
    """Match CLI identifiers against banks.yml; unknown ones become ad-hoc entries."""
    selected = []
    for raw_identifier in identifiers:
        identifier = raw_identifier.upper()
        match = None
        for bank in banks:
            if bank_identifier(bank) == identifier:
                match = bank
                break
        if match is not None:
            selected.append(match)
        elif identifier.isdigit():
            selected.append({"name": identifier, "cik": identifier})
        else:
            selected.append({"name": identifier, "ticker": identifier})
    return selected


if __name__ == "__main__":
    cfg = _load_config()
    banks = load_banks(cfg["sec"]["banks_file"])

    args = sys.argv[1:]
    if args:
        banks = select_banks(banks, args)

    failure_count = download_filings(cfg, banks)
    if failure_count:
        sys.exit(1)
