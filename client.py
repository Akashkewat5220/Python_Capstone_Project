"""Consume the REST API, print a DataFrame, and export CSV and a scatter plot."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Save figures on machines without a graphical display.
import matplotlib.pyplot as plt
import pandas as pd
import requests
from matplotlib.ticker import FuncFormatter
from pydantic import ValidationError

from schemas import Country

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent
REQUEST_TIMEOUT = 20.0
COLUMNS = ["country_name", "capital", "population", "area"]


class ClientError(Exception):
    """The API could not be reached or did not satisfy the country contract."""


def fetch_countries(
    base_url: str = DEFAULT_BASE_URL, timeout: float = REQUEST_TIMEOUT
) -> list[Country]:
    """Fetch and validate all GET /countries records through HTTP only."""
    url = f"{base_url.rstrip('/')}/countries"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ClientError(f"Could not request {url}: {exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise ClientError("The API returned invalid JSON.") from exc
    if not isinstance(payload, list):
        raise ClientError("The API payload must be a JSON array of country objects.")
    countries: list[Country] = []
    names: set[str] = set()
    for position, record in enumerate(payload, start=1):
        try:
            country = Country.model_validate(record)
        except ValidationError as exc:
            raise ClientError(
                f"API country #{position} violates the field contract: {exc}"
            ) from exc
        if country.country_name in names:
            raise ClientError(f"Duplicate API country name: {country.country_name!r}.")
        names.add(country.country_name)
        countries.append(country)
    return countries


def build_dataframe(countries: list[Country]) -> pd.DataFrame:
    """Build the fixed column order without substituting or coercing bad values."""
    frame = pd.DataFrame([country.model_dump() for country in countries], columns=COLUMNS)
    # Records have already passed strict validation; explicit dtypes also keep
    # empty results consistent with nonempty results.
    return frame.astype({"population": "int64", "area": "float64"})


def export_csv(frame: pd.DataFrame, output_path: str | Path) -> Path:
    """Write a UTF-8 CSV with headers and no DataFrame index."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, encoding="utf-8", index=False)
    return path


def save_scatter_plot(frame: pd.DataFrame, output_path: str | Path) -> bool:
    """Save a fresh PNG, including an explicit placeholder for empty data.

    Axes use original population and square-kilometer values, linear scales,
    and comma-separated ticks. Return whether there were countries to plot.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(figsize=(9, 6))
    try:
        axes.set_title("Population vs Area — Country Dataset", pad=14)
        axes.set_xlabel("Population")
        axes.set_ylabel("Area (sq. km)")
        axes.grid(True, alpha=0.35)
        axes.set_axisbelow(True)
        formatter = FuncFormatter(lambda value, _: f"{value:,.2f}".rstrip("0").rstrip("."))
        axes.xaxis.set_major_formatter(formatter)
        axes.yaxis.set_major_formatter(formatter)
        if frame.empty:
            axes.text(
                0.5, 0.5, "No countries to plot", ha="center", va="center", transform=axes.transAxes
            )
        else:
            axes.scatter(
                frame["population"],
                frame["area"],
                s=55,
                alpha=0.8,
                color="#2563a6",
                edgecolors="white",
                linewidths=0.5,
            )
        axes.tick_params(axis="x", labelrotation=20)
        fig.tight_layout()
        fig.savefig(path, dpi=180)
    finally:
        plt.close(fig)
    return not frame.empty


def run_client(
    base_url: str = DEFAULT_BASE_URL, output_dir: str | Path = DEFAULT_OUTPUT_DIR
) -> pd.DataFrame:
    """Fetch once; use the same complete DataFrame for printing, CSV, and PNG."""
    frame = build_dataframe(fetch_countries(base_url))
    if frame.empty:
        print("The API returned no countries. Exporting CSV headers and an empty-data chart.")
    else:
        print(frame.to_string(index=False))
    directory = Path(output_dir).resolve()
    csv_path = export_csv(frame, directory / "exported_countries.csv")
    plot_path = directory / "population_vs_area.png"
    save_scatter_plot(frame, plot_path)
    print(f"CSV: {csv_path}")
    print(f"Chart: {plot_path}")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API origin, including port")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    try:
        run_client(args.base_url, args.output_dir)
    except (ClientError, OSError) as exc:
        parser.exit(1, f"Client failed: {exc}\n")


if __name__ == "__main__":
    main()
