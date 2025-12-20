"""Extract Yoh jobs posted in the last 24 hours.

Data source:
https://shazamme.io/Job-Listing/src/php/actions?action=Get%20Jobs&dudaSiteID=4b57ce0f
This returns all jobs for jobs.yoh.com; we filter by `changedOnUTC` (ISO timestamp)
to keep only postings within the last day.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from typing import List

from openpyxl import Workbook

ENDPOINT = (
    "https://shazamme.io/Job-Listing/src/php/actions"
    "?dudaSiteID=4b57ce0f&action=Get%20Jobs"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (yoh-job-scraper)"}


def fetch_jobs() -> List[dict]:
    req = urllib.request.Request(ENDPOINT, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def parse_timestamp(job: dict) -> dt.datetime | None:
    """Prefer changedOnUTC (ISO) and fall back to postedDate (dd-mm-YYYY)."""
    ts = job["data"].get("changedOnUTC") or ""
    if ts:
        try:
            dt_obj = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt_obj if dt_obj.tzinfo else dt_obj.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass

    posted = job["data"].get("postedDate") or ""
    if posted:
        try:
            # postedDate appears as dd-mm-YYYY
            return dt.datetime.strptime(posted, "%d-%m-%Y").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None
    return None


def write_text(jobs: List[dict], path: str) -> None:
    lines = []
    for job in jobs:
        data = job["data"]
        posted_dt = parse_timestamp(job)
        posted_str = posted_dt.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ") if posted_dt else ""
        location = ", ".join(
            [part for part in (data.get("city"), data.get("state"), data.get("country")) if part]
        )
        lines.append(
            f"{data.get('jobName','')} | {location} | {data.get('workType','')} | "
            f"Posted: {posted_str} | {data.get('jobURL') or ''}"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) if lines else "No jobs found in the last 24 hours.")


def write_excel(jobs: List[dict], path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Yoh Jobs (24h)"
    ws.append(["Title", "Location", "Work Type", "Posted (UTC)", "URL", "Job ID", "Reference"])

    for job in jobs:
        data = job["data"]
        posted_dt = parse_timestamp(job)
        posted_str = posted_dt.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if posted_dt else ""
        location = ", ".join(
            [part for part in (data.get("city"), data.get("state"), data.get("country")) if part]
        )
        ws.append(
            [
                data.get("jobName"),
                location,
                data.get("workType"),
                posted_str,
                data.get("jobURL"),
                data.get("jobID"),
                data.get("referenceNumber"),
            ]
        )

    for col, width in {"A": 60, "B": 30, "C": 15, "D": 20, "E": 70}.items():
        ws.column_dimensions[col].width = width
    wb.save(path)


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=24)
    all_jobs = fetch_jobs()

    recent = []
    for job in all_jobs:
        ts = parse_timestamp(job)
        if ts and ts >= cutoff:
            recent.append(job)

    # Sort newest first
    recent.sort(key=lambda j: parse_timestamp(j) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)

    write_text(recent, "yoh_jobs_last_24h.txt")
    write_excel(recent, "yoh_jobs_last_24h.xlsx")
    print(f"Wrote {len(recent)} Yoh jobs to yoh_jobs_last_24h.txt and yoh_jobs_last_24h.xlsx")


if __name__ == "__main__":
    main()
