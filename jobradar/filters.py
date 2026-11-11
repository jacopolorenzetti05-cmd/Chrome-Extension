"""Relevance filter: keep / maybe / drop for each posting (see SPEC §5)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import geo
from .models import norm


def _rx(words: list[str]) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(words) + r")(?![a-z0-9])")


# ---- level -------------------------------------------------------------------------------------
LEVEL_STRONG = _rx([
    r"intern", r"interns", r"internship\w*", r"praktik\w*", r"pflichtpraktik\w*", r"werkstudent\w*", r"working student",
    r"stage", r"stages", r"stagiaire\w*", r"tirocini\w*", r"tirocinante", r"stagista", r"stagisti", r"trainee\w*",
    r"graduate\w*", r"grad", r"summer analyst\w*", r"summer associate\w*", r"summer (?:intern|internship|programme|program)\w*",
    r"off[ -]?cycle", r"junior", r"jr", r"entry[ -]level", r"early careers?", r"absolvent\w*", r"berufseinsteiger\w*",
    r"einstieg\w*", r"neolaureat\w*", r"neo laureat\w*", r"jeune diplome\w*", r"beca", r"becas", r"becario\w*",
    r"practicas", r"alternance", r"alternant\w*", r"young professional\w*", r"analyst program\w*", r"graduate program\w*",
    r"rotational", r"volontariat", r"volontaire international", r"vie", r"apprenticeship\w*", r"student\w*",
    r"thesis", r"masterand\w*", r"abschlussarbeit", r"tesista", r"debut"])
LEVEL_WEAK = _rx([r"associate", r"assistant\w*", r"coordinator", r"co ordinator", r"coordinat\w+", r"executive",
                  r"analyst", r"specialist", r"referent\w*", r"sachbearbeiter\w*", r"officer", r"consultant",
                  r"advisor", r"adviser", r"representative", r"addett\w*", r"assistente", r"mitarbeiter\w*",
                  r"tecnico", r"tecnica", r"specialista", r"chargee?", r"charge de"])
SENIOR = _rx([r"senior", r"sr", r"director\w*", r"head", r"heads", r"lead", r"principal", r"vice president", r"vp",
              r"svp", r"evp", r"chief", r"cfo", r"ceo", r"cmo", r"coo", r"leiter\w*", r"leitung", r"teamleiter\w*",
              r"abteilungsleiter\w*", r"bereichsleiter\w*", r"direttore", r"direttrice", r"directeur", r"directrice",
              r"responsabile", r"responsable", r"gerente", r"jefe", r"jefa", r"managing", r"expert\w*", r"executive director",
              r"md", r"partner", r"staff", r"team lead\w*", r"supervisor", r"mid level", r"experienced", r"lateral"])
MANAGER = _rx([r"manager\w*", r"managerin"])

# ---- function -----------------------------------------------------------------------------------
FUNC_SPORTS = _rx([
    r"partnerships?", r"partner management", r"partnermanagement", r"partner relations", r"sponsorships?",
    r"sponsoring", r"sponsor", r"sponsors", r"commercial\w*", r"commerciale", r"commerciali", r"comercial\w*",
    r"sales", r"vertrieb\w*", r"vermarktung", r"vendite", r"ventas", r"ventes", r"business development",
    r"geschaftsentwicklung", r"key account\w*", r"account manage\w*", r"account executive", r"licens\w*", r"licen[cs]ing",
    r"merchandising", r"hospitality", r"brand\w*", r"marketing", r"media rights", r"rights", r"broadcaster",
    r"client\w*", r"relationship\w*", r"advisory", r"revenue", r"growth", r"fan engagement", r"ticketing",
    r"crm", r"partenariat\w*", r"patrocinio\w*", r"sponsorizzazion\w*", r"kooperation\w*", r"events?",
    r"activation", r"go to market", r"customer success", r"business partner", r"betting account", r"trading partner",
    r"strategy", r"strategie", r"estrategia", r"strategia", r"negocio"])
FUNC_WEALTH = _rx([
    r"private bank\w*", r"private client\w*", r"wealth\w*", r"wealth management", r"asset (?:and|&)? ?wealth",
    r"awm", r"family office", r"uhnw", r"hnw\w*", r"client advis\w*", r"client service\w*", r"client relationship\w*",
    r"client\w*", r"relationship manage\w*", r"relationship\w*", r"advisory", r"investment advis\w*",
    r"investment consult\w*", r"investment specialist", r"kundenberat\w*", r"anlageberat\w*", r"vermogensverwaltung",
    r"consulenza", r"consulente finanziari\w*", r"private banker\w*", r"sales", r"business management",
    r"business manager", r"investment specialist", r"products? specialist", r"gestion de fortune",
    r"gestione patrimon\w*", r"intermediar\w*", r"berater\w*", r"external asset manag\w*", r"eam",
    r"service clients?", r"clientele"])
WEALTH_CORE = _rx([r"private bank\w*", r"private client\w*", r"wealth\w*", r"family office", r"uhnw", r"hnw\w*",
                   r"client advis\w*", r"relationship manage\w*", r"kundenberat\w*", r"anlageberat\w*",
                   r"vermogensverwaltung", r"private banker\w*", r"gestion de fortune", r"gestione patrimon\w*",
                   r"consulente finanziari\w*", r"awm", r"asset (?:and|&)? ?wealth", r"banquier\w* prive\w*",
                   r"banca privata", r"privatbank\w*", r"gestion privee", r"private wealth", r"client advisor\w*"])

# hard excludes (function) – checked on the title
EXCLUDE = _rx([
    r"engineer\w*", r"engineering", r"developer\w*", r"entwickler\w*", r"software", r"devops", r"sre", r"it",
    r"cyber\w*", r"infrastructure", r"cloud", r"network", r"sap", r"programmer", r"data engineer\w*", r"data scien\w*",
    r"machine learning", r"ml", r"ai engineer", r"qa", r"tester", r"test", r"architect\w*", r"technolog\w*", r"tech",
    r"informatik\w*", r"fullstack", r"full stack", r"backend", r"frontend", r"ux", r"ui", r"designer\w*", r"design",
    r"legal", r"lawyer", r"counsel", r"jurist\w*", r"paralegal", r"recht\w*", r"avvocat\w*", r"abogad\w*", r"juridique",
    r"hr", r"human resources", r"people partner", r"people", r"recruit\w*", r"talent acquisition", r"personal\w*",
    r"payroll", r"risorse umane", r"recursos humanos", r"ressources humaines", r"compliance", r"kyc", r"aml",
    r"audit\w*", r"tax", r"steuer\w*", r"accountant", r"accounting", r"buchhalt\w*", r"controller\w*", r"controlling",
    r"risk", r"credit", r"treasury", r"fund accounting", r"operations?", r"ops", r"logisti\w*", r"warehouse", r"lager\w*",
    r"supply chain", r"procurement", r"einkauf", r"facility", r"facilities", r"maintenance", r"technician\w*",
    r"mechanic\w*", r"techniker\w*", r"electrician", r"driver", r"fahrer\w*", r"chef", r"koch", r"kitchen", r"kuche",
    r"cook", r"bartender", r"barista", r"waiter", r"kellner\w*", r"service kraft", r"servicekraft", r"aushilfe\w*",
    r"minijob\w*", r"steward\w*", r"ordner", r"security", r"cleaner", r"reinigung\w*", r"greenkeeper\w*", r"gartner",
    r"physio\w*", r"therapist", r"nurse", r"doctor", r"medical", r"arzt", r"coach", r"coaches", r"scout\w*",
    r"trainer\w*", r"athletic", r"kit", r"store", r"stores", r"shop", r"boutique", r"retail associate\w*",
    r"sales associate\w*", r"sales assistant", r"sales advisor", r"verkaufer\w*", r"cashier", r"kassierer\w*",
    r"vendeu\w*", r"conseill\w* de vente", r"commess\w*", r"addett\w* vendita", r"dependient\w*", r"magasin",
    r"tienda", r"negozio", r"filiale", r"call center", r"contact centre", r"customer service", r"kundenservice",
    r"receptionist", r"rezeption\w*", r"empfang", r"office manager", r"secretary", r"sekretar\w*", r"translator",
    r"editor", r"journalist", r"redakteur\w*", r"producer", r"camera\w*", r"video\w*", r"photograph\w*",
    r"statistician", r"data collection", r"actuar\w*", r"quant\w*", r"trader", r"trading", r"research analyst",
    r"equity research", r"product owner", r"product manager", r"scrum", r"project manager", r"pmo",
    r"administrator", r"admin", r"administration", r"administrativ\w*", r"verwaltung", r"amministrazion\w*",
    r"administracion", r"lohn\w*", r"nachhaltigkeit", r"sustainability", r"esg", r"forensic", r"investigat\w*",
    r"fraud", r"collections", r"underwrit\w*", r"insurance", r"claims", r"mortgage", r"loan", r"lending",
    r"operations specialist", r"settlement\w*", r"custody", r"reconciliation\w*", r"fund administration",
    r"kitman", r"groundsman", r"turf", r"pitch", r"academy", r"medic\w*", r"ausbildung\w*", r"azubi\w*",
    r"auszubildend\w*", r"apprenti", r"lehrstelle", r"lehrling", r"fachinformatik\w*", r"kaufmann", r"kauffrau",
    r"kaufleute", r"duales studium", r"dual\w* stud\w*", r"school leaver\w*", r"volunteer\w*", r"volontari\w*",
    r"ehrenamt\w*", r"nutrition\w*", r"sport scien\w*", r"performance analyst", r"video analyst", r"match analyst",
    r"physiotherap\w*", r"psycholog\w*", r"social media", r"content", r"copywriter", r"graphic\w*", r"motion",
    r"animation", r"gaming", r"esports", r"media operations", r"broadcast operations", r"broadcast engineer",
    r"seo", r"sem", r"performance marketing", r"growth hacker", r"data analyst", r"business intelligence", r"bi",
    r"analytics", r"cfd", r"aerodynamic\w*", r"simulation", r"vehicle", r"composite\w*", r"machinist", r"fabricat\w*",
    r"cnc", r"race", r"electronics", r"embedded", r"firmware", r"student marketeer\w*", r"brand ambassador\w*",
    r"campus ambassador\w*", r"promoter\w*", r"merchandiser\w*", r"filial\w*", r"branch", r"teller",
    r"investment bank\w*", r"m a", r"capital markets", r"corporate finance", r"leveraged finance", r"ecm", r"dcm",
    r"fig", r"restructuring", r"private equity", r"private markets", r"structur\w*", r"derivative\w*",
    r"securities", r"prime services", r"global markets", r"sales trading", r"sales and trading", r"research",
    r"accounting", r"wealthtech", r"fintech", r"architect", r"business architect", r"troisieme", r"3eme", r"seconde",
    r"collegien\w*", r"lyceen\w*", r"schuler\w*", r"schulpraktik\w*", r"ingenieur\w*", r"planning", r"planner",
    r"amelioration continue", r"continuous improvement", r"production", r"produktion", r"quality", r"qualite",
    r"qualita", r"supply", r"maintenance", r"manufactur\w*", r"r d", r"laborator\w*", r"finance", r"financial",
    r"finanz\w*", r"comptab\w*", r"contabil\w*", r"auditor\w*", r"tresorerie", r"payroll", r"procure\w*",
    r"achats", r"acquisti", r"compras", r"approvisionn\w*", r"cogs"])
# functions that are fine to keep despite an EXCLUDE word (e.g. "Sales Operations" is still excluded, but
# "Commercial Partnerships – Media Rights" is not touched). Title words that rescue an excluded match:
RESCUE = _rx([r"partnerships?", r"sponsorship\w*", r"sponsoring", r"commercial", r"business development",
              r"private bank\w*", r"wealth", r"client advis\w*", r"relationship manage\w*", r"key account\w*",
              r"licensing", r"hospitality", r"media rights", r"financial advis\w*", r"consulent\w* finanziar\w*",
              r"finanzberat\w*", r"commercial finance", r"revenue"])
NON_EUROPE_ONLY = _rx([r"usa only", r"us only", r"u s based", r"must be based in the us", r"apac only"])
UNPAID = _rx([r"unpaid", r"non retribuit\w*", r"unbezahlt\w*", r"unvergutet\w*", r"non remunerat\w*", r"sin remuneracion",
              r"no remunerad\w*", r"volunteer position"])
YEARS = re.compile(r"(?:(?:at least|minimum|min|mindestens|almeno|au moins|minimo)\s+)?(\d{1,2})\s*\+?\s*"
                   r"(?:(?:-|to|bis|a|–)\s*\d{1,2}\s*)?(?:years?|yrs|jahre\w*|anni|ans|anos)\b"
                   r"(?:\s+\w+){0,6}?\s+(?:experience|erfahrung|esperienza|experiencia|berufserfahrung|work|relevant|professional|in)",
                   re.I)


@dataclass
class Verdict:
    relevance: str          # keep | maybe | drop
    reason: str
    level: str              # intern | working_student | graduate | entry | trainee | other
    region: str             # europe | mixed | non-europe | unknown
    country: str


def level_of(title_n: str, desc_n: str) -> str:
    if re.search(r"werkstudent|working student|studentische", title_n):
        return "working_student"
    if re.search(r"intern|praktik|stage|stagiaire|tirocin|stagist|summer|off ?cycle|beca|becario|practicas|thesis|"
                 r"masterand|alternan|vie\b|volontariat|debut", title_n):
        return "intern"
    if re.search(r"graduate|grad\b|absolvent|neolaureat|jeune diplome|analyst program|rotational|young professional|"
                 r"early career", title_n):
        return "graduate"
    if re.search(r"trainee", title_n):
        return "trainee"
    if re.search(r"junior|\bjr\b|entry level|einstieg|berufseinsteiger", title_n):
        return "entry"
    if re.search(r"student", title_n):
        return "working_student"
    return "other"


def max_years_required(desc: str) -> int:
    yrs = [int(m.group(1)) for m in YEARS.finditer(desc or "") if 0 < int(m.group(1)) < 30]
    return max(yrs) if yrs else 0


def classify(title: str, location: str, description: str, sector: str, src: dict | None = None,
             meta: str = "") -> Verdict:
    """meta = structured hints from the hiring system (department, division, category …)."""
    src = src or {}
    t = norm(title)
    meta_n = norm(meta)
    d = norm(description)[:15000]
    loc = location or ""
    reg = geo.region(loc)
    if reg == "unknown" and src.get("country"):
        # no usable location: the organisation's HQ decides Europe vs not, but no country is invented
        reg = "europe" if src["country"] in geo.EUROPE else "unknown"
    country = geo.primary_country(loc)
    lvl = level_of(t, d)
    v = lambda rel, why: Verdict(rel, why, lvl, reg, country or "")

    if reg == "non-europe":
        return v("drop", "outside Europe")
    tx = (src.get("params") or {}).get("title_exclude") or src.get("title_exclude")
    if tx and re.search(tx, title, re.I):
        return v("drop", "excluded by source rule (title_exclude)")
    if UNPAID.search(d) or UNPAID.search(t):
        return v("drop", "unpaid")
    hard = re.search(r"(?<![a-z])(engineer\w*|developer\w*|software|devops|data scien\w*)(?![a-z])", t)
    if hard:
        return v("drop", f"function excluded ('{hard.group(0)}')")
    excluded = EXCLUDE.search(t)
    if excluded and not RESCUE.search(t):
        return v("drop", f"function excluded ('{excluded.group(0)}')")
    strong = LEVEL_STRONG.search(t)
    weak = LEVEL_WEAK.search(t)
    senior = SENIOR.search(t)
    manager = MANAGER.search(t)
    years = max_years_required(description)

    # Teamwork-style "Assistant Manager"/"Associate Relationship Manager" are junior despite "manager"
    junior_manager = re.search(r"(assistant|associate|junior|trainee|graduate) (\w+ ){0,2}manager", t)
    if senior and not strong:
        return v("drop", f"senior ('{senior.group(0)}')")
    if strong and senior and re.search(r"senior|head|director|lead|principal|chief", t):
        return v("drop", f"senior ('{senior.group(0)}')")
    if manager and not strong and not junior_manager:
        if years >= 3:
            return v("drop", f"manager role, {years}+ years required")
    if years >= 5 and not strong:
        return v("drop", f"{years}+ years experience required")

    is_wealth = sector == "wealth"
    func_rx = FUNC_WEALTH if is_wealth else FUNC_SPORTS
    fm = func_rx.search(t)
    fm_desc = func_rx.search(d[:4000]) if not fm else None
    if is_wealth and src.get("wealth_arm_only"):
        # large universal banks: only their wealth / private-bank arm counts
        if not (WEALTH_CORE.search(t) or WEALTH_CORE.search(meta_n)):
            if strong and fm:
                return v("maybe", "entry-level client/sales role outside the wealth arm")
            return v("drop", "not in the wealth / private-bank arm")

    if strong:
        if fm:
            rel, why = "keep", f"{lvl} + {fm.group(0)}"
        elif fm_desc:
            rel, why = "maybe", f"{lvl}; function only in description ('{fm_desc.group(0)}')"
        else:
            return v("drop", f"{lvl} but no commercial/client-facing function")
    elif fm and (weak or junior_manager):
        rel, why = ("keep" if years <= 2 and (not manager or junior_manager) else "maybe"), f"junior-level {fm.group(0)} role"
        if rel == "keep" and years == 0 and not re.search(r"junior|assistant|coordinator|associate", t):
            rel, why = "maybe", f"{fm.group(0)} role, level unclear"
    elif fm and manager:
        rel, why = "maybe", f"{fm.group(0)} manager, no long experience requirement found"
    elif fm:
        rel, why = ("maybe" if years <= 3 else "drop"), f"{fm.group(0)} role, level unclear"
    else:
        return v("drop", "no target function or level")
    if reg == "unknown" and rel == "keep":
        rel, why = "maybe", why + "; location unknown"
    if reg == "mixed":
        why += "; multi-country"
    return v(rel, why)
