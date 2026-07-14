# 10k

Quarterly corpus builder for bank filings (10-K, 10-Q) and other bank documents,
downloaded from SEC EDGAR and investor-relations pages.

## Layout

| File | Role |
|---|---|
| [config.yml](config.yml) | Settings: forms/limits, output dirs, input file paths |
| [corpus/banks.yml](corpus/banks.yml) | **Input** — banks to pull (ticker, or CIK if no ticker) |
| [corpus/sources.yml](corpus/sources.yml) | **Input** — non-SEC documents (IR PDFs etc.) |
| [corpus/manifest.yml](corpus/manifest.yml) | **Output** — program-owned record of every download; do not hand-edit |
| [corpus/downloader_sec.py](corpus/downloader_sec.py) | Downloads SEC filings via EDGAR |
| [corpus/downloader_non_sec.py](corpus/downloader_non_sec.py) | Downloads the sources.yml documents |
| [corpus/manifest_utils.py](corpus/manifest_utils.py) | Shared manifest/run-id helpers |
| [corpus/manifest_to_csv.py](corpus/manifest_to_csv.py) | Exports manifest.yml as CSV for human parsing |
| [example.py](example.py) | sec-edgar-downloader usage examples |

## Setup

Set your SEC EDGAR identity (required by the API) in `.env`:

```
SEC_USER_NAME=Your Name
SEC_USER_EMAIL=you@example.com
```

## Quarterly run

```bash
python corpus/downloader_sec.py       # new SEC filings for all banks
python corpus/downloader_non_sec.py   # new non-SEC sources
```

Each quarter's SEC pull lands in its own directory
(`corpus/raw_data/sec/<year>Q<n>/`); non-SEC files land in
`corpus/raw_data/<category>/`. Anything already recorded in manifest.yml is
skipped, so reruns are incremental and resumable. Only each filing's primary
document is kept (full-submission.txt is deleted). Transient HTTP errors are
retried with exponential backoff (tenacity).

Limit a run to specific banks: `python corpus/downloader_sec.py JPM BAC`
