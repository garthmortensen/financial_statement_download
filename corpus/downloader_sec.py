"""
Download SEC filings (10-K, 10-Q, ...) via EDGAR for the banks in corpus/banks.yml.

Each run stores its downloads in a separate subdirectory named after the current
quarter (e.g. <output_dir>/2026Q3/). To save disk space, only the primary document
of each filing is kept: full-submission.txt is deleted after download.

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

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from sec_edgar_downloader import Downloader
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from log_utils import setup_logging

load_dotenv()

log = None  # bound in __main__ via setup_logging


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
    """Ticker or CIK for EDGAR API calls."""
    ticker = bank.get("ticker")
    if ticker:
        return str(ticker).upper()
    return str(bank["cik"])


def bank_folder_name(bank: dict) -> str:
    """Folder name for downloaded files: ticker, then placeholder_ticker, then CIK."""
    ticker = bank.get("ticker")
    if ticker:
        return str(ticker).upper()
    placeholder = bank.get("placeholder_ticker")
    if placeholder:
        return str(placeholder).upper()
    return str(bank["cik"])


@retry(**RETRY_KWARGS)
def _fetch_form(dl: Downloader, identifier: str, form: str, limit: int, skip: set[str]) -> int:
    return dl.get(
        form,
        identifier,
        limit=limit,
        download_details=True,
        accession_numbers_to_skip=skip or None,
    )


def prune_filings(run_dir: Path, identifier: str, form: str) -> None:
    """Keep only primary-document.html in each accession dir; delete everything else."""
    filings_dir = run_dir / "sec-edgar-filings" / identifier / form
    if not filings_dir.is_dir():
        return
    for accession_dir in filings_dir.iterdir():
        if not accession_dir.is_dir():
            continue
        for file in accession_dir.iterdir():
            if file.name != "primary-document.html":
                file.unlink()


def quarter_range(start: str, end: str) -> list[str]:
    """Return every quarter label from start to end inclusive, e.g.
    quarter_range('2022Q3', '2023Q1') -> ['2022Q3', '2022Q4', '2023Q1']."""
    quarters = []
    for period in pd.period_range(start, end, freq="Q"):
        quarters.append(str(period))
    return quarters


def download_filings(cfg: dict, banks: list[dict]) -> int:
    """Pull filings for each bank across all configured quarters.
    Returns the total number of failures."""
    sec_cfg = cfg["sec_download_settings"]
    pull_cfg = sec_cfg["pull_quarters"]
    quarters = quarter_range(pull_cfg["start"], pull_cfg["end"])
    forms: dict[str, int] = sec_cfg["forms"]
    base_dir = Path(sec_cfg["output_dir"])

    user_name = os.environ["SEC_USER_NAME"]
    user_email = os.environ["SEC_USER_EMAIL"]

    log.info("run_started", quarters=quarters, banks=len(banks))

    total_failures = []
    for quarter in quarters:                                    # e.g. "2026Q3"
        run_dir = base_dir / quarter                            # e.g. corpus/raw_data/sec/2026Q3
        run_dir.mkdir(parents=True, exist_ok=True)
        qlog = log.bind(quarter=quarter)
        qlog.info("quarter_start", run_dir=str(run_dir))

        dl = Downloader(user_name, user_email, run_dir)

        for bank in banks:
            identifier = bank_identifier(bank)                  # e.g. "JPM" or "0000811830" (for API)
            folder_name = bank_folder_name(bank)                # e.g. "JPM" or "SAN" (for folder)
            blog = qlog.bind(bank=folder_name)
            blog.info("bank_start")
            for form, limit in forms.items():                   # e.g. form="10-K", limit=1
                # Skip the download entirely if the form directory is already populated
                target_form_dir = run_dir / "sec-edgar-filings" / folder_name / form
                already_populated = False
                if target_form_dir.is_dir():
                    for entry in target_form_dir.iterdir():
                        if entry.is_dir():
                            already_populated = True
                            break
                if already_populated:
                    blog.info("form_skipped", form=form)
                    continue
                try:
                    count = _fetch_form(dl, identifier, form, limit, set())
                except Exception as exc:
                    blog.error("fetch_failed", form=form, error=str(exc))
                    total_failures.append(f"{folder_name} {form}")
                    continue
                # For CIK-only banks, move downloaded dirs from CIK folder to placeholder folder
                if identifier != folder_name:
                    cik_form_dir = run_dir / "sec-edgar-filings" / identifier / form
                    if cik_form_dir.is_dir():
                        target_form_dir.mkdir(parents=True, exist_ok=True)
                        for acc_dir in cik_form_dir.iterdir():
                            if acc_dir.is_dir():
                                acc_dir.rename(target_form_dir / acc_dir.name)
                        cik_form_dir.rmdir()
                        cik_bank_dir = run_dir / "sec-edgar-filings" / identifier
                        try:
                            cik_bank_dir.rmdir()
                        except OSError:
                            pass
                # files now in run_dir/sec-edgar-filings/JPM/10-K/0001628280-26-008131/
                prune_filings(run_dir, folder_name, form)
                blog.info("form_done", form=form, downloaded=count)  # count=1
            print()

        qlog.info("quarter_done")

    if total_failures:
        log.warning("run_failures", count=len(total_failures), failures=total_failures)
    log.info("run_finished", failures=len(total_failures))
    return len(total_failures)


def select_banks(banks: list[dict], identifiers: list[str]) -> list[dict]:
    """Match CLI identifiers against banks.yml; unknown ones become ad-hoc entries."""
    selected = []
    for raw_identifier in identifiers:
        identifier = raw_identifier.upper()
        match = None
        for bank in banks:
            if bank_identifier(bank) == identifier or bank_folder_name(bank) == identifier:
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
    log = setup_logging(cfg["log_dir"], "downloader_sec")
    banks = load_banks(cfg["sec_download_settings"]["banks_file"])

    args = sys.argv[1:]
    if args:
        banks = select_banks(banks, args)

    failure_count = download_filings(cfg, banks)
    if failure_count:
        sys.exit(1)
