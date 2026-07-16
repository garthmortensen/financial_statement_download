"""
Download the non-SEC documents listed in corpus/sources.yml (user-edited input).

Files land in <output_dir>/<category>/<name>.<filetype>. Transient failures are
retried with exponential backoff via tenacity.

Usage:
    python corpus/downloader_non_sec.py
"""

import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from log_utils import setup_logging

TIMEOUT = 60
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

log = None  # bound in __main__ via setup_logging


class TransientHTTPError(Exception):
    """HTTP 429 / 5xx — worth retrying with backoff."""


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(sources_file: str) -> list[dict]:
    with open(sources_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or not data.get("sources"):
        return []
    return data["sources"]


def sanitize(text):
    text = re.sub(r"[^\w\s-]", "", text)  # Remove special chars except whitespace and hyphens
    # Replace whitespace/hyphens with single underscore
    return re.sub(r"[\s_-]+", "_", text).strip("_").lower()


@retry(
    retry=retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout, TransientHTTPError)
    ),
    wait=wait_exponential_jitter(initial=1, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def fetch(url: str) -> bytes:
    response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    if response.status_code == 429 or response.status_code >= 500:
        raise TransientHTTPError(f"HTTP {response.status_code} for {url}")
    response.raise_for_status()
    return response.content


def polite_sleep_between_successes():
    delay = random.uniform(1, 3)
    log.info("sleeping", seconds=round(delay, 1))
    time.sleep(delay)


def save_summary(results):
    counts = {"OK": 0, "Skipped": 0, "Failed": 0}
    for result in results:
        counts[result["status"]] += 1
    log.info("run_finished", ok=counts["OK"], skipped=counts["Skipped"],
             failed=counts["Failed"])


def download_files() -> int:
    """Download sources listed in sources.yml. Returns failure count."""
    cfg = load_config()
    downloader_cfg = cfg["non_sec_download_settings"]
    output_dir = Path(downloader_cfg["output_dir"])

    sources = load_sources(downloader_cfg["sources_file"])

    results = []
    for source in sources:
        name = str(source.get("name", "")).strip()
        category = str(source.get("category", "")).strip()
        url = str(source.get("link", "")).strip()
        filetype = str(source.get("filetype", "")).strip().lower()

        if not url:
            continue
        if not filetype:
            url_path = urlparse(url).path
            filetype = Path(url_path).suffix.lstrip(".").lower() or "html"

        result_info = {"name": name, "category": category}

        # Route each file into a per-category subdir, e.g. raw_data/ir/
        category_dir = output_dir / sanitize(category)
        category_dir.mkdir(parents=True, exist_ok=True)
        filepath = category_dir / f"{sanitize(name)}.{filetype}"

        if filepath.exists():
            log.info("skipped_exists_on_disk", name=name, path=str(filepath))
            results.append({**result_info, "status": "Skipped"})
            continue

        log.info("downloading", name=name, url=url)
        try:
            content = fetch(url)
        except Exception as exc:
            log.error("download_failed", name=name, url=url, error=str(exc))
            results.append({**result_info, "status": "Failed"})
            continue

        filepath.write_bytes(content)
        log.info("downloaded", name=name, path=str(filepath), bytes=len(content))
        results.append({**result_info, "status": "OK"})
        polite_sleep_between_successes()

    save_summary(results)

    failure_count = 0
    for result in results:
        if result["status"] == "Failed":
            failure_count += 1
    return failure_count


if __name__ == "__main__":
    config = load_config()
    log = setup_logging(config["log_dir"], "downloader_non_sec")
    if download_files():
        sys.exit(1)
