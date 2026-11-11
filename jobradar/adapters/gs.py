"""Goldman Sachs careers (higher.gs.com) GraphQL API."""
from .. import http
from ..models import Posting

API = "https://api-higher.gs.com/gateway/api/v1/graphql"
Q = """query GetRoles($searchQueryInput: RoleSearchQueryInput!) { roleSearch(searchQueryInput: $searchQueryInput) {
 totalCount items { roleId corporateTitle jobTitle jobFunction locations { primary state country city } status division
 descriptionHtml externalSource { sourceId } } } }"""
Q_NODESC = Q.replace("descriptionHtml", "")


def _query(page, size, q):
    body = {"operationName": "GetRoles", "query": q, "variables": {"searchQueryInput": {
        "page": {"pageSize": size, "pageNumber": page}, "sort": {"sortStrategy": "RELEVANCE", "sortOrder": "DESC"},
        "filters": [], "experiences": ["EARLY_CAREER", "PROFESSIONAL"], "searchTerm": ""}}}
    r = http.post(API, json=body, headers={"Origin": "https://higher.gs.com", "Referer": "https://higher.gs.com/"})
    r.raise_for_status()
    d = r.json()
    if d.get("errors"):
        raise RuntimeError(str(d["errors"])[:200])
    return d["data"]["roleSearch"]


def fetch(src):
    q = Q
    try:
        _query(0, 1, q)
    except Exception:
        q = Q_NODESC
    out, page = {}, 0
    while True:
        rs = _query(page, 100, q)
        for j in rs["items"]:
            rid = j["roleId"]
            num = (j.get("externalSource") or {}).get("sourceId") or rid.split("_")[0]
            locs = [", ".join(x for x in [l.get("city"), l.get("country")] if x) for l in j.get("locations") or []]
            out[rid] = Posting(
                id=f"{src['key']}:{rid}", company=src["name"], title=j["jobTitle"], location=" | ".join(locs),
                url=f"https://higher.gs.com/roles/{num}",
                description_text=__import__("jobradar.models", fromlist=["x"]).html_to_text(j.get("descriptionHtml") or ""),
                source_adapter="gs", source_key=src["key"],
                extra={"corporateTitle": j.get("corporateTitle", ""), "division": j.get("division", ""),
                       "jobFunction": j.get("jobFunction", ""), "early_career": "EARLY" in rid or "CAMPUS" in rid})
        page += 1
        if not rs["items"] or page * 100 >= rs["totalCount"] or page > 30:
            break
    return list(out.values())
