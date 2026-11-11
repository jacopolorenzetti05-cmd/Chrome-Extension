"""Very small location → country resolver (Europe-focused)."""
from __future__ import annotations

import re

from .models import norm

EUROPE = {"CH", "DE", "AT", "LU", "IT", "IE", "GB", "MC", "NL", "ES", "FR", "BE", "PT", "DK", "SE",
          "NO", "FI", "PL", "CZ", "SK", "HU", "SI", "HR", "RO", "BG", "GR", "CY", "MT", "EE", "LV",
          "LT", "IS", "LI", "RS", "BA", "ME", "MK", "AL", "UA", "MD", "GI", "SM", "AD", "TR", "IM", "JE", "GG"}

TIER1 = {"CH", "DE", "AT", "LU"}          # + Milan (handled in scoring)
TIER2 = {"IE", "GB", "MC", "NL"}

COUNTRY_NAMES = {
    "CH": ["switzerland", "schweiz", "suisse", "svizzera", "suiza"],
    "DE": ["germany", "deutschland", "allemagne", "germania", "alemania"],
    "AT": ["austria", "osterreich", "oesterreich", "autriche"],
    "LU": ["luxembourg", "luxemburg", "lussemburgo"],
    "IT": ["italy", "italia", "italien", "italie"],
    "IE": ["ireland", "irland", "irlanda", "eire"],
    "GB": ["united kingdom", "uk", "great britain", "england", "scotland", "wales", "northern ireland",
           "regno unito", "vereinigtes konigreich", "gbr"],
    "MC": ["monaco"],
    "NL": ["netherlands", "the netherlands", "niederlande", "paesi bassi", "holland", "nld"],
    "ES": ["spain", "espana", "spanien", "spagna", "esp"],
    "FR": ["france", "frankreich", "francia", "fra"],
    "BE": ["belgium", "belgien", "belgique", "belgio"],
    "PT": ["portugal", "portogallo"],
    "DK": ["denmark", "danemark", "danimarca"],
    "SE": ["sweden", "schweden", "svezia", "sverige"],
    "NO": ["norway", "norwegen", "norge"],
    "FI": ["finland", "finnland"],
    "PL": ["poland", "polen", "polska"],
    "CZ": ["czech republic", "czechia", "tschechien"],
    "SK": ["slovakia"], "HU": ["hungary", "ungarn"], "SI": ["slovenia"], "HR": ["croatia"],
    "RO": ["romania"], "BG": ["bulgaria"], "GR": ["greece", "griechenland"], "CY": ["cyprus"],
    "MT": ["malta"], "EE": ["estonia"], "LV": ["latvia"], "LT": ["lithuania"], "IS": ["iceland"],
    "LI": ["liechtenstein"], "RS": ["serbia"], "UA": ["ukraine"], "GI": ["gibraltar"],
    "TR": ["turkey", "turkiye"], "IM": ["isle of man"], "JE": ["jersey"], "GG": ["guernsey"],
    "BA": ["bosnia"], "MK": ["north macedonia"], "AL": ["albania"], "ME": ["montenegro"],
    # non-Europe
    "US": ["united states", "usa", "u s", "united states of america"],
    "CA": ["canada"], "MX": ["mexico"], "BR": ["brazil", "brasil"], "AR": ["argentina"],
    "CL": ["chile"], "CO": ["colombia"], "PE": ["peru"],
    "CN": ["china"], "HK": ["hong kong"], "SG": ["singapore"], "JP": ["japan"], "KR": ["korea", "south korea"],
    "IN": ["india"], "AU": ["australia"], "NZ": ["new zealand"], "AE": ["united arab emirates", "uae"],
    "SA": ["saudi arabia", "ksa"], "QA": ["qatar"], "BH": ["bahrain"], "IL": ["israel"], "ZA": ["south africa"],
    "EG": ["egypt"], "NG": ["nigeria"], "KE": ["kenya"], "MA": ["morocco"], "TH": ["thailand"],
    "MY": ["malaysia"], "ID": ["indonesia"], "PH": ["philippines"], "VN": ["vietnam"], "TW": ["taiwan"],
    "UY": ["uruguay"], "PA": ["panama"], "BS": ["bahamas"], "KY": ["cayman islands"], "BM": ["bermuda"],
}

CITIES = {
    "CH": ["zurich", "geneva", "geneve", "genf", "basel", "bern", "lausanne", "lugano", "nyon", "zug", "lucerne",
           "luzern", "st gallen", "winterthur", "chiasso", "baar", "schlieren", "opfikon", "fuschl"],
    "DE": ["berlin", "munich", "munchen", "muenchen", "frankfurt", "hamburg", "cologne", "koln", "dusseldorf",
           "duesseldorf", "stuttgart", "dortmund", "leipzig", "herzogenaurach", "leverkusen", "sinsheim",
           "zuzenhausen", "aachen", "hannover", "nuremberg", "nurnberg", "bremen", "essen", "mainz", "wolfsburg",
           "monchengladbach", "bonn", "karlsruhe", "mannheim", "heidelberg", "eschborn", "gelsenkirchen", "freiburg",
           "unterfohring", "ismaning", "garching", "augsburg", "potsdam", "dresden", "kiel", "ingolstadt", "walldorf"],
    "AT": ["vienna", "wien", "salzburg", "graz", "linz", "innsbruck", "wals siezenheim", "fuschl am see",
           "elsbethen", "klagenfurt"],
    "LU": ["luxembourg city", "kirchberg", "leudelange", "bertrange", "strassen", "munsbach"],
    "IT": ["milan", "milano", "rome", "roma", "turin", "torino", "florence", "firenze", "bologna", "naples",
           "napoli", "venice", "venezia", "verona", "genoa", "genova", "cesena", "trieste", "padova", "padua",
           "bergamo", "brescia", "monza", "vinovo", "continassa", "coverciano", "cernusco", "assago"],
    "IE": ["dublin", "cork", "galway", "limerick", "kildare", "waterford", "dun laoghaire", "maynooth"],
    "GB": ["london", "manchester", "birmingham", "edinburgh", "glasgow", "leeds", "liverpool", "bristol",
           "brackley", "milton keynes", "enstone", "brentford", "knutsford", "northampton", "leicester",
           "sheffield", "nottingham", "newcastle", "cardiff", "belfast", "cambridge", "oxford", "reading",
           "chelmsford", "canary wharf", "northwich", "silverstone", "woking", "guildford", "slough", "isleworth",
           "osterley", "harrogate", "brighton", "southampton", "bournemouth", "coventry", "wembley", "poole",
           "radlett", "stockport", "salford", "windsor", "jersey", "guernsey", "orpington", "watford", "leatherhead"],
    "MC": ["monte carlo", "monte-carlo", "fontvieille"],
    "NL": ["amsterdam", "rotterdam", "utrecht", "the hague", "den haag", "eindhoven", "hilversum", "zoeterwoude",
           "hoofddorp", "schiphol", "amstelveen", "leiden", "zwolle", "haarlem"],
    "ES": ["madrid", "barcelona", "valencia", "seville", "sevilla", "malaga", "bilbao", "palma", "alicante",
           "zaragoza", "las rozas", "valdebebas"],
    "FR": ["paris", "lyon", "marseille", "lille", "nice", "toulouse", "bordeaux", "nantes", "strasbourg",
           "viry chatillon", "villeneuve d ascq", "boulogne billancourt", "la defense", "neuilly", "levallois",
           "saint denis", "montpellier", "rennes", "nanterre", "puteaux", "courbevoie", "marcq en baroeul"],
    "BE": ["brussels", "bruxelles", "brussel", "antwerp", "antwerpen", "leuven", "ghent", "gent", "liege"],
    "PT": ["lisbon", "lisboa", "porto", "braga", "oeiras"],
    "DK": ["copenhagen", "kobenhavn", "aarhus"], "SE": ["stockholm", "gothenburg", "goteborg", "malmo"],
    "NO": ["oslo"], "FI": ["helsinki"], "PL": ["warsaw", "warszawa", "krakow", "wroclaw", "katowice", "gdansk", "lodz", "poznan"],
    "CZ": ["prague", "praha", "brno"], "HU": ["budapest"], "RO": ["bucharest", "cluj"], "GR": ["athens", "thessaloniki"],
    "BG": ["sofia"], "HR": ["zagreb"], "SI": ["ljubljana"], "SK": ["bratislava"], "EE": ["tallinn"], "LV": ["riga"],
    "LT": ["vilnius"], "MT": ["valletta", "st julian s", "sliema", "birkirkara"], "CY": ["limassol", "nicosia", "larnaca"],
    "GI": ["gibraltar"], "RS": ["belgrade"], "UA": ["kyiv", "kiev", "lviv"], "IM": ["douglas"], "TR": ["istanbul", "ankara"],
    "LI": ["vaduz", "bendern", "triesen"],
    "US": ["new york", "nyc", "los angeles", "san francisco", "chicago", "boston", "miami", "atlanta", "dallas",
           "houston", "seattle", "denver", "austin", "beaverton", "portland", "philadelphia", "washington",
           "nashville", "charlotte", "phoenix", "las vegas", "orlando", "tampa", "jersey city", "san diego",
           "salt lake", "minneapolis", "detroit", "st louis", "baltimore", "pittsburgh", "indianapolis",
           "columbus", "purchase", "o fallon", "waltham", "stamford", "brooklyn", "beverly hills", "tarrytown",
           "wilmington", "plano", "irving", "tempe", "new jersey", "florida", "california", "texas"],
    "CA": ["toronto", "vancouver", "montreal", "calgary", "ottawa"],
    "MX": ["mexico city", "ciudad de mexico", "monterrey", "guadalajara"], "BR": ["sao paulo", "rio de janeiro"],
    "AR": ["buenos aires"], "CN": ["shanghai", "beijing", "shenzhen", "guangzhou"], "HK": ["hong kong", "kowloon"],
    "SG": ["singapore"], "JP": ["tokyo", "osaka"], "KR": ["seoul"],
    "IN": ["mumbai", "bangalore", "bengaluru", "pune", "hyderabad", "chennai", "delhi", "gurgaon", "gurugram", "noida", "kolkata"],
    "AU": ["sydney", "melbourne", "brisbane", "perth"], "NZ": ["auckland"], "AE": ["dubai", "abu dhabi"],
    "SA": ["riyadh", "jeddah"], "QA": ["doha"], "IL": ["tel aviv"], "ZA": ["johannesburg", "cape town"],
    "TH": ["bangkok"], "MY": ["kuala lumpur"], "PH": ["manila", "taguig"], "ID": ["jakarta"], "TW": ["taipei"],
    "UY": ["montevideo"], "CO": ["bogota"], "CL": ["santiago"], "PE": ["lima"], "EG": ["cairo"], "MA": ["casablanca"],
    "BH": ["manama"],
}

ISO3 = {"CHE": "CH", "DEU": "DE", "AUT": "AT", "LUX": "LU", "ITA": "IT", "IRL": "IE", "GBR": "GB", "MCO": "MC",
        "NLD": "NL", "ESP": "ES", "FRA": "FR", "BEL": "BE", "PRT": "PT", "USA": "US", "POL": "PL", "SWE": "SE",
        "DNK": "DK", "NOR": "NO", "FIN": "FI", "CZE": "CZ", "HKG": "HK", "SGP": "SG", "IND": "IN", "CAN": "CA",
        "AUS": "AU", "ARE": "AE", "JPN": "JP", "CHN": "CN", "BRA": "BR", "MEX": "MX", "GRC": "GR", "ROU": "RO",
        "HUN": "HU", "MLT": "MT", "CYP": "CY", "BGR": "BG", "LIE": "LI", "TUR": "TR", "ISR": "IL", "SAU": "SA"}

US_STATES = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
             "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
             "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"}

_PATTERNS: list[tuple[re.Pattern, str]] = []
for _cc, _names in list(COUNTRY_NAMES.items()) + list(CITIES.items()):
    for _n in _names:
        _PATTERNS.append((re.compile(r"(?<![a-z0-9])" + re.escape(_n) + r"(?![a-z0-9])"), _cc))
# longer names first so "new york" beats "york", "northern ireland" beats "ireland"
_PATTERNS.sort(key=lambda x: -len(x[0].pattern))

COUNTRY_LABEL = {"CH": "Switzerland", "DE": "Germany", "AT": "Austria", "LU": "Luxembourg", "IT": "Italy",
                 "IE": "Ireland", "GB": "United Kingdom", "MC": "Monaco", "NL": "Netherlands", "ES": "Spain",
                 "FR": "France", "BE": "Belgium", "PT": "Portugal", "US": "United States"}


def countries(location: str) -> list[str]:
    """Return ISO-2 country codes found in a free-text location (order of appearance, unique)."""
    if not location:
        return []
    found: list[tuple[int, str]] = []
    raw = location
    # explicit codes like "Zurich, CH" / "London, GB" / "DEU" / "Austin, TX"
    for m in re.finditer(r"(?<![A-Za-z])([A-Z]{2,3})(?![A-Za-z])", raw):
        code = m.group(1)
        if len(code) == 3 and code in ISO3:
            found.append((m.start(), ISO3[code]))
        elif len(code) == 2:
            if code in COUNTRY_NAMES and code not in {"IN", "CO", "ME", "AL", "PA", "LA", "MA", "SA", "ID", "IL", "IS"}:
                found.append((m.start(), code))
            elif code in US_STATES and re.search(r",\s*" + code + r"\b", raw) and code not in {"DE", "IN", "ME", "AL", "PA", "LA", "MA", "CO", "ID", "IL"}:
                found.append((m.start(), "US"))
            elif code == "UK":
                found.append((m.start(), "GB"))
    n = " " + norm(raw) + " "
    taken: list[tuple[int, int]] = []
    for pat, cc in _PATTERNS:
        for m in pat.finditer(n):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start() + 10000, cc))
    out: list[str] = []
    for _, cc in sorted(found):
        if cc not in out:
            out.append(cc)
    return out


def region(location: str) -> str:
    """'europe', 'non-europe', 'mixed' (Europe among others) or 'unknown'."""
    cs = countries(location)
    if not cs:
        if re.search(r"\b(emea|europe|europa|remote eu)\b", location or "", re.I):
            return "europe"
        return "unknown"
    eu = [c for c in cs if c in EUROPE]
    if eu and len(eu) == len(cs):
        return "europe"
    if eu:
        return "mixed"
    return "non-europe"


def primary_country(location: str) -> str:
    cs = countries(location)
    for c in cs:
        if c in EUROPE:
            return c
    return cs[0] if cs else ""


def is_milan(location: str) -> bool:
    return bool(re.search(r"\b(milan|milano)\b", norm(location)))
