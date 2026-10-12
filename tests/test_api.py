"""HTTP contracts use HTTPX's ASGI transport with an explicit app lifespan."""

import json
import sqlite3
from urllib.parse import quote

import httpx
import pytest

from api import create_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def api_app(tmp_path):
    return create_app(tmp_path / "countries.db")


@pytest.fixture
async def api_client(api_app):
    # ASGITransport sends HTTP requests in-process but does not run startup itself.
    async with api_app.router.lifespan_context(api_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_app), base_url="http://testserver"
        ) as client:
            yield client


async def test_all_five_endpoints_and_full_crud_cycle(api_client, sample_country):
    assert (await api_client.get("/countries")).status_code == 200
    assert (await api_client.get("/countries")).json() == []
    created = await api_client.post("/countries", json=sample_country)
    assert created.status_code == 201
    assert created.json() == sample_country
    path = "/countries/" + quote(sample_country["country_name"], safe="")
    retrieved = await api_client.get(path)
    assert retrieved.status_code == 200
    assert retrieved.json() == sample_country
    listed = await api_client.get("/countries")
    assert listed.status_code == 200
    assert listed.json() == [sample_country]
    details = {"capital": "Replacement City", "population": 0, "area": 0.5}
    updated = await api_client.put(path, json=details)
    assert updated.status_code == 200
    assert updated.json() == {"country_name": sample_country["country_name"], **details}
    assert (await api_client.get(path)).json() == updated.json()
    deleted = await api_client.delete(path)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert (await api_client.get("/countries")).json() == []


async def test_missing_names_return_404_for_read_update_and_delete(api_client):
    path = "/countries/Missing%20Demo"
    assert (await api_client.get(path)).status_code == 404
    assert (
        await api_client.put(path, json={"capital": "", "population": 0, "area": 0})
    ).status_code == 404
    assert (await api_client.delete(path)).status_code == 404


async def test_creation_trims_strings_and_rejects_duplicate_normalized_name(
    api_client, sample_country
):
    payload = {
        **sample_country,
        "country_name": "  Student Demo Country  ",
        "capital": " Demo City ",
    }
    first = await api_client.post("/countries", json=payload)
    assert first.status_code == 201
    assert first.json() == sample_country
    duplicate = await api_client.post("/countries", json=sample_country)
    assert duplicate.status_code == 409
    assert (await api_client.get("/countries")).json() == [sample_country]


@pytest.mark.parametrize("name", ["Åland O'Brien Demo", "Åland O'Brien / Demo"])
async def test_url_encoded_spaces_unicode_apostrophes_and_slashes(api_client, sample_country, name):
    payload = {**sample_country, "country_name": name, "capital": "None"}
    assert (await api_client.post("/countries", json=payload)).status_code == 201
    path = "/countries/" + quote(name, safe="")
    assert "%C3%85" in path and "%20" in path and "%27" in path
    if "/" in name:
        assert "%2F" in path
    assert (await api_client.get(path)).json() == payload
    assert (await api_client.get("/countries/" + quote(name.lower(), safe=""))).status_code == 404
    details = {"capital": "Mariehamn", "population": 0, "area": 14_000_000.0}
    assert (await api_client.put(path, json=details)).status_code == 200
    assert (await api_client.get(path)).json() == {"country_name": name, **details}
    assert (await api_client.delete(path)).status_code == 204
    assert (await api_client.get(path)).status_code == 404


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("country_name", "  "),
        ("country_name", None),
        ("capital", None),
        ("capital", 42),
        ("population", -1),
        ("population", 1.5),
        ("population", True),
        ("population", "1234"),
        ("population", 2**63),
        ("area", -1.0),
        ("area", True),
        ("area", "56.75"),
        ("area", float("nan")),
        ("area", float("inf")),
        ("area", -float("inf")),
    ],
)
async def test_post_invalid_body_returns_422_without_writing(
    api_client, sample_country, field, invalid
):
    # Raw JSON also checks the parser's handling of nonfinite numeric tokens.
    response = await api_client.post(
        "/countries",
        content=json.dumps({**sample_country, field: invalid}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert (await api_client.get("/countries")).json() == []


async def test_post_rejects_missing_and_unexpected_fields(api_client, sample_country):
    missing = {key: value for key, value in sample_country.items() if key != "capital"}
    assert (await api_client.post("/countries", json=missing)).status_code == 422
    assert (
        await api_client.post("/countries", json={**sample_country, "id": 1})
    ).status_code == 422


@pytest.mark.parametrize(
    "details",
    [
        {"capital": "Only one field"},
        {"capital": "Demo", "population": 1, "area": 2, "country_name": "Renamed"},
        {"capital": "Demo", "population": -1, "area": 2},
        {"capital": "Demo", "population": 1.5, "area": 2},
        {"capital": "Demo", "population": True, "area": 2},
        {"capital": "Demo", "population": 1, "area": True},
        {"capital": "Demo", "population": 1, "area": -2},
    ],
)
async def test_put_requires_complete_valid_details_and_immutable_name(
    api_client, sample_country, details
):
    await api_client.post("/countries", json=sample_country)
    path = "/countries/" + quote(sample_country["country_name"], safe="")
    assert (await api_client.put(path, json=details)).status_code == 422
    assert (await api_client.get(path)).json() == sample_country


async def test_sqlite_failure_is_500_and_does_not_expose_internals(
    api_client, api_app, monkeypatch, caplog
):
    def fail():
        raise sqlite3.OperationalError("private database path /secret/countries.db")

    monkeypatch.setattr(api_app.state.database, "list_countries", fail)
    response = await api_client.get("/countries")
    assert response.status_code == 500
    assert "/secret" not in response.text
    assert "private database path" not in response.text
    assert caplog.records


async def test_swagger_and_openapi_describe_required_endpoints(api_client):
    assert (await api_client.get("/docs")).status_code == 200
    specification = (await api_client.get("/openapi.json")).json()
    assert {"get", "post"}.issubset(specification["paths"]["/countries"])
    assert {"get", "put", "delete"}.issubset(specification["paths"]["/countries/{country_name}"])
    for path, methods in specification["paths"].items():
        for method in methods.values():
            assert method.get("description"), path
