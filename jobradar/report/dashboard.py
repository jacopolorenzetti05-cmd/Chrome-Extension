"""Static, mobile-friendly dashboard (published to GitHub Pages)."""
from __future__ import annotations

import datetime as dt
import html
import json

from .. import config
from ..store import Store
from . import data

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Radar</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mute:#5d6470;--line:#e3e6ea;--acc:#0b5fff;--ok:#127a3a;--warn:#a15c00;--bad:#b42318;--chip:#eef1f5}
@media (prefers-color-scheme: dark){:root{--bg:#0f1115;--card:#171a20;--ink:#e8eaee;--mute:#9aa2ae;--line:#2a2f37;--acc:#6ea0ff;--ok:#4cc27a;--warn:#e0a34a;--bad:#ff7a6e;--chip:#222730}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{padding:16px;max-width:1400px;margin:auto}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mute);font-size:13px}
nav{display:flex;gap:6px;padding:0 16px;max-width:1400px;margin:auto;flex-wrap:wrap}
nav button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:8px 14px;border-radius:999px;font-weight:600;cursor:pointer}
nav button.on{background:var(--acc);border-color:var(--acc);color:#fff}
.bar{display:flex;gap:8px;flex-wrap:wrap;padding:12px 16px;max-width:1400px;margin:auto}
.bar select,.bar input{padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font-size:14px}
main{padding:0 16px 40px;max-width:1400px;margin:auto}
.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;min-width:1100px}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--card);font-size:12px;color:var(--mute);cursor:pointer;white-space:nowrap}
td.sc{font-weight:700;font-size:16px;text-align:center}.s9{color:var(--ok)}.s7{color:var(--acc)}.s5{color:var(--warn)}.s1{color:var(--mute)}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;background:var(--chip);font-size:12px;white-space:nowrap}
.New{background:#dff5e6;color:#0b5b2a}.Closing{background:#fde7d7;color:#8a3b00}.Removed{background:#eee;color:#666}
.maybe{opacity:.8}.small{font-size:12px;color:var(--mute)}a{color:var(--acc)}
.cards{display:none}
@media (max-width:760px){.tblwrap{display:none}.cards{display:block}
 .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:10px}
 .card .top{display:flex;justify-content:space-between;gap:8px}.card .sc{font-size:20px;font-weight:700}}
.health td.st{font-weight:700}.okc{color:var(--ok)}.badc{color:var(--bad)}.warnc{color:var(--warn)}
.empty{padding:24px;text-align:center;color:var(--mute)}
</style></head><body>
<header><h1>Job Radar</h1><div class="sub">Official postings only · read directly from employers' hiring systems · updated __UPDATED__ · __COUNTS__</div></header>
<nav><button data-tab="sports" class="on">Sports</button><button data-tab="wealth">Wealth Management</button><button data-tab="health">Source health</button></nav>
<div class="bar" id="filters">
 <select id="fCountry"><option value="">All countries</option></select>
 <select id="fStatus"><option value="">All statuses (no removed)</option><option>New</option><option>Active</option><option>Closing soon</option><option value="Removed">Removed (history)</option></select>
 <select id="fRel"><option value="">Strong + maybe</option><option value="keep">Strong matches only</option><option value="maybe">Maybe bucket</option></select>
 <select id="fMine"><option value="">Any application status</option></select>
 <input id="fText" placeholder="Search company / role" size="22">
</div>
<main><div id="view"></div></main>
<script>
const DATA = __DATA__;
const COLS=[["score","Score"],["company","Company"],["title","Role"],["segment","Segment"],["location","Location"],["pay","Pay"],["languages","Languages"],["type","Type/Timing"],["deadline","Deadline"],["display_status","Status"],["my_status","My status"],["why","Why it fits"],["url","Official link"],["first_seen","First seen"],["last_seen","Last seen"]];
let tab="sports",sortKey="score",sortDir=-1;
const $=s=>document.querySelector(s), esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const countries=[...new Set(DATA.postings.map(p=>p.country).filter(Boolean))].sort();
countries.forEach(c=>$("#fCountry").insertAdjacentHTML("beforeend",`<option>${c}</option>`));
DATA.statuses.forEach(s=>$("#fMine").insertAdjacentHTML("beforeend",`<option>${s}</option>`));
try{const s=JSON.parse(localStorage.getItem("jr-f")||"{}");for(const k in s){if($("#"+k))$("#"+k).value=s[k]}; if(s.tab)tab=s.tab}catch(e){}
function save(){try{const o={tab};["fCountry","fStatus","fRel","fMine","fText"].forEach(k=>o[k]=$("#"+k).value);localStorage.setItem("jr-f",JSON.stringify(o))}catch(e){}}
function scClass(s){return s>=9?"s9":s>=7?"s7":s>=5?"s5":"s1"}
function rows(){const c=$("#fCountry").value,st=$("#fStatus").value,rel=$("#fRel").value,mine=$("#fMine").value,q=$("#fText").value.toLowerCase();
 return DATA.postings.filter(p=>p.sector===tab && (st? p.display_status===st : p.display_status!=="Removed") && (!c||p.country===c) && (!rel||p.relevance===rel) && (!mine||p.my_status===mine) && (!q||(p.company+" "+p.title+" "+p.location).toLowerCase().includes(q)))
 .sort((a,b)=>{let x=a[sortKey]??"",y=b[sortKey]??"";if(typeof x==="number"||typeof y==="number"){x=+x||0;y=+y||0}return (x>y?1:x<y?-1:0)*sortDir||((b.score||0)-(a.score||0))})}
function cell(p,k){switch(k){
 case "score":return `<td class="sc ${scClass(p.score)}">${p.score??""}</td>`;
 case "title":return `<td><b>${esc(p.title)}</b>${p.relevance==="maybe"?' <span class="chip">maybe</span>':""}${p.level==="working_student"?' <span class="chip">Werkstudent</span>':""}<div class="small">${esc(p.reason)}</div></td>`;
 case "type":return `<td>${esc(p.type)}<div class="small">${esc(p.timing)}</div></td>`;
 case "display_status":return `<td><span class="chip ${p.display_status.split(" ")[0]}">${esc(p.display_status)}</span></td>`;
 case "url":return `<td><a href="${esc(p.url)}" target="_blank" rel="noopener">Open posting ↗</a><div class="small">${esc(p.verify_note||"")}</div></td>`;
 case "my_status":return `<td>${esc(p.my_status)}${p.my_note?`<div class="small">${esc(p.my_note)}</div>`:""}<div class="small" title="id for my_status.yaml">${esc(p.id)}</div></td>`;
 default:return `<td>${esc(p[k])}</td>`}}
function renderJobs(){const r=rows();
 if(!r.length){$("#view").innerHTML=`<div class="empty">No postings match these filters.</div>`;return}
 const th=COLS.map(([k,l])=>`<th data-k="${k}">${l}${k===sortKey?(sortDir<0?" ▼":" ▲"):""}</th>`).join("");
 const tb=r.map(p=>`<tr class="${p.relevance}">${COLS.map(([k])=>cell(p,k)).join("")}</tr>`).join("");
 const cards=r.map(p=>`<div class="card ${p.relevance}"><div class="top"><div><b>${esc(p.title)}</b><div>${esc(p.company)} · ${esc(p.location)}</div></div><div class="sc ${scClass(p.score)}">${p.score}</div></div>
  <div class="small">${esc(p.type)} ${esc(p.timing)} · ${esc(p.pay)} · ${esc(p.languages)}</div>
  <div class="small">${esc(p.why)}</div><div style="margin-top:6px"><span class="chip ${p.display_status.split(" ")[0]}">${esc(p.display_status)}</span> ${p.deadline?`<span class="chip">Deadline ${esc(p.deadline)}</span>`:""} <span class="chip">${esc(p.my_status)}</span> <a href="${esc(p.url)}" target="_blank" rel="noopener">Official posting ↗</a></div>
  <div class="small">First seen ${esc(p.first_seen)} · last seen ${esc(p.last_seen)}</div></div>`).join("");
 $("#view").innerHTML=`<div class="small" style="margin-bottom:6px">${r.length} postings</div><div class="tblwrap"><table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div><div class="cards">${cards}</div>`;
 document.querySelectorAll("th[data-k]").forEach(h=>h.onclick=()=>{const k=h.dataset.k;sortDir=(k===sortKey)?-sortDir:(k==="score"?-1:1);sortKey=k;renderJobs()})}
function renderHealth(){const h=DATA.health;
 const cls=s=>s.startsWith("OK")?"okc":s.startsWith("ERROR")||s.startsWith("ZERO")?"badc":"warnc";
 $("#view").innerHTML=`<div class="small" style="margin-bottom:6px">${h.length} sources · ${h.filter(x=>x.health.startsWith("OK")).length} OK</div><div class="tblwrap health"><table><thead><tr><th>Status</th><th>Source</th><th>Sector</th><th>Adapter</th><th>Jobs today</th><th>Relevant</th><th>Maybe</th><th>Last success</th><th>Error / notes</th></tr></thead><tbody>${
 h.map(x=>`<tr><td class="st ${cls(x.health)}">${esc(x.health)}</td><td><a href="${esc(x.careers_url)}" target="_blank" rel="noopener">${esc(x.name)}</a></td><td>${esc(x.sector)}</td><td>${esc(x.adapter)}</td><td>${x.fetched??""}</td><td>${x.relevant??""}</td><td>${x.maybe??""}</td><td>${esc((x.last_success||"").slice(0,16).replace("T"," "))}</td><td><span class="badc">${esc(x.error)}</span><div class="small">${esc(x.notes)}</div></td></tr>`).join("")}</tbody></table></div>
 <div class="cards">${h.map(x=>`<div class="card"><b class="${cls(x.health)}">${esc(x.health)}</b> · <b>${esc(x.name)}</b> <span class="small">(${esc(x.adapter)})</span><div class="small">jobs ${x.fetched??"–"} · relevant ${x.relevant??"–"} · maybe ${x.maybe??"–"} · last success ${esc((x.last_success||"").slice(0,10))}</div><div class="small badc">${esc(x.error)}</div><div class="small">${esc(x.notes)}</div></div>`).join("")}</div>`}
function render(){document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("on",b.dataset.tab===tab));$("#filters").style.display=tab==="health"?"none":"flex";tab==="health"?renderHealth():renderJobs();save()}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render()});
["fCountry","fStatus","fRel","fMine","fText"].forEach(id=>$("#"+id).addEventListener("input",render));
render();
</script></body></html>"""


def build(store: Store | None = None, out_dir=None) -> str:
    own = store is None
    store = store or Store()
    out_dir = out_dir or config.SITE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    all_posts = data.postings(store)
    # never show a posting as active unless its official URL passed today's check
    shown = [p for p in all_posts if p["display_status"] == "Removed" or p.get("verified") == 1]
    unverified = sum(1 for p in all_posts if p["display_status"] != "Removed" and p.get("verified") != 1)
    for p in shown:
        if config.is_aggregator(p["url"]):
            raise RuntimeError(f"aggregator URL leaked into dashboard: {p['url']}")
    health = data.source_health(store)
    payload = {"postings": shown, "health": health, "statuses": data.STATUSES,
               "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
    active = [p for p in shown if p["display_status"] != "Removed"]
    counts = (f"{sum(1 for p in active if p['sector']=='sports')} sports · "
              f"{sum(1 for p in active if p['sector']=='wealth')} wealth · "
              f"{sum(1 for h in health if h['health'].startswith('OK'))}/{len(health)} sources OK"
              + (f" · {unverified} hidden (URL check failed)" if unverified else ""))
    page = (TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__UPDATED__", html.escape(payload["generated"].replace("T", " ") + " UTC"))
            .replace("__COUNTS__", html.escape(counts)))
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    (out_dir / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
    if own:
        store.close()
    return str(out_dir / "index.html")
