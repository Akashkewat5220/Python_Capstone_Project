"""Fetch the practice page and atomically seed its first 20 countries."""

import argparse
import sqlite3
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pydantic import ValidationError

from database import DEFAULT_DB_PATH, CountryDatabaseManager
from schemas import Country

SOURCE_URL = "https://www.scrapethissite.com/pages/simple/"
SCRAPE_LIMIT = 20
REQUEST_TIMEOUT = 20.0


class ScrapeError(Exception):
    """The source could not be fetched or the selected batch was invalid."""


def fetch_html(url: str = SOURCE_URL, timeout: float = REQUEST_TIMEOUT) -> str:
    """Fetch HTML with a finite timeout, HTTP checks, and default TLS verification."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScrapeError(f"Could not fetch {url}: {exc}") from exc
    # The inspected source declares UTF-8; requests' fallback for text/html
    # can otherwise decode Åland incorrectly as Latin-1.
    response.encoding = "utf-8"
    return response.text


def parse_countries(html: str) -> list[Country]:
    """Validate exactly the first 20 containers in HTML document order.

    A malformed selected container fails the entire batch; later countries
    never replace it. This function performs no network or database access.
    """
    containers = BeautifulSoup(html, "html.parser").select(".country")
    if len(containers) < SCRAPE_LIMIT:
        raise ScrapeError(
            f"Expected at least {SCRAPE_LIMIT} country containers; found {len(containers)}."
        )
    selected = containers[:SCRAPE_LIMIT]
    countries: list[Country] = []
    seen: set[str] = set()
    for position, container in enumerate(selected, start=1):
        fields: dict[str, str] = {}
        for field in ("country_name", "capital", "population", "area"):
            selector = ".country-name" if field == "country_name" else f".country-{field}"
            element = container.select_one(selector)
            if element is None:
                raise ScrapeError(f"Selected country #{position} is missing {field}.")
            fields[field] = element.get_text().strip()
        try:
            country = Country(
                country_name=fields["country_name"],
                capital=fields["capital"],
                population=int(fields["population"]),
                area=float(fields["area"]),
            )
        except (ValueError, OverflowError, ValidationError) as exc:
            raise ScrapeError(f"Selected country #{position} has invalid data: {exc}") from exc
        if country.country_name in seen:
            raise ScrapeError(f"Duplicate selected country name: {country.country_name!r}.")
        seen.add(country.country_name)
        countries.append(country)
    return countries


def seed_database(db_path: str | Path = DEFAULT_DB_PATH, url: str = SOURCE_URL) -> list[Country]:
    """Validate the whole live batch before any writes, then upsert atomically.

    Matching names are refreshed, missing names are inserted, and unrelated
    manually created countries are preserved. Return the records in source order.
    """
    countries = parse_countries(fetch_html(url))
    manager = CountryDatabaseManager(db_path)
    manager.initialize_schema()
    manager.upsert_seed(countries)
    return countries


def main() -> None:
    """Run explicit live scraping; importing this module never fetches data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path")
    args = parser.parse_args()
    try:
        countries = seed_database(args.db)
    except (ScrapeError, sqlite3.Error, OSError) as exc:
        parser.exit(1, f"Scrape/seed failed: {exc}\n")
    print(f"Seeded {len(countries)} source records into {args.db.resolve()}")
    print("First 20 source names: " + ", ".join(country.country_name for country in countries))


if __name__ == "__main__":
    main()
