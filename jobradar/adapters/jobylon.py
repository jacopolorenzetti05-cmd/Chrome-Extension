"""Jobylon (emp.jobylon.com) – job links are read from the employer's official careers page
(rendered, because e.g. uefa.com blocks plain HTTP clients); each posting is then read from
emp.jobylon.com (JSON-LD JobPosting).

params: list_urls, company_filter (regex on the jobylon URL slug, optional)
"""
from . import html as html_adapter


def fetch(src):
    p = dict(src["params"])
    pat = r"https://emp\.jobylon\.com/jobs/\d+"
    if p.get("company_filter"):
        pat += r"-" + p["company_filter"]
    p.setdefault("link_pattern", pat)
    p.setdefault("render", True)
    p.setdefault("id_pattern", r"/jobs/(\d+)")
    p.setdefault("wait_ms", 5000)
    s = dict(src, params=p)
    posts = html_adapter.fetch(s)
    src["_snapshot"] = s.get("_snapshot")
    for x in posts:
        x.source_adapter = "jobylon"
    return posts
