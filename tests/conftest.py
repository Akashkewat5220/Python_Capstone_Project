"""Shared offline inputs; ordinary tests never require the live website."""

from pathlib import Path

import pytest


@pytest.fixture
def country_html() -> str:
    return (Path(__file__).parent / "fixtures" / "countries.html").read_text(encoding="utf-8")


@pytest.fixture
def sample_country() -> dict:
    return {
        "country_name": "Student Demo Country",
        "capital": "Demo City",
        "population": 1234,
        "area": 56.75,
    }
