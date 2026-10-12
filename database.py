"""SQLite persistence with one short-lived connection per database operation."""

import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from schemas import Country, CountryDetails, normalize_country_name

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "countries.db"


class DuplicateCountryError(Exception):
    """Raised when ordinary creation tries to reuse a normalized country name."""


class CountryNotFoundError(Exception):
    """Raised when reading, updating, or deleting a missing country."""


class CountryDatabaseManager:
    """Own the schema and CRUD operations, rather than an always-open connection.

    Inputs are validated Country/CountryDetails objects or equivalent mappings.
    Every method opens and closes its own connection. Writes use one explicit
    transaction, so a successful return means the change has been committed.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path).expanduser().resolve()

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except Exception:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def initialize_schema(self) -> None:
        """Create the countries table if missing; never fetch or seed source data."""
        with self._connection(write=True) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS countries (
                    country_name TEXT NOT NULL PRIMARY KEY
                        CHECK (length(trim(country_name)) > 0),
                    capital TEXT NOT NULL,
                    population INTEGER NOT NULL
                        CHECK (typeof(population) = 'integer' AND population >= 0),
                    area REAL NOT NULL
                        CHECK (area >= 0 AND area <= 1.7976931348623157e308)
                )
                """
            )

    @staticmethod
    def _validate_country(country: Country | Mapping[str, Any]) -> Country:
        # Revalidate existing models too: callers may have used model_construct().
        values = country.model_dump() if isinstance(country, Country) else country
        return Country.model_validate(values)

    @staticmethod
    def _validate_details(details: CountryDetails | Mapping[str, Any]) -> CountryDetails:
        values = details.model_dump() if isinstance(details, CountryDetails) else details
        return CountryDetails.model_validate(values)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Country:
        return Country.model_validate(dict(row))

    def create_country(self, country: Country | Mapping[str, Any]) -> Country:
        """Insert and return a record; raise DuplicateCountryError if its key exists."""
        record = self._validate_country(country)
        with self._connection(write=True) as connection:
            try:
                connection.execute(
                    """INSERT INTO countries (country_name, capital, population, area)
                       VALUES (?, ?, ?, ?)""",
                    (
                        record.country_name,
                        record.capital,
                        record.population,
                        record.area,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if exc.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY:
                    raise DuplicateCountryError(record.country_name) from exc
                raise
        return record

    def list_countries(self) -> list[Country]:
        """Return all records sorted by name using SQLite's case-sensitive BINARY order."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT country_name, capital, population, area
                   FROM countries ORDER BY country_name COLLATE BINARY"""
            ).fetchall()
            return [self._from_row(row) for row in rows]

    def get_country(self, name: str) -> Country:
        """Return one normalized-name match; raise CountryNotFoundError if missing."""
        country_name = normalize_country_name(name)
        with self._connection() as connection:
            row = connection.execute(
                """SELECT country_name, capital, population, area
                   FROM countries WHERE country_name = ?""",
                (country_name,),
            ).fetchone()
            if row is None:
                raise CountryNotFoundError(country_name)
            return self._from_row(row)

    def update_country(self, name: str, details: CountryDetails | Mapping[str, Any]) -> Country:
        """Replace all three details, retaining the key; raise if the key is missing."""
        country_name = normalize_country_name(name)
        replacement = self._validate_details(details)
        with self._connection(write=True) as connection:
            cursor = connection.execute(
                """UPDATE countries SET capital = ?, population = ?, area = ?
                   WHERE country_name = ?""",
                (
                    replacement.capital,
                    replacement.population,
                    replacement.area,
                    country_name,
                ),
            )
            if cursor.rowcount == 0:
                raise CountryNotFoundError(country_name)
        return Country(country_name=country_name, **replacement.model_dump())

    def delete_country(self, name: str) -> None:
        """Delete one normalized-name match; raise CountryNotFoundError if missing."""
        country_name = normalize_country_name(name)
        with self._connection(write=True) as connection:
            cursor = connection.execute(
                "DELETE FROM countries WHERE country_name = ?", (country_name,)
            )
            if cursor.rowcount == 0:
                raise CountryNotFoundError(country_name)

    def upsert_seed(self, countries: Iterable[Country | Mapping[str, Any]]) -> int:
        """Validate a full batch, then insert/refresh it atomically and return its size.

        Duplicate normalized names in one batch raise DuplicateCountryError before
        writing. Existing scraped names are refreshed; unrelated records remain.
        The scraper, rather than the database, enforces its 20-country limit.
        """
        records = [self._validate_country(country) for country in countries]
        seen: set[str] = set()
        for record in records:
            if record.country_name in seen:
                raise DuplicateCountryError(record.country_name)
            seen.add(record.country_name)

        with self._connection(write=True) as connection:
            connection.executemany(
                """INSERT INTO countries (country_name, capital, population, area)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(country_name) DO UPDATE SET
                       capital = excluded.capital,
                       population = excluded.population,
                       area = excluded.area""",
                [
                    (
                        record.country_name,
                        record.capital,
                        record.population,
                        record.area,
                    )
                    for record in records
                ],
            )
        return len(records)
