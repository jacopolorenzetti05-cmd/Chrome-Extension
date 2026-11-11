"""Enrichment: pay, languages, type/timing, deadline and the 1–10 score (SPEC §6–7)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re

from . import config, geo
from .models import norm

TODAY = dt.date.today()

# ---------------------------------------------------------------- pay
PAY_CONTEXT = re.compile(r"salary|stipend|pay\b|paid|vergutung|verguetung|gehalt|entgelt|lohn|retribuzion|retribuit|"
                         r"compenso|rimborso|remunerat|compensation|salaire|gratification|sueldo|salario|brutto|bruto|"
                         r"gross|per month|monthly|monatlich|al mese|mensil|par mois|per annum|p a\b|jahresgehalt", re.I)
AMOUNT = re.compile(
    r"(?P<cur1>€|eur|chf|£|gbp|usd|\$|sfr\.?|fr\.)\s?(?P<a>\d{1,3}(?:[.,' ]\d{3})*(?:[.,]\d{1,2})?\s?k?)"
    r"(?:\s?(?:-|–|to|bis|a)\s?(?:€|eur|chf|£|gbp)?\s?(?P<b>\d{1,3}(?:[.,' ]\d{3})*(?:[.,]\d{1,2})?\s?k?))?"
    r"|(?P<a2>\d{1,3}(?:[.,' ]\d{3})*(?:[.,]\d{1,2})?\s?k?)(?:\s?(?:-|–|to|bis)\s?(?P<b2>\d{1,3}(?:[.,' ]\d{3})*(?:[.,]\d{1,2})?\s?k?))?"
    r"\s?(?P<cur2>€|eur|euro|chf|£|gbp|franken)",
    re.I)
PERIOD = re.compile(r"(per|/|a|pro|al|par|each)\s?(month|monat|mese|mois|mes)|monthly|monatlich|mensil|"
                    r"(per|/|a|pro|al|par)\s?(year|annum|jahr|anno|an|ano)|annual|jahres|p\.?a\.?|"
                    r"(per|/|pro|an|all)\s?(hour|stunde|ora|heure|hora)|hourly|stundenlohn", re.I)


def _num(s: str) -> float:
    s = s.strip().lower()
    k = s.endswith("k")
    s = s.rstrip("k").strip().replace("'", "").replace(" ", "")
    if re.search(r"[.,]\d{3}$", s) or re.search(r"[.,]\d{3}[.,]", s):
        s = re.sub(r"[.,](?=\d{3})", "", s)
    s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return 0
    return v * 1000 if k else v


def posted_pay(text: str) -> str:
    """Find a salary/stipend stated in the posting text. Returns '' if none."""
    if not text:
        return ""
    for m in AMOUNT.finditer(text):
        ctx = text[max(0, m.start() - 120): m.end() + 60]
        if not PAY_CONTEXT.search(ctx):
            continue
        a = _num(m.group("a") or m.group("a2") or "0")
        if a < 8 or a > 400000:            # rule out "3 days", "€5bn"
            continue
        if re.search(r"(bn|billion|million|mio|mrd|milliard|turnover|revenue|umsatz|fatturato)", ctx, re.I):
            continue
        per = PERIOD.search(text[m.end(): m.end() + 40]) or PERIOD.search(ctx)
        unit = ""
        if per:
            p = per.group(0).lower()
            unit = "/hour" if re.search(r"hour|stunde|ora|heure|hora", p) else "/month" if re.search(r"mon|mese|mois|mes", p) else "/year"
        return re.sub(r"\s+", " ", m.group(0)).strip() + (f" {unit}" if unit else "")
    return ""


def estimate_pay(country: str, kind: str, table: dict | None = None) -> str:
    table = table if table is not None else config.load_yaml(config.PAY_FILE, {})
    bucket = {"intern": "intern", "working_student": "intern", "trainee": "graduate", "graduate": "graduate"}.get(kind, "entry")
    row = (table.get("countries") or {}).get(country) or (table.get("countries") or {}).get("default")
    if not row or bucket not in row:
        return ""
    return f"{row[bucket]}"


# ---------------------------------------------------------------- languages
LANGS = {
    "German": r"german|deutsch\w*|tedesco|allemand|aleman",
    "English": r"english|englisch\w*|inglese|anglais|ingles",
    "Italian": r"italian|italienisch\w*|italiano|italien|italiana",
    "French": r"french|franzosisch\w*|francese|francais|frances",
    "Spanish": r"spanish|spanisch\w*|spagnolo|espagnol|espanol|castellano",
    "Dutch": r"dutch|niederlandisch\w*|olandese|neerlandais|nederlands",
    "Portuguese": r"portuguese|portugiesisch|portoghese|portugais|portugues",
    "Arabic": r"arabic|arabisch",
    "Polish": r"polish|polnisch",
    "Mandarin": r"mandarin|chinese|chinesisch",
}
REQ = re.compile(r"fluen\w*|proficien\w*|native|mother tongue|business level|business fluent|working knowledge|"
                 r"excellent|very good|good command|command of|written and spoken|spoken and written|c1|c2|b2|"
                 r"required|essential|must|skills|kenntniss\w*|sprachkenntnis\w*|verhandlungssicher|fliessend|"
                 r"sehr gut\w*|gute|muttersprach\w*|wort und schrift|conoscenza|ottim\w*|padronanza|fluente|"
                 r"madrelingua|maitrise|courant|bilingu\w*|dominio|nivel|imprescindible|language|sprache|lingua|langue|idioma")
STOP = {
    "English": " the and with you our for are will your this have from team ",
    "German": " und der die das mit sie wir fur ihre eine ein ist auf bei im zu ",
    "Italian": " il la di che per con della delle sono una nel ed gli dei ",
    "French": " le la les des et pour avec vous nous une est dans du sur ",
    "Spanish": " el la los las con para que una del por nuestro como es ",
    "Dutch": " de het een en van voor met je wij zijn bij ",
}


def posting_language(text: str) -> str:
    words = " " + norm(text[:4000]) + " "
    scores = {lang: sum(words.count(f" {w} ") for w in s.split()) for lang, s in STOP.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 5 else ""


def languages(title: str, text: str) -> tuple[list[str], str, str]:
    """Return (required languages, posting language, display string)."""
    found: list[str] = []
    for sent in re.split(r"(?<=[.!?;•·\n])\s+|\s[-–•]\s", text or ""):
        s = norm(sent)
        if len(s) > 400:
            s = s[:400]
        if not REQ.search(s):
            continue
        for lang, pat in LANGS.items():
            if re.search(r"(?<![a-z])(?:" + pat + r")(?![a-z])", s) and lang not in found:
                found.append(lang)
    tl = norm(title)
    for lang, pat in LANGS.items():
        if re.search(r"(?<![a-z])(?:" + pat + r")(?![a-z])", tl) and lang not in found and re.search(r"speak|sprach|native|lingua", tl):
            found.append(lang)
    plang = posting_language(text or title)
    if found:
        disp = ", ".join(found)
    elif plang:
        disp = f"{plang} (likely)"
    else:
        disp = ""
    return found, plang, disp


# ---------------------------------------------------------------- timing / deadline
MONTHS = {m: i for i, ms in enumerate([
    "january|januar|jan|gennaio|janvier|enero", "february|februar|feb|febbraio|fevrier|febrero",
    "march|marz|maerz|mar|marzo|mars", "april|apr|aprile|avril|abril", "may|mai|maggio|mayo",
    "june|juni|jun|giugno|juin|junio", "july|juli|jul|luglio|juillet|julio", "august|aug|agosto|aout",
    "september|sept|sep|settembre|septembre|septiembre", "october|oktober|oct|okt|ottobre|octobre|octubre",
    "november|nov|novembre|noviembre", "december|dezember|dec|dez|dicembre|decembre|diciembre"], 1)
    for m in ms.split("|")}
MONTH_RX = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_RXES = [
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{1,2})[./](\d{1,2})[./](20\d{2})"),
    re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\.?\s+(" + MONTH_RX + r")\.?,?\s+(20\d{2})", re.I),
    re.compile(r"(" + MONTH_RX + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})", re.I),
]
DEADLINE_CTX = re.compile(r"deadline|closing date|closes on|apply by|apply before|applications? close|"
                          r"bewerbungsfrist|bewerbungsschluss|bewerbung bis|bewerben bis|scadenza|entro il|candidature entro|"
                          r"fecha limite|plazo|date limite|avant le|until|bis zum|by the", re.I)


def _parse_date(s: str) -> dt.date | None:
    for i, rx in enumerate(DATE_RXES):
        m = rx.search(s)
        if not m:
            continue
        try:
            if i == 0:
                return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if i == 1:
                return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if i == 2:
                return dt.date(int(m.group(3)), MONTHS[norm(m.group(2))], int(m.group(1)))
            if i == 3:
                return dt.date(int(m.group(3)), MONTHS[norm(m.group(1))], int(m.group(2)))
        except (ValueError, KeyError):
            continue
    return None


def find_deadline(text: str) -> str:
    for m in DEADLINE_CTX.finditer(text or ""):
        d = _parse_date(text[m.end(): m.end() + 60])
        if d and TODAY - dt.timedelta(days=60) <= d <= TODAY + dt.timedelta(days=400):
            return d.isoformat()
    return ""


START_RX = re.compile(r"(?:start(?:ing)?(?: date)?|beginn|eintritt|ab|from|inizio|a partire da|des|début|debut|"
                      r"incorporacion|starts?|commencing|available from)\s*:?\s*(?:in |im |on |the |le |el |dal |the )?"
                      r"(?:(\d{1,2})[./])?\s*((?:" + MONTH_RX + r")|\d{1,2})[./ ,]*\s*(20\d{2})", re.I)


def timing(title: str, text: str, kind: str) -> tuple[str, int]:
    """Return (label, fit) where fit is +1 good, 0 neutral, -1 clashes with the Dublin term (Jan–May 2027)."""
    t = norm(title + " " + (text or "")[:6000])
    if re.search(r"summer(?: \w+){0,2} (?:20)?27|sommer(?:praktikum)? 2027|estate 2027|ete 2027|2027 summer", t):
        return "Summer 2027", 1
    if re.search(r"off ?cycle", t):
        m = START_RX.search(text or "")
        return ("Off-cycle" + (f" (start {m.group(2)} {m.group(3)})" if m else "")), 0 if not m else _fit(m)
    if re.search(r"graduate (?:programme|program).{0,40}(2027|2028)|(2027|2028).{0,30}graduate", t):
        yr = re.search(r"(2027|2028)", t).group(1)
        return f"Graduate {yr}", 1
    m = START_RX.search(text or "")
    if m:
        return f"Start {m.group(2).capitalize() if not m.group(2).isdigit() else m.group(2)} {m.group(3)}", _fit(m)
    if re.search(r"summer (?:20)?26|sommer 2026", t):
        return "Summer 2026", -1
    if re.search(r"\b(asap|immediately|ab sofort|sofort|immediate start|da subito|des que possible)\b", t):
        return "ASAP", -1 if kind in ("intern", "working_student") else 0
    return "", 0


def _fit(m) -> int:
    mon = m.group(2)
    try:
        month = int(mon) if mon.isdigit() else MONTHS[norm(mon)]
        year = int(m.group(3))
    except (KeyError, ValueError):
        return 0
    if year == 2027 and 1 <= month <= 5:
        return -1
    if (year == 2027 and month >= 6) or year >= 2028:
        return 1
    return -1 if year <= 2026 else 0


TYPE_LABEL = {"intern": "Internship", "working_student": "Working student", "graduate": "Graduate programme",
              "trainee": "Trainee", "entry": "Entry level", "other": "Junior/other"}


# ---------------------------------------------------------------- scoring
STRONG_FUNCS_SPORTS = re.compile(r"partnership|sponsor|commercial|business development|key account|licens|"
                                 r"hospitality|media rights|sales|vertrieb|vermarktung|partner")
STRONG_FUNCS_WEALTH = re.compile(r"private bank|wealth|client advis|relationship manag|kundenberat|private client|"
                                 r"advisory|family office|hnw")


def rule_score(rec: dict) -> tuple[int, str]:
    t = norm(rec["title"])
    s = 4.5
    why = []
    sector = rec["sector"]
    strong = (STRONG_FUNCS_WEALTH if sector == "wealth" else STRONG_FUNCS_SPORTS).search(t)
    if strong:
        s += 2
        why.append(f"{strong.group(0)} role")
    elif re.search(r"marketing|brand|client|events|ticketing|strategy", t):
        s += 1
        why.append("commercial-adjacent role")
    country = rec.get("country", "")
    loc = rec.get("location", "")
    if country in geo.TIER1 or geo.is_milan(loc):
        s += 1.5
        why.append(f"tier-1 location ({'Milan' if geo.is_milan(loc) else geo.COUNTRY_LABEL.get(country, country)})")
    elif country in geo.TIER2:
        s += 1
        why.append(f"tier-2 location ({geo.COUNTRY_LABEL.get(country, country)})")
    lvl = rec.get("level")
    if lvl in ("intern", "graduate", "trainee"):
        s += 1
        why.append(TYPE_LABEL[lvl].lower())
    elif lvl == "working_student":
        s -= 0.5
        why.append("working-student (needs local enrolment)")
    elif lvl == "entry":
        s += 0.5
    req = rec.get("languages_required") or []
    if any(l in ("German", "Italian") for l in req):
        s += 1
        why.append("German/Italian is an edge")
    others = [l for l in req if l not in ("German", "Italian", "English")]
    if others and not any(l in ("German", "Italian") for l in req):
        s -= 1.5
        why.append(f"needs {', '.join(others)}")
    fit = rec.get("timing_fit", 0)
    if fit > 0:
        s += 1
        why.append("timing fits (summer/late 2027)")
    elif fit < 0:
        s -= 1.5
        why.append("timing clashes with Dublin term")
    if rec.get("relevance") == "maybe":
        s -= 1.5
    s = max(1, min(10, round(s)))
    return int(s), ("; ".join(why[:4]) or "borderline match").capitalize()


def claude_score(rec: dict, profile: str) -> tuple[int, str] | None:
    """Optional: ask Claude for a 1–10 score + one-sentence reason (needs ANTHROPIC_API_KEY)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic(max_retries=2)
    prompt = (f"Candidate profile:\n{profile}\n\nJob posting:\nCompany: {rec['company']}\nTitle: {rec['title']}\n"
              f"Location: {rec['location']}\nType/timing: {rec.get('type','')} {rec.get('timing','')}\n"
              f"Languages: {rec.get('languages','')}\nDescription (excerpt): {rec.get('description','')[:3500]}\n\n"
              "Rate how well this posting fits the candidate on a 1-10 scale using the profile's score guide. "
              'Reply with JSON only: {"score": <int 1-10>, "why": "<one sentence>"}')
    try:
        resp = client.beta.messages.create(
            model=os.environ.get("JOBRADAR_CLAUDE_MODEL", "claude-opus-5-5"), max_tokens=2000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            messages=[{"role": "user", "content": prompt}])
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if b.type == "text")
        d = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        return max(1, min(10, int(d["score"]))), str(d["why"]).strip()
    except Exception:
        return None


def enrich(rec: dict, pay_table: dict) -> dict:
    """rec contains title, description, location, country, level, sector, relevance, salary_text, deadline."""
    text = rec.get("description", "")
    req, plang, disp = languages(rec["title"], text)
    rec["languages_required"] = req
    rec["posting_language"] = plang
    rec["languages"] = disp
    pp = rec.get("salary_text") or posted_pay(text)
    if pp:
        rec["pay"] = f"{pp} (posted)"
    else:
        est = estimate_pay(rec.get("country") or "default", rec.get("level", "other"), pay_table)
        rec["pay"] = f"{est} (est.)" if est else ""
    rec["type"] = TYPE_LABEL.get(rec.get("level", "other"), "Other")
    rec["timing"], rec["timing_fit"] = timing(rec["title"], text, rec.get("level", "other"))
    if not rec.get("deadline"):
        rec["deadline"] = find_deadline(text)
    rec["score"], rec["why"] = rule_score(rec)
    rec["score_source"] = "rules"
    return rec
