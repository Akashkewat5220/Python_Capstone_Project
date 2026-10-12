"""Scraping order, source edge cases, network failures, and all-or-nothing seeds."""

from unittest.mock import Mock

import pytest
import requests
from bs4 import BeautifulSoup

from database import CountryDatabaseManager
from scraper import SOURCE_URL, ScrapeError, fetch_html, parse_countries, seed_database


def test_first_twenty_are_selected_before_sorting_or_filtering(country_html):
    countries = parse_countries(country_html)
    expected = ["Zulu Demo", "Åland Islands", "Antarctica"] + [
        f"Demo {index:02d}" for index in range(4, 21)
    ]
    assert [country.country_name for country in countries] == expected
    assert len(countries) == 20


def test_source_values_survive_parsing(country_html):
    countries = parse_countries(country_html)
    assert countries[0].model_dump() == {
        "country_name": "Zulu Demo",
        "capital": "Demo City",
        "population": 42,
        "area": 3.5,
    }
    assert countries[1].country_name == "Åland Islands"
    assert countries[2].capital == "None"
    assert countries[2].population == 0
    assert countries[2].area == 14_000_000.0
    assert type(countries[2].population) is int
    assert type(countries[2].area) is float


@pytest.mark.parametrize(
    ("selector", "text"),
    [
        (".country-name", "   "),
        (".country-population", "12.5"),
        (".country-population", "-1"),
        (".country-population", "not a number"),
        (".country-area", "-2.0"),
        (".country-area", "nan"),
        (".country-area", "inf"),
        (".country-area", "not a number"),
    ],
)
def test_invalid_selected_record_is_not_replaced_by_later_country(country_html, selector, text):
    soup = BeautifulSoup(country_html, "html.parser")
    soup.select(".country")[19].select_one(selector).string = text
    with pytest.raises(ScrapeError, match=r".+"):
        parse_countries(str(soup))


@pytest.mark.parametrize(
    "selector",
    [".country-name", ".country-capital", ".country-population", ".country-area"],
)
def test_missing_required_element_fails(country_html, selector):
    soup = BeautifulSoup(country_html, "html.parser")
    soup.select(".country")[0].select_one(selector).decompose()
    with pytest.raises(ScrapeError, match=r".+"):
        parse_countries(str(soup))


def test_too_few_country_containers_fail(country_html):
    soup = BeautifulSoup(country_html, "html.parser")
    for country in soup.select(".country")[19:]:
        country.decompose()
    with pytest.raises(ScrapeError, match="20"):
        parse_countries(str(soup))


def test_duplicate_names_after_trimming_fail(country_html):
    soup = BeautifulSoup(country_html, "html.parser")
    soup.select(".country")[1].select_one(".country-name").string = " Zulu Demo "
    with pytest.raises(ScrapeError, match=r"[Dd]uplicate"):
        parse_countries(str(soup))


def test_fetch_checks_status_uses_finite_timeout_and_normal_tls(monkeypatch, country_html):
    response = Mock(text=country_html)
    get = Mock(return_value=response)
    monkeypatch.setattr("scraper.requests.get", get)
    assert fetch_html() == country_html
    response.raise_for_status.assert_called_once_with()
    assert get.call_args.args == (SOURCE_URL,)
    timeout = get.call_args.kwargs["timeout"]
    assert 0 < timeout < float("inf")
    assert get.call_args.kwargs.get("verify", True) is True


@pytest.mark.parametrize(
    "failure", [requests.Timeout("timed out"), requests.ConnectionError("offline")]
)
def test_fetch_connection_failures_are_clear(monkeypatch, failure):
    monkeypatch.setattr("scraper.requests.get", Mock(side_effect=failure))
    with pytest.raises(ScrapeError, match=r".+"):
        fetch_html()


def test_fetch_http_failure_is_clear(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("503 unavailable")
    monkeypatch.setattr("scraper.requests.get", Mock(return_value=response))
    with pytest.raises(ScrapeError, match=r".+"):
        fetch_html()


def test_invalid_scrape_does_not_partially_change_database(
    tmp_path, monkeypatch, country_html, sample_country
):
    path = tmp_path / "countries.db"
    manager = CountryDatabaseManager(path)
    manager.initialize_schema()
    manager.create_country(sample_country)
    soup = BeautifulSoup(country_html, "html.parser")
    soup.select(".country")[19].select_one(".country-area").string = "bad"
    monkeypatch.setattr("scraper.fetch_html", Mock(return_value=str(soup)))
    with pytest.raises(ScrapeError):
        seed_database(path)
    assert [country.model_dump() for country in manager.list_countries()] == [sample_country]


def test_fetch_failure_does_not_create_database(tmp_path, monkeypatch):
    path = tmp_path / "countries.db"
    monkeypatch.setattr("scraper.fetch_html", Mock(side_effect=ScrapeError("network unavailable")))
    with pytest.raises(ScrapeError, match="network unavailable"):
        seed_database(path)
    assert not path.exists()


def test_successful_seed_writes_complete_batch(tmp_path, monkeypatch, country_html):
    path = tmp_path / "countries.db"
    monkeypatch.setattr("scraper.fetch_html", Mock(return_value=country_html))
    selected = seed_database(path)
    actual = CountryDatabaseManager(path).list_countries()
    assert len(selected) == len(actual) == 20
    assert {country.country_name: country.model_dump() for country in actual} == {
        country.country_name: country.model_dump() for country in selected
    }
