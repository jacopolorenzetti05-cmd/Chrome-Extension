from jobradar.filters import classify


def rel(title, loc="Zurich, Switzerland", desc="", sector="sports", **src):
    return classify(title, loc, desc, sector, src).relevance


def test_keeps_sports_internships():
    assert rel("Intern Partnerships & Sponsorship", "London, UK") == "keep"
    assert rel("Praktikant (m/w/d) Sponsoring und Vermarktung", "München") == "keep"
    assert rel("Pflichtpraktikum Vertrieb", "Hamburg, Germany") == "keep"
    assert rel("Stage Marketing commerciale", "Milano") == "keep"
    assert rel("Graduate Programme – Commercial", "Dublin, Ireland") == "keep"
    assert rel("Media Rights and Broadcaster Services Intern", "Nyon") == "keep"


def test_working_student_is_kept_and_flagged():
    v = classify("Werkstudent (m/w/d) Partnermanagement", "Leipzig", "", "sports", {})
    assert v.relevance == "keep" and v.level == "working_student"


def test_drops_senior_and_non_target():
    assert rel("Head of Partnerships") == "drop"
    assert rel("Senior Sponsorship Manager") == "drop"
    assert rel("Director, Commercial") == "drop"
    assert rel("Backend Developer (m/f/d)", "Aachen") == "drop"
    assert rel("Legal Counsel") == "drop"
    assert rel("HR Business Partner") == "drop"
    assert rel("Sales Associate – Store Munich", "Munich") == "drop"


def test_drops_outside_europe():
    assert rel("Sales Intern", "New York, NY") == "drop"
    assert rel("Partnerships Intern", "Singapore") == "drop"


def test_manager_with_experience_is_dropped_but_without_is_maybe():
    long_exp = "You bring 5+ years of experience in sponsorship sales."
    assert rel("Partnership Manager", "London, UK", long_exp) == "drop"
    assert rel("Partnership Manager", "London, UK", "Great opportunity.") == "maybe"


def test_maybe_bucket_for_borderline():
    assert rel("Intern Finance", "Zurich") in ("maybe", "drop")
    assert rel("Partnerships Executive", "London, UK") == "maybe"


def test_wealth_rules():
    assert rel("Intern Private Banking", "Geneva", sector="wealth") == "keep"
    assert rel("Graduate Programme – Wealth Management", "London", sector="wealth") == "keep"
    assert rel("Assistant Relationship Manager", "Zurich", sector="wealth") == "keep"
    # big universal banks: only the wealth arm counts
    assert rel("Summer Analyst – Investment Banking", "London", sector="wealth", wealth_arm_only=True) in ("maybe", "drop")
    assert rel("Summer Analyst – Private Bank", "London", sector="wealth", wealth_arm_only=True) == "keep"


def test_unpaid_is_dropped():
    assert rel("Marketing Intern", "Milan", "This is an unpaid internship.") == "drop"


def test_unknown_location_falls_back_to_source_country():
    v = classify("Sponsorship Intern", "", "", "sports", {"country": "CH"})
    assert v.relevance == "keep" and v.country == "CH"
