"""Oracle Recruiting Cloud (HCM candidate experience) REST API.

params: host (e.g. jpmc.fa.oraclecloud.com), site (e.g. CX_1001), optional search_terms, lang (default en)
"""
from .. import http
from ..models import Posting, html_to_text, iso_date

EXPAND = "requisitionList.secondaryLocations,flexFieldsFacet.values"


EUROPE = ["United Kingdom", "Germany", "Switzerland", "Luxembourg", "Italy", "Ireland", "Austria", "Monaco",
          "Netherlands", "Spain", "France", "Belgium", "Portugal", "Sweden", "Denmark", "Norway", "Finland", "Poland",
          "Czech Republic", "Hungary", "Greece", "Malta", "Cyprus", "Jersey", "Guernsey", "Liechtenstein"]


def _europe_location_ids(host, site, names):
    r = http.get(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                 params={"onlyData": "true", "expand": EXPAND,
                         "finder": f"findReqs;siteNumber={site},facetsList=LOCATIONS,limit=1"})
    r.raise_for_status()
    facets = r.json()["items"][0].get("locationsFacet", [])
    return [(f["Id"], f["Name"]) for f in facets if f.get("Name") in names]


def fetch(src):
    p = src["params"]
    host, site = p["host"], p["site"]
    lang = p.get("lang", "en")
    seen = {}
    loc_ids = [None]
    if p.get("europe_only", True):
        loc_ids = [i for i, _ in _europe_location_ids(host, site, p.get("countries", EUROPE))]
        if not loc_ids:
            return []
    for loc_id in loc_ids:
        term = ""
        offset = 0
        while True:
            finder = f"findReqs;siteNumber={site},facetsList=LOCATIONS,limit=100,offset={offset},sortBy=POSTING_DATES_DESC"
            if loc_id:
                finder += f",selectedLocationsFacet={loc_id}"
            r = http.get(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                         params={"onlyData": "true", "expand": EXPAND, "finder": finder})
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                break
            reqs = items[0].get("requisitionList", [])
            total = items[0].get("TotalJobsCount", 0)
            for j in reqs:
                jid = str(j["Id"])
                locs = [j.get("PrimaryLocation", "")] + [s.get("Name", "") for s in j.get("secondaryLocations") or []]
                seen[jid] = Posting(
                    id=f"{src['key']}:{jid}", company=src["name"], title=j.get("Title", ""),
                    location=" | ".join(l for l in dict.fromkeys(locs) if l),
                    url=f"https://{host}/hcmUI/CandidateExperience/{lang}/sites/{site}/job/{jid}",
                    posted_at=iso_date(j.get("PostedDate")), description_text=html_to_text(j.get("ShortDescriptionStr") or ""),
                    source_adapter="oracle", source_key=src["key"])
            offset += len(reqs)
            if not reqs or offset >= total or offset >= p.get("max_results", 3000):
                break
    return list(seen.values())


def detail(src, post):
    p = src["params"]
    jid = post.id.split(":", 1)[1]
    r = http.get(f"https://{p['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails",
                 params={"expand": "all", "onlyData": "true", "finder": f"ById;Id=\"{jid}\",siteNumber={p['site']}"})
    r.raise_for_status()
    items = r.json().get("items", [])
    if items:
        d = items[0]
        post.description_text = html_to_text(" ".join(d.get(k) or "" for k in (
            "ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr", "CorporateDescriptionStr")))
        if d.get("ExternalPostedEndDate"):
            post.deadline = iso_date(d["ExternalPostedEndDate"])
