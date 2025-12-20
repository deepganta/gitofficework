"""Extract Judge.com jobs posted in the last 24 hours.

The public AJAX endpoint powers the jobs page:
https://www.judge.com/wp-admin/admin-ajax.php?action=jdg_get_jobs

We post a JSON payload (same as the site script) and paginate through results
until we pass the 24h cutoff. Output is written to both TXT and XLSX files.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import urllib.request
from typing import Dict, List

from openpyxl import Workbook

ENDPOINT = "https://www.judge.com/wp-admin/admin-ajax.php?action=jdg_get_jobs"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (judge-job-scraper)",
}

BASE_PAYLOAD: Dict = {
    "categories": [],
    "countries": "USA",
    "geo": [{"distance": 50, "latLong": [0], "location": ""}],
    "query": "",
    "states": "",
    "type": ["Any"],
    "page": 0,
    "remote": False,
}


def fetch_page(page: int) -> Dict:
    payload = {"payload": {**BASE_PAYLOAD, "page": page}}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        outer = json.loads(resp.read().decode())
    return json.loads(outer)


def parse_opened(ts_ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts_ms / 1000, tz=dt.timezone.utc)


def collect_recent_jobs(cutoff: dt.datetime) -> List[dict]:
    page = 0
    recent: List[dict] = []

    while True:
        data = fetch_page(page)
        hits = data.get("hits", [])
        if not hits:
            break

        for job in hits:
            opened_dt = parse_opened(job["opened"])
            if opened_dt >= cutoff:
                recent.append(
                    {
                        "id": job.get("jobOrderId"),
                        "title": job.get("title", "").strip(),
                        "location": (job.get("location") or "").strip(),
                        "type": (job.get("type") or "").strip(),
                        "category": (job.get("category", {}).get("description") or "").strip(),
                        "salary": (job.get("salary") or "").strip(),
                        "opened": opened_dt,
                        "url": f"https://www.judge.com/jobs/details/{job.get('jobOrderId')}/",
                    }
                )

        # Pagination guard: stop once oldest on this page is older than cutoff.
        oldest = parse_opened(hits[-1]["opened"])
        total = data.get("total", 0)
        size = data.get("size", 20)
        max_pages = math.ceil(total / size) if size else 0
        page += 1
        if oldest < cutoff or (max_pages and page >= max_pages):
            break

    recent.sort(key=lambda j: j["opened"], reverse=True)
    return recent


def write_text(jobs: List[dict], path: str) -> None:
    lines = []
    for job in jobs:
        posted_str = job["opened"].strftime("%Y-%m-%d %H:%M:%SZ")
        parts = [job["location"], job["type"], job["category"]]
        summary = " | ".join(filter(None, parts))
        lines.append(f"{job['title']} | {summary} | Posted: {posted_str} | {job['url']}")
    output = "\n".join(lines) if lines else "No jobs found in the last 24 hours."
    with open(path, "w", encoding="utf-8") as f:
        f.write(output)


def write_excel(jobs: List[dict], path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Judge Jobs (24h)"
    ws.append(["Title", "Location", "Type", "Category", "Salary", "Posted (UTC)", "URL", "Job ID"])

    for job in jobs:
        ws.append(
            [
                job["title"],
                job["location"],
                job["type"],
                job["category"],
                job["salary"],
                job["opened"].strftime("%Y-%m-%d %H:%M:%S"),
                job["url"],
                job["id"],
            ]
        )

    for col, width in {"A": 60, "B": 30, "C": 15, "D": 25, "E": 15, "F": 20, "G": 70}.items():
        ws.column_dimensions[col].width = width

    wb.save(path)


def main() -> None:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    jobs = collect_recent_jobs(cutoff)
    write_text(jobs, "judge_jobs_last_24h.txt")
    write_excel(jobs, "judge_jobs_last_24h.xlsx")
    print(f"Wrote {len(jobs)} Judge jobs to judge_jobs_last_24h.txt and judge_jobs_last_24h.xlsx")


if __name__ == "__main__":
    main()
