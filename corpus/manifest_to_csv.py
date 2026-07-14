"""
Convert corpus/manifest.yml (program-owned download record) into a CSV for
human parsing, e.g. to open in a spreadsheet.

Usage:
    python corpus/manifest_to_csv.py                     # writes corpus/manifest.csv
    python corpus/manifest_to_csv.py out/other.csv       # custom output path
"""

import csv
import sys

from manifest_utils import MANIFEST_FILE, load_manifest

CSV_FIELDS = ["source", "name", "category", "filetype", "link", "method", "pulled", "path"]
DEFAULT_OUTPUT = "corpus/manifest.csv"


def manifest_to_csv(output_path: str = DEFAULT_OUTPUT) -> None:
    documents = load_manifest()
    if not documents:
        print(f"No entries found in {MANIFEST_FILE}; nothing to write.")
        return

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for entry in documents:
            writer.writerow(entry)
    print(f"Wrote {len(documents)} rows to {output_path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        manifest_to_csv(args[0])
    else:
        manifest_to_csv()
