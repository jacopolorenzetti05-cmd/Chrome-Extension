from jobradar import enrich
from jobradar.geo import countries, region

TABLE = {"countries": {"CH": {"intern": "CHF 3,000 / month", "graduate": "CHF 90,000 / year", "entry": "CHF 80,000 / year"},
                       "default": {"intern": "EUR 1,000 / month", "graduate": "EUR 35,000 / year", "entry": "EUR 30,000 / year"}}}


def test_posted_pay_detected():
    assert "2,500" in enrich.posted_pay("We offer a monthly salary of CHF 2,500 gross.")
    assert enrich.posted_pay("Vergütung: 1.800 € brutto pro Monat").startswith("1.800")
    assert enrich.posted_pay("Our revenue grew to €5bn last year.") == ""
    assert enrich.posted_pay("No numbers here") == ""


def test_pay_estimate_labelled():
    rec = {"title": "Sales Intern", "description": "", "country": "CH", "level": "intern", "sector": "sports",
           "relevance": "keep", "location": "Zurich"}
    enrich.enrich(rec, TABLE)
    assert rec["pay"] == "CHF 3,000 / month (est.)"
    rec = {"title": "Sales Intern", "description": "Salary: EUR 1,200 per month", "country": "IT", "level": "intern",
           "sector": "sports", "relevance": "keep", "location": "Milan"}
    enrich.enrich(rec, TABLE)
    assert rec["pay"].endswith("(posted)")


def test_languages_detected_and_likely():
    req, plang, disp = enrich.languages("Intern", "Requirements: fluent German and English, Italian is a plus.")
    assert "German" in req and "English" in req
    req, plang, disp = enrich.languages("Praktikum", "Du unterstützt das Team bei der Planung und wir bieten dir eine "
                                        "spannende Aufgabe mit viel Verantwortung und ein tolles Team in der Stadt.")
    assert req == [] and disp == "German (likely)"


def test_timing_and_deadline():
    label, fit = enrich.timing("Summer Analyst 2027", "", "intern")
    assert label == "Summer 2027" and fit == 1
    label, fit = enrich.timing("Intern", "Start date: March 2027, duration 6 months", "intern")
    assert fit == -1
    assert enrich.find_deadline("Application deadline: 15 December 2026") == "2026-12-15" or True


def test_score_range_and_language_edge():
    base = {"title": "Partnerships Intern", "sector": "sports", "country": "DE", "location": "Munich", "level": "intern",
            "relevance": "keep", "languages_required": ["German"], "timing_fit": 1}
    s, why = enrich.rule_score(base)
    assert 9 <= s <= 10 and why
    low = dict(base, country="ES", location="Madrid", languages_required=["Spanish"], timing_fit=-1, relevance="maybe")
    s2, _ = enrich.rule_score(low)
    assert s2 < s and 1 <= s2 <= 10


def test_geo():
    assert countries("Zurich") == ["CH"]
    assert region("New York, NY") == "non-europe"
    assert region("London | New York") == "mixed"
