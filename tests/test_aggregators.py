"""Acceptance check 3: no URL in the dashboard points to an aggregator domain."""
import json
from pathlib import Path

import pytest

from jobradar.config import AGGREGATOR_DOMAINS, is_aggregator

BLOCKLIST = ["indeed.com", "de.indeed.com", "glassdoor.com", "iagora.com", "jobsinfootball.com", "globalsportsjobs.com",
             "talendo.ch", "jobleads.com", "linkedin.com/jobs", "stepstone.de", "efinancialcareers.com",
             "workinsports.com", "teamworkonline.com/jobs", "ziprecruiter.ie", "builtin.com"]


def test_blocklist_detected():
    for d in BLOCKLIST:
        assert is_aggregator(f"https://{d}/job/123"), d
    assert not is_aggregator("https://jobs.smartrecruiters.com/RedBull/123")
    assert not is_aggregator("https://boards.greenhouse.io/onrunning/jobs/1")
    assert not is_aggregator("https://www.ccep.jobs/en/job/rotterdam/internship-fernandes-and-monster-energy/1299/1")


SITE = Path(__file__).resolve().parent.parent / "site" / "data.json"


@pytest.mark.skipif(not SITE.exists(), reason="dashboard not built yet (run `python -m jobradar run`)")
def test_dashboard_has_no_aggregator_urls():
    data = json.loads(SITE.read_text())
    bad = [p["url"] for p in data["postings"] if is_aggregator(p["url"]) or is_aggregator(p.get("apply_url") or "")]
    assert not bad, bad
    for p in data["postings"]:
        host = p["url"].split("/")[2].lower()
        assert not any(host.startswith(b.split("/")[0]) or host.endswith("." + b.split("/")[0]) for b in BLOCKLIST), p["url"]
