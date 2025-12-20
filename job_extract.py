"""Scrape Insight Global jobs posted in the last 24 hours.

The careers site renders each result with a hidden JSON block that contains the
posted date and other metadata. This script walks the paginated results ordered
by most recent, collects any jobs posted within the last 24 hours, and writes
them to ``jobs_last_24h.txt``.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Iterable, List, Tuple

from openpyxl import Workbook
from openpyxl.utils import get_column_letter


# A broad search term is required; a single letter returns all the newest jobs.
SEARCH_TERM = "a"
BASE_URL = (
    "https://jobs.insightglobal.com/find_a_job/{page}/"
    "?orderby=recent&filterby=all&miles=False&remote=False&srch=" + SEARCH_TERM
)
HEADERS = {"User-Agent": "Mozilla/5.0 (job-scraper)"}
MAX_PAGES = 50  # fail-safe upper bound

# Regex to capture the job link, title, and inline JSON payload for each row.
JOB_BLOCK_RE = re.compile(
    r"<div class=\"job-title\"><a href='(?P<href>[^']+)'[^>]*>"
    r"(?P<title>[^<]+)</a>.*?"
    r"<div style=\"display:none;\">(?P<data>{.*?})</div>",
    re.S,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_jobs(html_text: str) -> Iterable[Tuple[str, str, dict]]:
    """Yield (title, href, metadata) tuples from the HTML page."""
    for match in JOB_BLOCK_RE.finditer(html_text):
        raw_json = html.unescape(match.group("data"))
        try:
            meta = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        yield match.group("title"), match.group("href"), meta


def parse_posted_date(raw: str) -> dt.datetime | None:
    m = re.search(r"/Date\((\d+)\)/", raw)
    if not m:
        return None
    ts_ms = int(m.group(1))
    return dt.datetime.fromtimestamp(ts_ms / 1000, tz=dt.timezone.utc)


def scrape_recent_jobs(cutoff: dt.datetime) -> List[dict]:
    recent: List[dict] = []
    for page in range(1, MAX_PAGES + 1):
        page_path = "" if page == 1 else f"{page}/"
        url = BASE_URL.format(page=page_path)
        try:
            html_text = fetch(url)
        except urllib.error.URLError as exc:  # network issue; stop gracefully
            print(f"Failed to fetch page {page}: {exc}", file=sys.stderr)
            break

        jobs_on_page = list(parse_jobs(html_text))
        if not jobs_on_page:
            break

        page_has_newer = False
        for title, href, meta in jobs_on_page:
            posted_dt = parse_posted_date(meta.get("PostedDate", ""))
            if posted_dt is None:
                continue
            if posted_dt < cutoff:
                continue

            page_has_newer = True
            recent.append(
                {
                    "title": title.strip(),
                    "href": "https://jobs.insightglobal.com" + href,
                    "city": meta.get("City", ""),
                    "state": meta.get("State", ""),
                    "job_type": ", ".join(meta.get("JobType", [])),
                    "posted": posted_dt,
                    "job_id": meta.get("JobID"),
                    "salary_low": meta.get("SalaryLow"),
                    "salary_high": meta.get("SalaryHigh"),
                }
            )

        # Pages are ordered by most recent; once an entire page is older we can stop.
        if not page_has_newer:
            break

    # Sort newest first for consistency.
    recent.sort(key=lambda j: j["posted"], reverse=True)
    return recent


def write_output(jobs: List[dict], path: str) -> None:
    lines = []
    for job in jobs:
        posted_str = job["posted"].astimezone(dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%SZ"
        )
        location = ", ".join(filter(None, [job["city"], job["state"]]))
        line = (
            f"{job['title']} | {location} | {job['job_type']} | "
            f"Posted: {posted_str} | {job['href']}"
        )
        lines.append(line)

    output = "\n".join(lines) if lines else "No jobs found in the last 24 hours."
    with open(path, "w", encoding="utf-8") as f:
        f.write(output)


def write_excel(jobs: List[dict], path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs (last 24h)"

    headers = [
        "Title",
        "Location",
        "Job Type",
        "Posted (UTC)",
        "URL",
        "Job ID",
        "Salary Low",
        "Salary High",
    ]
    ws.append(headers)

    for job in jobs:
        location = ", ".join(filter(None, [job["city"], job["state"]]))
        posted_str = job["posted"].astimezone(dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        ws.append(
            [
                job["title"],
                location,
                job["job_type"],
                posted_str,
                job["href"],
                job["job_id"],
                job["salary_low"],
                job["salary_high"],
            ]
        )

    # Basic column sizing for readability.
    widths = {
        "A": 60,
        "B": 25,
        "C": 18,
        "D": 20,
        "E": 60,
        "F": 10,
        "G": 12,
        "H": 12,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    wb.save(path)


def main() -> None:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    jobs = scrape_recent_jobs(cutoff)
    write_output(jobs, "jobs_last_24h.txt")
    write_excel(jobs, "jobs_last_24h.xlsx")
    print(
        f"Wrote {len(jobs)} jobs to jobs_last_24h.txt and jobs_last_24h.xlsx"
    )


if __name__ == "__main__":
    main()
