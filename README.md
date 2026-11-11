# Job Radar

A daily tracker of **official** internship, graduate and entry-level job postings in two sectors:

1. **Sports business** – partnerships, sponsorship, commercial, sales, licensing, hospitality, marketing roles at clubs, leagues, federations, agencies, sports media/data companies, sports brands and sponsor brands.
2. **Wealth management / private banking** – client-facing, advisory, business-management and graduate roles.

Every posting is read **directly from the employer's own hiring system** (its ATS API or its own careers site) on the day it is shown. No job boards or aggregators are ever used, and every link shown is checked live (HTTP 200 and the job title must appear on the official page).

- Dashboard (GitHub Pages): `https://<your-github-user>.github.io/<repo>/` – tabs *Sports*, *Wealth Management*, *Source health*.
- Daily digest by e-mail (Gmail) and/or Telegram at ~06:30 UTC.
- Full history in `data/jobradar.db` (SQLite), exported to `jobs.xlsx` / `jobs.csv`.

---

## How it works (in one paragraph)

`sources.yaml` lists ~90 organisations and, for each, which hiring system it uses (Greenhouse, SmartRecruiters, Workday, SuccessFactors, Teamtailor, Personio, Oracle, Pinpoint, …). Every morning GitHub Actions runs `python -m jobradar run`: it fetches **every** source, keeps the relevant roles (filters in `jobradar/filters.py`), adds pay / languages / timing / a 1–10 score (`jobradar/enrich.py`), opens each official link to confirm it is live, updates the history (a posting missing from its source on **two consecutive runs** becomes *Removed*), builds the dashboard and sends the digest. Sources that fail, return 0 jobs when they normally have some, or change layout are listed in the **Source health** tab and in the digest – never silently skipped.

## Commands

```bash
pip install -r requirements.txt
python -m playwright install chromium          # headless browser for JavaScript career sites

python -m jobradar run          # full daily run (fetch, filter, verify, dashboard, digest)
python -m jobradar doctor       # test every source live and print a health table (writes nothing)
python -m jobradar verify --sample 20   # re-open 20 random relevant postings and check them live
python -m jobradar export       # jobs.xlsx + jobs.csv with the full history
python -m jobradar add-source "Company" --sector sports --careers-url https://company.com/careers
python -m jobradar dashboard    # rebuild site/index.html from the database
python -m pytest                # unit tests;  python -m pytest -m live   → one live test per adapter
```

---

## How to add a source

**Easy way:** let the tool detect the hiring system for you:

```bash
python -m jobradar add-source "Hertha BSC" --sector sports --careers-url https://www.herthabsc.com/de/karriere --country DE --segment Club
```

It opens the official careers page in a headless browser, looks at the links and network requests (Greenhouse, Lever, SmartRecruiters, Workable, Ashby, Personio, Recruitee, Teamtailor, Workday, Oracle, Pinpoint, Eightfold, SuccessFactors, softgarden, Jobylon, Phenom …), fetches the jobs once to prove it works, and appends an entry to `sources.yaml`. If nothing machine-readable is found it falls back to the `html` adapter and says so in `notes` – check its `link_pattern`.

**By hand:** add a block to `sources.yaml`, e.g.

```yaml
- name: Example FC
  sector: sports            # sports | wealth
  segment: Club             # free text shown in the dashboard
  country: DE               # HQ country (used when a posting has no location)
  adapter: greenhouse       # see the table below
  careers_url: https://www.example-fc.com/careers
  params: {token: examplefc}
  notes: why / how this source was chosen
```

| adapter | params |
|---|---|
| greenhouse | `token` (board name in `boards.greenhouse.io/<token>`) |
| lever | `company` |
| smartrecruiters | `company` (e.g. `RedBull`), optional `country` (`at`) |
| workable | `account` |
| recruitee | `company` or `base_url` |
| personio | `company`, `tld` (de/com) |
| teamtailor | `company` or `base_url` (custom domain) |
| ashby | `org` |
| workday | `host`, `tenant`, `site` (from `https://<host>/<lang>/<site>`), optional `facet_filter` |
| successfactors | `mode: rmk` + `base_url` · `mode: classic` + `host` + `company` · `mode: feed` + `feed_url` |
| oracle | `host` (`xxx.fa.oraclecloud.com`), `site` (`CX_1`) – Europe only by default |
| pinpoint | `company` |
| jobylon | `list_urls` (official page that links to emp.jobylon.com) |
| phenom, eightfold, gs, beesite, brassring, hibob, softgarden, digitalrecruiters | see the module docstring in `jobradar/adapters/` |
| html | `list_urls`, `link_pattern` (regex for job links), optional `render: true` for JavaScript pages |

Then run `python -m jobradar doctor --only "Example FC"` to test it. Set `enabled: false` (with a reason in `notes`) to keep a source documented but not fetched.

Aggregators can never be added: their domains are blocked in `jobradar/config.py` (`AGGREGATOR_DOMAINS`) and a test fails if one ever reaches the dashboard.

---

## How to change the profile and the scoring

- **Profile** – `profile.md`. It is used for the optional Claude score (see below) and documents the rules.
- **Which roles are kept** – `jobradar/filters.py`: keyword lists for level (intern, Praktikum, graduate, …), function (partnership, sponsorship, sales, private banking, …), and things to drop (senior, IT, legal, HR, store jobs, …). Borderline roles go into the *maybe* bucket instead of being dropped.
- **Rule-based score (1–10)** – `rule_score()` in `jobradar/enrich.py`. Points for: a core commercial/partnership (or private-banking/client) function, location tier (CH/DE/AT/LU/Milan > IE/UK/MC/NL > rest of Europe), level (internship/graduate), German or Italian requirement (your edge), timing (summer 2027 / off-cycle from mid-2027 / graduate 2027-28 = good; starts Jan–May 2027 = clash with Dublin). Change the numbers there.
- **Pay estimates** – `pay_estimates.yaml` (country × intern / graduate / entry). Posted salaries always win and are labelled "(posted)"; estimates are labelled "(est.)".
- **Optional Claude score** – add a repository secret `ANTHROPIC_API_KEY`. New relevant postings then get a 1–10 score and a one-sentence "why it fits" from Claude using `profile.md`; without the key the rules are used.

## How to mark your applications

Edit `my_status.yaml` (in GitHub you can do this in the browser: open the file → pencil icon → commit). Use the posting id shown in the dashboard's *My status* column:

```yaml
applications:
  "red-bull:744000099999999": {status: Applied, note: "applied 12 Nov"}
  "uefa:396274": Interview
```

Allowed statuses: `Not applied`, `Applied`, `Interview`, `Offer`, `Rejected`, `Not interested`. The daily run never writes to this file; the dashboard shows the status and lets you filter by it.

---

## One-time setup on GitHub (done by you – no passwords are ever stored in the code)

1. Push this repository to GitHub.
2. **Settings → Pages → Source: GitHub Actions.**
3. **Settings → Secrets and variables → Actions → New repository secret:**
   - `GMAIL_USER` – the Gmail address that sends the digest
   - `GMAIL_APP_PASSWORD` – a Gmail *app password* (Google Account → Security → 2-Step Verification → App passwords)
   - `DIGEST_TO` – where the digest goes (optional, defaults to `GMAIL_USER`; comma-separate several)
   - optional: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`
4. **Actions → "Job Radar daily run" → Run workflow** once. After that it runs every day at 06:30 UTC.

The workflow lives in `.github/workflows/daily.yml`. Scheduled workflows only run from the default branch, so merge to `main` first.

## Files

```
jobradar/            package (adapters/, filters.py, enrich.py, verify.py, pipeline.py, store/, report/)
sources.yaml         organisations and their hiring systems
profile.md           your profile (filtering/scoring notes, Claude prompt)
pay_estimates.yaml   pay estimate table
my_status.yaml       your application tracking (never overwritten)
data/jobradar.db     full history (committed by the workflow)
site/                generated dashboard (published to GitHub Pages)
out/                 generated digest (digest.html / digest.txt)
tests/               unit tests + live adapter smoke tests
```
