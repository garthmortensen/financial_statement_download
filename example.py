"""
Examples of what sec_edgar_downloader.Downloader can do beyond basic 10-K downloads.
"""

from datetime import date
from sec_edgar_downloader import Downloader

dl = Downloader("Your Name", "your@email.com", "corpus/raw_data/sec")

# ── Form types ────────────────────────────────────────────────────────────────

# Annual report (domestic)
dl.get("10-K", "JPM")    # JPMorgan Chase

# Annual report (foreign private issuer — files 20-F instead of 10-K)
dl.get("20-F", "DB")     # Deutsche Bank

# Quarterly report
dl.get("10-Q", "BAC")   # Bank of America

# Current report (material events: earnings, M&A, leadership changes, …)
dl.get("8-K", "WFC")    # Wells Fargo

# Proxy statement (executive pay, board elections)
dl.get("DEF 14A", "C")  # Citigroup

# Insider ownership at IPO
dl.get("S-1", "CFG")    # Citizens Financial Group (IPO 2014)

# Institutional holdings (13F filers — asset managers)
dl.get("13F-HR", "0000019617")   # JPMorgan Chase by CIK

# Beneficial ownership report (activist investors, ≥5 % stake)
dl.get("SC 13G", "GS")  # Goldman Sachs
dl.get("SC 13D", "GS")

# Insider transactions (officers / directors)
dl.get("4", "MS")       # Morgan Stanley

# Special disclosure (conflict minerals, etc.)
dl.get("SD", "JPM")


# ── Filtering options ─────────────────────────────────────────────────────────

# Date range  (after / before accept "YYYY-MM-DD" strings, date, or datetime)
dl.get("10-K", "WFC", after="2015-01-01", before="2020-12-31")   # Wells Fargo
dl.get("10-K", "WFC", after=date(2015, 1, 1), before=date(2020, 12, 31))

# Limit to N most-recent filings
dl.get("10-K", "JPM", limit=5)

# Include amendments (10-K/A, 8-K/A, …)
dl.get("8-K", "BAC", include_amends=True)   # Bank of America

# Download human-readable detail document (HTML/XML) in addition to raw filing
dl.get("10-K", "GS", download_details=True)  # Goldman Sachs

# Skip specific accession numbers you've already processed
dl.get("10-K", "JPM", accession_numbers_to_skip={"0000019617-23-000234"})


# ── Using CIK instead of ticker ───────────────────────────────────────────────

# CIKs are stable; useful when a company was renamed or delisted
dl.get("10-K", "0000019617")   # JPMorgan Chase CIK
dl.get("10-K", "0000070858")   # Bank of America CIK
dl.get("10-K", "0000831001")   # Citigroup CIK


# ── Inspect supported form types ──────────────────────────────────────────────

print(Downloader.supported_forms)          # full list (~150 form types)
print(len(Downloader.supported_forms))     # → 150+
