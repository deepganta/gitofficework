"""Extract Hays jobs posted in the last 24 hours.

This uses the UKG/Ultipro job board endpoint behind the public listings page:
https://recruiting.ultipro.com/HAY1004HAUS/JobBoard/bebb31cb-327e-46b6-80a7-e0033ffa4653
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from typing import Dict, List, Optional

from openpyxl import Workbook

BASE_URL = "https://recruiting.ultipro.com/HAY1004HAUS/JobBoard/bebb31cb-327e-46b6-80a7-e0033ffa4653"
LOAD_URL = f"{BASE_URL}/JobBoardView/LoadSearchResults"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (hays-job-scraper)",
    "X-Requested-With": "XMLHttpRequest",
}

ORDER_BY = [{"Value": "postedDateDesc", "PropertyName": "PostedDate", "Ascending": False}]
MATCH_CRITERIA = {
    "PreferredJobs": [],
    "Educations": [],
    "LicenseAndCertifications": [],
    "Skills": [],
    "hasNoLicenses": False,
    "SkippedSkills": [],
}


def fetch_page(
    opener: urllib.request.OpenerDirector, skip: int, top: int
) -> Dict:
    payload = {
        "opportunitySearch": {
            "Top": top,
            "Skip": skip,
            "QueryString": "",
            "Filters": [],
            "OrderBy": ORDER_BY,
            "ProximitySearchType": 0,
        },
        "matchCriteria": MATCH_CRITERIA,
    }
    headers = dict(HEADERS)
    req = urllib.request.Request(
        LOAD_URL, data=json.dumps(payload).encode("utf-8"), headers=headers
    )
    with opener.open(req) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def parse_posted_date(raw: str | None) -> Optional[dt.datetime]:
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def format_locations(locations: List[dict]) -> str:
    parts: List[str] = []
    for loc in locations or []:
        address = loc.get("Address") or {}
        city = address.get("City") or ""
        state = (address.get("State") or {}).get("Code") or (address.get("State") or {}).get("Name") or ""
        label = ", ".join(filter(None, [city, state]))
        desc = loc.get("LocalizedDescription") or ""
        if desc and desc not in label:
            label = f"{label} ({desc})" if label else desc
        if label:
            parts.append(label)

    unique = []
    for item in parts:
        if item not in unique:
            unique.append(item)
    return "; ".join(unique)


def collect_recent_jobs(cutoff: dt.datetime) -> List[dict]:
    opener = urllib.request.build_opener()

    skip = 0
    top = 50
    total = None
    recent: List[dict] = []

    while True:
        data = fetch_page(opener, skip, top)
        opportunities = data.get("opportunities", [])
        if not opportunities:
            break

        if total is None:
            total = data.get("totalCount", 0)

        for job in opportunities:
            posted_dt = parse_posted_date(job.get("PostedDate"))
            if posted_dt is None or posted_dt < cutoff:
                continue

            recent.append(
                {
                    "id": job.get("Id"),
                    "title": (job.get("Title") or "").strip(),
                    "category": (job.get("JobCategoryName") or "").strip(),
                    "full_time": job.get("FullTime"),
                    "location": format_locations(job.get("Locations") or []),
                    "posted": posted_dt,
                    "requisition": job.get("RequisitionNumber"),
                    "url": f"{BASE_URL}/OpportunityDetail?opportunityId={job.get('Id')}",
                }
            )

        oldest = None
        for job in reversed(opportunities):
            oldest = parse_posted_date(job.get("PostedDate"))
            if oldest:
                break

        skip += top
        if (oldest and oldest < cutoff) or (total is not None and skip >= total):
            break

    recent.sort(key=lambda j: j["posted"], reverse=True)
    return recent


def write_text(jobs: List[dict], path: str) -> None:
    lines = []
    for job in jobs:
        posted_str = job["posted"].astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        full_time = "Full Time" if job["full_time"] else "Part Time/Other"
        summary = " | ".join(filter(None, [job["location"], job["category"], full_time]))
        lines.append(f"{job['title']} | {summary} | Posted: {posted_str} | {job['url']}")
    output = "\n".join(lines) if lines else "No jobs found in the last 24 hours."
    with open(path, "w", encoding="utf-8") as f:
        f.write(output)


def write_excel(jobs: List[dict], path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Hays Jobs (24h)"
    ws.append(
        [
            "Title",
            "Location",
            "Category",
            "Full Time",
            "Posted (UTC)",
            "URL",
            "Job ID",
            "Requisition",
        ]
    )

    for job in jobs:
        ws.append(
            [
                job["title"],
                job["location"],
                job["category"],
                "Yes" if job["full_time"] else "No",
                job["posted"].astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                job["url"],
                job["id"],
                job["requisition"],
            ]
        )

    for col, width in {"A": 60, "B": 35, "C": 20, "D": 10, "E": 20, "F": 70, "G": 36}.items():
        ws.column_dimensions[col].width = width

    wb.save(path)


def main() -> None:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)
    jobs = collect_recent_jobs(cutoff)
    write_text(jobs, "hays_jobs_last_24h.txt")
    write_excel(jobs, "hays_jobs_last_24h.xlsx")
    print(f"Wrote {len(jobs)} Hays jobs to hays_jobs_last_24h.txt and hays_jobs_last_24h.xlsx")


if __name__ == "__main__":
    main()
