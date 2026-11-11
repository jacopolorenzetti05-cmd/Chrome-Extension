"""HiBob careers sites ({company}.careers.hibob.com). The job-ad API needs the site's session cookie,
so it is called from inside a headless browser page."""
from ..http import Browser
from ..models import Posting, html_to_text, iso_date


def fetch(src):
    base = src["params"]["base_url"].rstrip("/")
    d = Browser.get().fetch_json_via_page(base + "/", base + "/api/job-ad")
    out = []
    for j in d.get("jobAdDetails", []):
        jid = j.get("id")
        loc = ", ".join(x for x in [j.get("site"), j.get("country")] if x) or j.get("siteName", "")
        out.append(Posting(
            id=f"{src['key']}:{jid}", company=src["name"], title=j.get("title", ""), location=loc,
            url=f"{base}/jobs/{jid}", posted_at=iso_date(j.get("publishedAt") or j.get("creationDate")),
            description_text=html_to_text(" ".join(str(j.get(k) or "") for k in ("description", "requirements", "responsibilities", "benefits"))),
            source_adapter="hibob", source_key=src["key"],
            extra={"employmentType": j.get("employmentType", ""), "department": j.get("department", "")}))
    return out
