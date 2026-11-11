# Job Radar – build specification (for Claude Code)

Owner: Jacopo Lorenzetti. Read this whole file before writing code. Build the project in this folder, test it against the live internet, and do not report "done" until the acceptance checks at the bottom pass.

## 1. Goal

A daily job tracker for two sectors:

1. **Sports business** – partnerships, sponsorship, commercial, sales, business development, licensing, hospitality, marketing roles at clubs, leagues, federations, tours, agencies, sports media and sports data companies, sports brands, sponsor brands that invest heavily in sport (Red Bull, HEINEKEN, AB InBev…), betting operators and sports events.
2. **Wealth management / private banking** – client-facing, advisory, business-management and graduate roles at private banks and the wealth arms of investment banks.

Target level: internships (incl. mandatory internships / Pflichtpraktikum – these are fine), summer and off-cycle 2027 internships, graduate programmes and entry-level roles. Europe only.

## 2. The non-negotiable rule: only live, official postings

The previous version failed because it used web search and aggregator sites. This version must follow these rules without exception:

- **A posting may only appear in the tracker if, in today's run, it was read directly from the employer's own hiring system** (its ATS API or its own careers domain). Aggregators (Indeed, Glassdoor, iagora, Jobs in Football, Global Sports Jobs, talendo, jobleads, etc.) may never be the source or the link.
- **The link shown must be the employer's official posting/apply URL**, and the run must confirm it responds (HTTP 200, not a redirect to a "job closed"/search page) and that the page contains the job title.
- A posting that is missing from its source in **two consecutive runs** is marked `Removed` (kept in history, hidden from the default view). A posting whose URL check fails is never shown as active.
- Every source is fetched every run. If a source fails (error, 0 jobs when it usually has some, layout change), it is reported in a **Source health** section – never silently skipped.

## 3. Architecture

- Python 3.11+, package `jobradar`, CLI with `python -m jobradar run | doctor | add-source | export`.
- `sources.yaml` – one entry per organisation: name, sector (sports / wealth), segment, country, `adapter`, adapter parameters, official careers URL, notes.
- `adapters/` – one module per hiring-system type, each returning a list of normalised postings: `id, company, title, location, url, apply_url, posted_at (if available), description_text, source_adapter`.
- `filters.py` – keeps relevant roles (see §5).
- `enrich.py` – pay and languages (see §6) and scoring (see §7).
- `store/` – SQLite (or JSON) with full history: first_seen, last_seen, status, consecutive_misses.
- `report/` – builds the outputs (see §8).
- `.github/workflows/daily.yml` – runs every day at 06:30 UTC on GitHub Actions, commits the updated data, publishes the dashboard to GitHub Pages, sends the digest.
- `tests/` – unit tests for filters/enrichment and one live smoke test per adapter.

### Adapters to implement (verify every endpoint live – the URLs below are starting points, not facts)

| Adapter | Typical public endpoint to try |
|---|---|
| greenhouse | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` (EU boards: also try the `eu` variant) |
| lever | `https://api.lever.co/v0/postings/{company}?mode=json` (EU: `api.eu.lever.co`) |
| smartrecruiters | `https://api.smartrecruiters.com/v1/companies/{company}/postings` |
| workable | `https://apply.workable.com/api/v3/accounts/{account}/jobs` (POST) |
| recruitee | `https://{company}.recruitee.com/api/offers/` |
| personio | `https://{company}.jobs.personio.de/xml` (or `.com`) |
| teamtailor | the company's teamtailor jobs page / feed |
| ashby | `https://api.ashbyhq.com/posting-api/job-board/{org}` |
| workday | the site's `/wday/cxs/{tenant}/{site}/jobs` JSON endpoint (POST) |
| successfactors | SAP SuccessFactors / RMK career sites (search page or feed) |
| jobylon | UEFA / UC3 and others on emp.jobylon.com |
| html | fallback: fetch the official careers page (use Playwright for JavaScript-rendered pages), extract job links, follow them. Store a snapshot hash so changes are detectable. |

For each organisation, **discover which system it uses by visiting its official careers page** (look at the links / network requests), then add it to `sources.yaml` with the right adapter. If no machine-readable source exists, use `html` and say so in notes.

## 4. Organisations to cover (seed list – extend it)

Starting hints from earlier research (verify each): Red Bull → SmartRecruiters (`RedBull`); On Running → Greenhouse (`onrunning`); Two Circles → Workable (`twocircles`); Infront Sports & Media → Teamtailor (`infrontsportsmediaag`); UEFA/UC3 → Jobylon; Playtomic → Factorial; Sportec Solutions → Recruitee (`sportecsolutions`); DAZN → careers.dazn.com; Goldman Sachs → higher.gs.com; UBS → jobs.ubs.com (BrassRing); Barclays → search.jobs.barclays; SPORTFIVE → jobs.sportfive.com.

**Sports – leagues & federations:** UEFA, UC3, FIFA, DFL/Bundesliga International, DFB, Lega Serie A, FIGC, LaLiga, Premier League, Formula 1, ATP Tour, WTA, Premier Padel, Euroleague, IOC, IRFU, FAI.
**Sports – clubs:** FC Bayern München, Borussia Dortmund, Eintracht Frankfurt, VfB Stuttgart, TSG Hoffenheim, RB Leipzig, Bayer 04 Leverkusen, FC Red Bull Salzburg, FC Basel, Inter, AC Milan, Juventus, City Football Group, Real Madrid, FC Barcelona, Leinster Rugby, Mercedes-AMG F1, Red Bull Racing, Alpine F1.
**Sports – agencies:** SPORTFIVE, Infront, Two Circles, IMG / WME / IMG Licensing, CAA, Octagon, Wasserman, Relevent, TEAM Marketing.
**Sports – media & data:** DAZN, Sky, WBD/Eurosport, Sportradar, Stats Perform, Genius Sports, Sportec Solutions, RCS Sport.
**Sports – brands & sponsors:** adidas, PUMA, Nike (EMEA), On, Technogym, BasicNet/Kappa, Decathlon, Red Bull, HEINEKEN, AB InBev, Coca-Cola, Mastercard; betting: Flutter (Paddy Power, Betfair).
**Wealth management:** Goldman Sachs, UBS, Barclays Private Bank, J.P. Morgan Private Bank, Julius Baer, Pictet, Lombard Odier, Vontobel, EFG, LGT, Rothschild & Co, Schroders, Morgan Stanley, Citi, BNP Paribas Wealth Management (incl. BNL, BGL), Mediobanca, Intesa Sanpaolo Private Banking / Fideuram, Banca Generali, Deutsche Bank Wealth Management, Davy, Bank of Ireland, Goodbody.

## 5. Relevance filter

- Location: Europe (prioritise CH, DE, AT, LU, IT, IE, UK, MC, NL, ES, FR).
- Keep: intern, internship, praktikum, praktikant, pflichtpraktikum, werkstudent (flag separately), stage, tirocinio, trainee, graduate, analyst programme, summer analyst, off-cycle, junior, entry level, associate (entry).
- Function keywords (EN/DE/IT/FR/ES): partnership, sponsorship, commercial, sales, business development, key account, licensing, hospitality, brand, marketing, media rights, client, relationship, advisory, private bank, wealth, Partnermanagement, Sponsoring, Vertrieb, Vermarktung, commerciale, vendite, private banking, consulenza.
- Drop: senior/director/head/manager with experience requirements, pure IT/engineering, legal, HR, operations-only, US/Asia-only roles.
- Keep a "maybe" bucket for borderline roles instead of dropping them.

## 6. Enrichment

- **Pay:** if the posting states a salary/stipend, show it with "(posted)". Otherwise show an estimate from a small table by country × role type (intern / graduate / entry), labelled "(est.)". Keep the table in `pay_estimates.yaml` so it can be edited.
- **Languages:** detect required languages from the posting text (e.g. "fluent German", "Deutsch", "italiano", "français", "English") and the language the posting is written in. Show detected ones plainly; if only inferred from posting language, add "(likely)".

## 7. Scoring (1–10)

Rule-based by default (role function, sector, location priority, level, language edge – Jacopo has C1+ in Italian, English and German – and timing: he studies in Dublin Jan–May 2027, so summer/off-cycle 2027 and graduate starts from late 2027 fit best). Optional: if `ANTHROPIC_API_KEY` is set, ask Claude for a 1–10 score and a one-sentence "why it fits" using `profile.md`; fall back to rules otherwise.

## 8. Outputs

1. **Dashboard (main view):** a mobile-friendly static HTML page published on GitHub Pages, with two tabs – Sports and Wealth Management – columns: Score, Company, Role, Segment, Location, Pay, Languages, Type/Timing, Deadline, Status (New / Active / Closing soon), Why it fits, Official link, First seen, Last seen. Sort by score, filter by country/status. Plus a **Source health** tab: every source, its adapter, jobs found today, last success, errors.
2. **Daily digest:** email (Gmail SMTP with an app password stored as a GitHub secret) – or Telegram if configured – listing new postings (score, company, role, city, pay, languages, official link), postings closing within 7 days, and any failed sources.
3. **Export:** `export` writes `jobs.xlsx` and `jobs.csv` for the full history.

## 9. Personal tracking

Jacopo's own application status (Not applied / Applied / Interview / Offer / Rejected / Not interested) lives in `my_status.yaml` keyed by posting id, so the daily run never overwrites it. The dashboard shows it.

## 10. Acceptance checks (must pass before reporting done)

1. `python -m jobradar doctor` runs every source in `sources.yaml` live and prints a table: source, adapter, jobs fetched, relevant jobs, status. Every source is either OK or has a documented reason and a fallback.
2. For a random sample of 20 relevant postings, the run opens the official URL, confirms HTTP 200 and that the title appears on the page, and prints the results. 0 failures allowed.
3. No URL in the dashboard points to an aggregator domain (write a test with a blocklist).
4. Running `run` twice in a row produces no duplicates and no spurious "Removed".
5. The GitHub Actions workflow runs successfully once, the dashboard is reachable on GitHub Pages, and one digest email arrives.
6. `README.md` explains in plain language how to add a source, how to change the profile/scoring, and how to mark applications.

## 11. Working style

- Ask Jacopo before creating accounts or entering any password; he will create the GitHub account/repo and the Gmail app password himself.
- Commit in small steps with clear messages.
- When a source cannot be read reliably, say so plainly in the Source health tab instead of guessing.
