import csv
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

CSV_FILE = "corpus/data_sources.csv"
OUTPUT_DIR = "corpus/raw_data"
TIMEOUT = 60
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

def sanitize(text):
    text = re.sub(r"[^\w\s-]", "", text)  # Remove special chars except whitespace and hyphens
    return re.sub(r"[\s_-]+", "_", text).strip("_").lower()  # Replace whitespace/hyphens with single underscore


def download_with_wget(url, filepath):
    wget = shutil.which("wget")
    if not wget:
        return False
    tmp = filepath + ".part"
    try:
        subprocess.run(
            # wget flags: --quiet, --timeout, --tries, --user-agent, --output-document
            [wget, "--quiet", f"--timeout={TIMEOUT}", "--tries=3",
             f"--user-agent={USER_AGENT}", f"--output-document={tmp}", url],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        os.replace(tmp, filepath)
        return True
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def download_with_curl(url, filepath):
    curl = shutil.which("curl")
    if not curl:
        return False
    tmp = filepath + ".part"
    try:
        subprocess.run(
            # curl flags: --fail, --location, --silent, --max-time, --retry, -A (user-agent), -o (output)
            [curl, "--fail", "--location", "--silent", f"--max-time={TIMEOUT}",
             "--retry=3", "-A", USER_AGENT, "-o", tmp, url],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        os.replace(tmp, filepath)
        return True
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def download_with_fallback(url, filepath):
    """Try requests → wget → curl. Raises if all fail."""
    try:
        response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        Path(filepath).write_bytes(response.content)
        return
    except Exception:
        pass
    if download_with_wget(url, filepath):
        return
    if download_with_curl(url, filepath):
        return
    raise RuntimeError(f"All download methods failed for {url}")


def polite_sleep():
    delay = random.uniform(1, 3)
    print(f"  Sleeping {delay:.1f}s...")
    time.sleep(delay)


def save_summary(results):
    print("\n--- Download Summary ---")
    for r in results:
        print(f"  {r['status']:8}  {r['category']} / {r['name']}")


def download_files():
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    results = []

    with open(CSV_FILE, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        name     = row.get("Name", "").strip()
        category = row.get("Category", "").strip()
        filetype = row.get("Filetype", "html").strip().lower()
        url      = row.get("Link", "").strip()

        if not url:
            continue

        filepath = os.path.join(OUTPUT_DIR, f"{sanitize(category)}_{sanitize(name)}.{filetype}")

        if os.path.exists(filepath):
            print(f"  Exists: {name}")
            results.append({"name": name, "category": category, "status": "Skipped"})
            continue

        print(f"  Downloading: {name}...")
        try:
            download_with_fallback(url, filepath)
            results.append({"name": name, "category": category, "status": "OK"})
            polite_sleep()
        except Exception as e:
            print(f"  Failed: {e}")
            results.append({"name": name, "category": category, "status": "Failed"})

    save_summary(results)


if __name__ == "__main__":
    download_files()
