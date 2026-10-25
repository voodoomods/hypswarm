from importer import import_rows


def test_three_rows():
    assert len(import_rows("fixtures/quoted.csv")) == 3


def test_quoted_comma_is_kept():
    rows = import_rows("fixtures/quoted.csv")
    assert rows[1]["name"] == "Doe, Jane"


def test_columns():
    assert list(import_rows("fixtures/quoted.csv")[0]) == ["id", "name", "city"]
