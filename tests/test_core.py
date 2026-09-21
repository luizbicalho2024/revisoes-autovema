from src.importer import clean_chassis, clean_digits, clean_plate
from src.journey import loyalty_level_from_revisions


def test_normalization():
    assert clean_digits("005.456.202-36") == "00545620236"
    assert clean_chassis("9bd-123 abc") == "9BD123ABC"
    assert clean_plate("NEB2575-RO") == "NEB2575"


def test_loyalty_progression():
    bonuses = {3: 1.0, 4: 2.0, 5: 3.0}
    revisions = [{"revision_number": i, "status": "realizada"} for i in range(1, 4)]
    level, bonus, cancelled, reason = loyalty_level_from_revisions(revisions, bonuses)
    assert level == 3
    assert bonus == 1.0
    assert cancelled is False
    assert reason is None


def test_loyalty_cancels_on_external_revision():
    bonuses = {3: 1.0, 4: 2.0, 5: 3.0}
    revisions = [
        {"revision_number": 1, "status": "realizada"},
        {"revision_number": 2, "status": "externa_perdida"},
    ]
    level, bonus, cancelled, reason = loyalty_level_from_revisions(revisions, bonuses)
    assert level == 0
    assert bonus == 0.0
    assert cancelled is True
    assert reason
