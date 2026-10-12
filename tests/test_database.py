"""Database behavior is verified through public methods and fresh connections."""

import sqlite3

import pytest
from pydantic import ValidationError

from database import (
    CountryDatabaseManager,
    CountryNotFoundError,
    DuplicateCountryError,
)


@pytest.fixture
def manager(tmp_path):
    database = CountryDatabaseManager(tmp_path / "countries.db")
    database.initialize_schema()
    return database


def test_schema_uses_name_as_natural_primary_key(tmp_path):
    path = tmp_path / "countries.db"
    manager = CountryDatabaseManager(path)
    manager.initialize_schema()
    manager.initialize_schema()
    with sqlite3.connect(path) as connection:
        columns = connection.execute("PRAGMA table_info(countries)").fetchall()
        by_name = {column[1]: column for column in columns}
        assert list(by_name) == ["country_name", "capital", "population", "area"]
        assert by_name["country_name"][2:] == ("TEXT", 1, None, 1)
        assert by_name["capital"][2] == "TEXT"
        assert by_name["population"][2] == "INTEGER"
        assert by_name["area"][2] == "REAL"
        for column in columns:
            assert column[3] == 1
        for population, area in [(-1, 1.0), (1, -1.0)]:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO countries VALUES (?, ?, ?, ?)",
                    ("Negative Demo", "Demo City", population, area),
                )


def test_crud_changes_persist_across_new_connections(tmp_path, sample_country):
    path = tmp_path / "countries.db"
    manager = CountryDatabaseManager(path)
    manager.initialize_schema()
    assert manager.list_countries() == []
    assert manager.create_country(sample_country).model_dump() == sample_country
    fresh_manager = CountryDatabaseManager(path)
    assert fresh_manager.get_country(sample_country["country_name"]).model_dump() == (
        sample_country
    )
    replacement = {"capital": "Replacement City", "population": 0, "area": 0.0}
    changed = fresh_manager.update_country(sample_country["country_name"], replacement)
    assert changed.model_dump() == {
        "country_name": sample_country["country_name"],
        **replacement,
    }
    assert manager.get_country(sample_country["country_name"]) == changed
    fresh_manager.delete_country(sample_country["country_name"])
    assert CountryDatabaseManager(path).list_countries() == []


def test_trimmed_duplicate_rejected_but_case_is_significant(manager, sample_country):
    manager.create_country(sample_country)
    duplicate = {**sample_country, "country_name": " Student Demo Country "}
    with pytest.raises(DuplicateCountryError):
        manager.create_country(duplicate)
    different_case = {**sample_country, "country_name": "student demo country"}
    manager.create_country(different_case)
    assert len(manager.list_countries()) == 2
    assert manager.get_country(" Student Demo Country ").country_name == ("Student Demo Country")


def test_parameterized_values_preserve_apostrophes_and_unicode(manager, sample_country):
    name = "Åland O'Brien'); DROP TABLE countries; --"
    country = {
        **sample_country,
        "country_name": name,
        "capital": "  Île d'O'Brien  ",
    }
    manager.create_country(country)
    assert manager.get_country(name).capital == "Île d'O'Brien"
    assert len(manager.list_countries()) == 1
    manager.delete_country(name)
    assert manager.list_countries() == []


def test_list_order_is_deterministic_binary_name_order(manager, sample_country):
    names = ["zulu", "Åland", "Alpha", "alpha", "Bravo"]
    for name in names:
        manager.create_country({**sample_country, "country_name": name})
    expected = sorted(names)
    assert [country.country_name for country in manager.list_countries()] == expected
    assert [country.country_name for country in manager.list_countries()] == expected


def test_missing_records_raise_domain_error(manager):
    with pytest.raises(CountryNotFoundError):
        manager.get_country("Missing")
    with pytest.raises(CountryNotFoundError):
        manager.update_country("Missing", {"capital": "", "population": 0, "area": 0})
    with pytest.raises(CountryNotFoundError):
        manager.delete_country("Missing")


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("country_name", "  "),
        ("capital", None),
        ("population", -1),
        ("population", 1.5),
        ("population", True),
        ("population", "1"),
        ("population", 2**63),
        ("area", -1.0),
        ("area", True),
        ("area", "1.5"),
        ("area", float("inf")),
        ("area", float("nan")),
    ],
)
def test_database_boundaries_reject_invalid_records(manager, sample_country, field, invalid):
    with pytest.raises(ValidationError):
        manager.create_country({**sample_country, field: invalid})
    assert manager.list_countries() == []


def test_repeated_seed_updates_matches_preserves_manual_rows(manager, sample_country):
    manual = {**sample_country, "country_name": "Manual Country"}
    scraped = [{**sample_country, "country_name": f"Scraped {index:02d}"} for index in range(20)]
    manager.create_country(manual)
    assert manager.upsert_seed(scraped) == 20
    refreshed = [{**country, "population": index} for index, country in enumerate(scraped)]
    assert manager.upsert_seed(refreshed) == 20
    assert len(manager.list_countries()) == 21
    assert manager.get_country("Manual Country").model_dump() == manual
    assert manager.get_country("Scraped 19").population == 19
    assert manager.get_country("Scraped 00").population == 0
    manager.create_country({**sample_country, "country_name": "Additional Country"})
    assert len(manager.list_countries()) == 22


def test_full_seed_batch_validated_before_any_write(manager, sample_country):
    manager.create_country(sample_country)
    seed = [
        {**sample_country, "population": 999},
        {**sample_country, "country_name": "Invalid Final Row", "population": -1},
    ]
    with pytest.raises(ValidationError):
        manager.upsert_seed(seed)
    assert [country.model_dump() for country in manager.list_countries()] == [sample_country]


def test_duplicate_seed_names_reject_entire_batch(manager, sample_country):
    duplicate = {**sample_country, "country_name": " Student Demo Country "}
    with pytest.raises(DuplicateCountryError):
        manager.upsert_seed([sample_country, duplicate])
    assert manager.list_countries() == []


def test_seed_transaction_rolls_back_if_sqlite_rejects_later_record(tmp_path, sample_country):
    path = tmp_path / "countries.db"
    manager = CountryDatabaseManager(path)
    manager.initialize_schema()
    manager.create_country(sample_country)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TRIGGER reject_test_row BEFORE INSERT ON countries
               WHEN NEW.country_name = 'Rejected Demo'
               BEGIN SELECT RAISE(ABORT, 'test transaction failure'); END"""
        )
    batch = [
        {**sample_country, "population": 999},
        {**sample_country, "country_name": "Rejected Demo"},
    ]
    with pytest.raises(sqlite3.DatabaseError, match="test transaction failure"):
        manager.upsert_seed(batch)
    assert [country.model_dump() for country in manager.list_countries()] == [sample_country]
