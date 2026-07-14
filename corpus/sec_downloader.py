"""
Download SEC filings (10-K, 10-Q, ...) via EDGAR.

Forms and per-form limits come from config.yml (sec.forms). Already-downloaded
accessions are skipped, so quarterly reruns only fetch new filings.

Usage:
    python corpus/sec_downloader.py                    # uses tickers from config.yml
    python corpus/sec_downloader.py AAPL MSFT GOOG     # pass tickers as args
    python corpus/sec_downloader.py --manifest         # write a data_sources.csv-style manifest

Files land in <output_dir>/sec-edgar-filings/<TICKER>/<FORM>/<accession>/
The `sec-edgar-downloader` library handles rate limiting (10 req/s cap).
"""

import csv
import os
import sys
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
from sec_edgar_downloader import Downloader

load_dotenv()

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
MANIFEST_FILE = "corpus/data_sources_sec.csv"


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["sec"]


def fetch_filing_rows(
    dl: Downloader, tickers: list[str], forms: dict[str, int], user_agent: str
) -> list[dict]:
    """Build data_sources.csv-style rows (Source, Name, Category, Filetype, Link) via the
    SEC submissions API, matching the schema downloader.py already expects.

    Note: only searches the "recent" submissions window (~1000 filings). For heavy
    filers (e.g. JPM's daily 424B2s) that window may not reach back far enough to
    contain all requested filings; the download path paginates and is not affected."""
    rows = []
    for ticker in tickers:
        cik = dl.ticker_to_cik_mapping[ticker]
        resp = requests.get(
            SUBMISSIONS_URL.format(cik=cik), headers={"User-Agent": user_agent}, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        company_name = data["name"]
        recent = data["filings"]["recent"]

        counts = dict.fromkeys(forms, 0)
        for form, accession, primary_doc, report_date in zip(
            recent["form"],
            recent["accessionNumber"],
            recent["primaryDocument"],
            recent["reportDate"],
        ):
            if form not in forms or counts[form] >= forms[form]:
                continue
            acc_no_dash = accession.replace("-", "")
            link = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{acc_no_dash}/{primary_doc}"
            )
            filetype = Path(primary_doc).suffix.lstrip(".") or "htm"
            rows.append({
                "Source": "SEC EDGAR",
                "Name": f"{company_name} {report_date}",
                "Category": form,
                "Filetype": filetype,
                "Link": link,
            })
            counts[form] += 1
            if all(counts[f] >= forms[f] for f in forms):
                break

    return rows


def write_manifest(rows: list[dict], path: str = MANIFEST_FILE) -> None:
    """Write rows out in the same Source,Name,Category,Filetype,Link schema as data_sources.csv
    so they can be fed straight into downloader.py's generic download pipeline."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Source", "Name", "Category", "Filetype", "Link"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def existing_accessions(output_dir: Path, ticker: str, form: str) -> set[str]:
    """Accession numbers already on disk for this ticker/form (for incremental reruns)."""
    filings_dir = output_dir / "sec-edgar-filings" / ticker / form
    if not filings_dir.is_dir():
        return set()
    return {d.name for d in filings_dir.iterdir() if d.is_dir()}


def download_filings(tickers: list[str]) -> None:
    cfg = _load_config()

    user_name = os.environ["SEC_USER_NAME"]
    user_email = os.environ["SEC_USER_EMAIL"]

    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    dl = Downloader(user_name, user_email, output_dir)
    forms: dict[str, int] = cfg["forms"]

    for ticker in tickers:
        for form, limit in forms.items():
            skip = existing_accessions(output_dir, ticker, form)
            print(f"Fetching up to {limit} new {form}(s) for {ticker} "
                  f"({len(skip)} already downloaded) ...")
            try:
                n = dl.get(
                    form,
                    ticker,
                    limit=limit,
                    download_details=True,
                    accession_numbers_to_skip=skip or None,
                )
                print(f"  OK  {n} new → {output_dir / 'sec-edgar-filings' / ticker / form}")
            except Exception as exc:
                print(f"  FAILED: {exc}")


if __name__ == "__main__":
    cfg = _load_config()
    args = sys.argv[1:]

    write_manifest_only = "--manifest" in args
    args = [a for a in args if a != "--manifest"]

    tickers = args if args else cfg["tickers"]
    tickers = [t.upper() for t in tickers]

    if write_manifest_only:
        user_name = os.environ["SEC_USER_NAME"]
        user_email = os.environ["SEC_USER_EMAIL"]
        dl = Downloader(user_name, user_email, cfg["output_dir"])
        rows = fetch_filing_rows(dl, tickers, cfg["forms"], dl.user_agent)
        write_manifest(rows)
    else:
        download_filings(tickers)
