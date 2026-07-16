# 10k

Quarterly corpus builder for bank filings (10-K, 10-Q) and other bank documents,
downloaded from SEC EDGAR and investor-relations pages.

## Layout

| File | Role |
|---|---|
| [config.yml](config.yml) | Settings: forms/limits, output dirs, input file paths |
| [corpus/banks.yml](corpus/banks.yml) | **Input** — banks to pull (ticker, or CIK if no ticker) |
| [corpus/sources.yml](corpus/sources.yml) | **Input** — non-SEC documents (IR PDFs etc.) |
| [corpus/downloader_sec.py](corpus/downloader_sec.py) | Downloads SEC filings via EDGAR |
| [corpus/downloader_non_sec.py](corpus/downloader_non_sec.py) | Downloads the sources.yml documents |
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
`corpus/raw_data/<category>/`. Only each filing's primary document is kept
(full-submission.txt is deleted). Transient HTTP errors are
retried with exponential backoff (tenacity). Each run writes a JSONL log to
`logs/<script>_<timestamp>.jsonl`.

Limit a run to specific banks: `python corpus/downloader_sec.py JPM BAC`

## Output structure

```
corpus/raw_data/sec/<year>Q<n>/sec-edgar-filings/<TICKER>/<FORM>/<accession>/primary-document.html
```

The accession number (e.g. `0000040729-26-000005`) is EDGAR's permanent filing
identifier: `<filer-CIK>-<year>-<sequence>`. It uniquely identifies one
submission and is stable — the same accession number always refers to the same
filing.
