"""Client HTTP validation, complete exports, and the plotted X/Y data contract."""

import csv
from unittest.mock import Mock

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd
import pytest
import requests
from matplotlib.axes import Axes

from client import (
    ClientError,
    build_dataframe,
    export_csv,
    fetch_countries,
    run_client,
    save_scatter_plot,
)
from schemas import Country

COLUMNS = ["country_name", "capital", "population", "area"]


@pytest.fixture
def country_records(sample_country):
    return [
        Country.model_validate({**sample_country, "country_name": "Åland Islands"}),
        Country.model_validate(
            {
                "country_name": "Antarctica",
                "capital": "None",
                "population": 0,
                "area": 14_000_000.0,
            }
        ),
        Country.model_validate({**sample_country, "country_name": "O'Brien Demo"}),
    ]


def test_fetch_uses_http_override_timeout_and_validates_records(monkeypatch, country_records):
    payload = [country.model_dump() for country in country_records]
    response = Mock()
    response.json.return_value = payload
    get = Mock(return_value=response)
    monkeypatch.setattr("client.requests.get", get)
    countries = fetch_countries("http://localhost:8765/", timeout=3.5)
    assert countries == country_records
    get.assert_called_once_with("http://localhost:8765/countries", timeout=3.5)
    response.raise_for_status.assert_called_once_with()


@pytest.mark.parametrize(
    "failure", [requests.ConnectionError("refused"), requests.Timeout("timed out")]
)
def test_fetch_connection_errors_are_clear(monkeypatch, failure):
    monkeypatch.setattr("client.requests.get", Mock(side_effect=failure))
    with pytest.raises(ClientError, match=r".+"):
        fetch_countries()


def test_fetch_http_error_is_clear(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("500 server error")
    monkeypatch.setattr("client.requests.get", Mock(return_value=response))
    with pytest.raises(ClientError, match=r".+"):
        fetch_countries()


def test_invalid_json_is_a_client_error(monkeypatch):
    response = Mock()
    response.json.side_effect = ValueError("bad JSON")
    monkeypatch.setattr("client.requests.get", Mock(return_value=response))
    with pytest.raises(ClientError, match=r"[Jj][Ss][Oo][Nn]"):
        fetch_countries()


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"countries": []}, ["not an object"], [None]],
)
def test_wrong_payload_shapes_fail(monkeypatch, payload):
    response = Mock()
    response.json.return_value = payload
    monkeypatch.setattr("client.requests.get", Mock(return_value=response))
    with pytest.raises(ClientError, match=r".+"):
        fetch_countries()


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("country_name", " "),
        ("capital", None),
        ("population", None),
        ("population", -1),
        ("population", 1.5),
        ("population", True),
        ("population", "1234"),
        ("area", None),
        ("area", True),
        ("area", "56.75"),
        ("area", float("inf")),
        ("area", float("nan")),
    ],
)
def test_invalid_api_record_is_rejected_without_coercion(
    monkeypatch, sample_country, field, invalid
):
    response = Mock()
    response.json.return_value = [sample_country, {**sample_country, field: invalid}]
    monkeypatch.setattr("client.requests.get", Mock(return_value=response))
    with pytest.raises(ClientError, match=r".+"):
        fetch_countries()


def test_missing_unexpected_and_duplicate_fields_fail(monkeypatch, sample_country):
    payloads = [
        [{key: value for key, value in sample_country.items() if key != "population"}],
        [{**sample_country, "id": 1}],
        [sample_country, {**sample_country, "country_name": " Student Demo Country "}],
    ]
    for payload in payloads:
        response = Mock()
        response.json.return_value = payload
        monkeypatch.setattr("client.requests.get", Mock(return_value=response))
        with pytest.raises(ClientError):
            fetch_countries()


def test_dataframe_has_required_columns_and_numeric_types(country_records):
    frame = build_dataframe(country_records)
    assert frame.columns.tolist() == COLUMNS
    assert frame["population"].dtype.kind in "iu"
    assert frame["area"].dtype.kind == "f"
    assert frame["population"].tolist() == [1234, 0, 1234]
    assert frame["area"].tolist() == [56.75, 14_000_000.0, 56.75]
    assert frame["capital"].tolist() == ["Demo City", "None", "Demo City"]


def test_csv_has_exact_headers_rows_unicode_and_no_index(tmp_path, country_records):
    frame = build_dataframe(country_records)
    path = tmp_path / "exports" / "exported_countries.csv"
    assert export_csv(frame, path) == path
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == COLUMNS
        rows = list(reader)
    assert len(rows) == 3
    assert rows[0]["country_name"] == "Åland Islands"
    assert rows[1]["capital"] == "None"
    assert rows[1]["population"] == "0"
    assert rows[2]["country_name"] == "O'Brien Demo"
    reread = pd.read_csv(path, keep_default_na=False)
    pd.testing.assert_frame_equal(reread, frame)


def test_plot_uses_every_population_as_x_area_as_y_and_closes_figure(
    tmp_path, monkeypatch, country_records
):
    frame = build_dataframe(country_records)
    plotted = {}
    original_scatter = Axes.scatter

    def record_scatter(axes, x, y, *args, **kwargs):
        collection = original_scatter(axes, x, y, *args, **kwargs)
        plotted["axes"] = axes
        plotted["coordinates"] = collection.get_offsets().tolist()
        return collection

    monkeypatch.setattr(Axes, "scatter", record_scatter)
    path = tmp_path / "population_vs_area.png"
    assert save_scatter_plot(frame, path) is True
    assert plotted["coordinates"] == [
        [1234.0, 56.75],
        [0.0, 14_000_000.0],
        [1234.0, 56.75],
    ]
    axes = plotted["axes"]
    assert axes.get_xlabel() == "Population"
    assert axes.get_ylabel() == "Area (sq. km)"
    assert "Population vs Area" in axes.get_title()
    assert axes.get_xscale() == axes.get_yscale() == "linear"
    assert any(line.get_visible() for line in axes.get_xgridlines())
    assert any(line.get_visible() for line in axes.get_ygridlines())
    assert not plt.fignum_exists(axes.figure.number)
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    pixels = mpimg.imread(path)
    assert pixels.shape[0] >= 600 and pixels.shape[1] >= 900


def test_run_client_prints_all_twenty_rows_and_writes_matching_outputs(
    tmp_path, monkeypatch, capsys, sample_country
):
    payload = [{**sample_country, "country_name": f"Demo Row {index:02d}"} for index in range(20)]
    response = Mock()
    response.json.return_value = payload
    monkeypatch.setattr("client.requests.get", Mock(return_value=response))
    frame = run_client(output_dir=tmp_path)
    output = capsys.readouterr().out
    for country in payload:
        assert country["country_name"] in output
    assert "[20 rows x" not in output
    reread = pd.read_csv(tmp_path / "exported_countries.csv", keep_default_na=False)
    pd.testing.assert_frame_equal(reread, frame)
    assert len(reread) == 20
    assert (tmp_path / "population_vs_area.png").is_file()


def test_empty_api_writes_headers_and_fresh_explicit_empty_chart(tmp_path, monkeypatch, capsys):
    response = Mock()
    response.json.return_value = []
    monkeypatch.setattr("client.requests.get", Mock(return_value=response))
    path = tmp_path / "population_vs_area.png"
    path.write_bytes(b"old chart that must be replaced")
    captured = {}
    original_subplots = plt.subplots

    def record_subplots(*args, **kwargs):
        figure, axes = original_subplots(*args, **kwargs)
        captured["axes"] = axes
        return figure, axes

    monkeypatch.setattr(plt, "subplots", record_subplots)
    frame = run_client(output_dir=tmp_path)
    assert frame.empty
    assert frame.columns.tolist() == COLUMNS
    assert frame["population"].dtype.kind in "iu"
    assert "no countries" in capsys.readouterr().out.lower()
    with (tmp_path / "exported_countries.csv").open(encoding="utf-8", newline="") as stream:
        assert list(csv.reader(stream)) == [COLUMNS]
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert [text.get_text() for text in captured["axes"].texts] == ["No countries to plot"]
    assert not captured["axes"].collections
    assert not plt.fignum_exists(captured["axes"].figure.number)
