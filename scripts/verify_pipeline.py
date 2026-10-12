"""Explicit live integration check; never run as part of the offline test suite.

Run from the project root with: .venv/bin/python -m scripts.verify_pipeline
Only this check's temporary database is mutated. The real server is stopped in
a finally block, and TemporaryDirectory removes only this check's own files.
"""

import csv
import os
import shlex
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from PIL import Image

from database import CountryDatabaseManager
from scraper import SCRAPE_LIMIT, fetch_html, seed_database

PROJECT_DIR = Path(__file__).resolve().parent.parent
COLUMNS = ["country_name", "capital", "population", "area"]


def require(condition: bool, message: str) -> None:
    """Keep verification active even if Python is run with optimization enabled."""
    if not condition:
        raise RuntimeError(message)


def check_exports(output_dir: Path, expected: list[dict]) -> None:
    with (output_dir / "exported_countries.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == COLUMNS, "CSV columns or index are incorrect")
        rows = list(reader)
    actual = [
        {**row, "population": int(row["population"]), "area": float(row["area"])} for row in rows
    ]
    require(actual == expected, "CSV records differ from the API/source dataset")
    with Image.open(output_dir / "population_vs_area.png") as image:
        require(image.format == "PNG", "Chart is not a PNG")
        require(image.size == (1620, 1080), "Unexpected chart resolution")
        image.verify()
    print(f"CSV: {len(rows)} exact source rows, UTF-8, four headers, no index; PNG: 1620×1080")


def main() -> None:
    # Independently read the displayed fields to compare the database with the
    # selected source records, rather than checking the count alone.
    html = fetch_html()
    selected = BeautifulSoup(html, "html.parser").select(".country")[:SCRAPE_LIMIT]
    require(len(selected) == 20, "Live source has fewer than 20 countries")
    expected = [
        {
            "country_name": item.select_one(".country-name").get_text().strip(),
            "capital": item.select_one(".country-capital").get_text().strip(),
            "population": int(item.select_one(".country-population").get_text().strip()),
            "area": float(item.select_one(".country-area").get_text().strip()),
        }
        for item in selected
    ]
    expected.sort(key=lambda record: record["country_name"])
    with TemporaryDirectory(prefix="country-capstone-live-") as temporary:
        directory = Path(temporary)
        db_path = directory / "countries.db"
        seed_database(db_path)
        manager = CountryDatabaseManager(db_path)
        require(
            [item.model_dump() for item in manager.list_countries()] == expected,
            "Initial live seed differs from the selected source records",
        )
        with sqlite3.connect(db_path) as connection:
            schema = connection.execute("PRAGMA table_info(countries)").fetchall()
            require(
                [(row[1], row[2], row[3], row[5]) for row in schema]
                == [
                    ("country_name", "TEXT", 1, 1),
                    ("capital", "TEXT", 1, 0),
                    ("population", "INTEGER", 1, 0),
                    ("area", "REAL", 1, 0),
                ],
                "Natural-key schema does not match the contract",
            )
            types = connection.execute(
                "SELECT DISTINCT typeof(population), typeof(area) FROM countries"
            ).fetchall()
            require(types == [("integer", "real")], "SQLite numeric types are incorrect")
        print(
            "Live seed: exactly 20 matching records, natural TEXT primary key, INTEGER/REAL storage"
        )
        seed_database(db_path)
        require(
            [item.model_dump() for item in manager.list_countries()] == expected,
            "Repeated seed changed records or produced duplicates",
        )
        print("Repeated live seed: exactly 20 unchanged records")

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"
        server_command = [
            sys.executable,
            "-m",
            "uvicorn",
            "api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        environment = {**os.environ, "COUNTRY_DB_PATH": str(db_path)}
        print("Server command: " + shlex.join(server_command))
        with (directory / "server.log").open("w+") as log:
            server = subprocess.Popen(
                server_command,
                cwd=PROJECT_DIR,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 15
                while True:
                    require(server.poll() is None, "Uvicorn exited before becoming ready")
                    try:
                        response = requests.get(f"{base_url}/countries", timeout=1)
                        if response.status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    require(time.monotonic() < deadline, "Uvicorn did not become ready")
                    time.sleep(0.1)

                def request(method: str, path: str, status: int, **kwargs) -> requests.Response:
                    result = requests.request(method, base_url + path, timeout=10, **kwargs)
                    require(
                        result.status_code == status,
                        f"{method} {path}: expected {status}, got {result.status_code}: {result.text}",
                    )
                    print(f"HTTP {method} {path}: {status}")
                    return result

                require(
                    request("GET", "/countries", 200).json() == expected,
                    "HTTP list differs from source records",
                )
                aland = next(item for item in expected if item["country_name"] == "Åland")
                require(
                    request("GET", "/countries/" + quote("Åland", safe=""), 200).json() == aland,
                    "Unicode routing changed Åland",
                )
                request("GET", "/docs", 200)
                request("GET", "/openapi.json", 200)
                client_command = [
                    sys.executable,
                    "client.py",
                    "--base-url",
                    base_url,
                    "--output-dir",
                    str(directory),
                ]
                print("Client command: " + shlex.join(client_command))
                subprocess.run(client_command, cwd=PROJECT_DIR, check=True, timeout=60)
                check_exports(directory, expected)

                demo = {
                    "country_name": "Demo Student's Åland",
                    "capital": "Demo Capital",
                    "population": 1000,
                    "area": 125.5,
                }
                path = "/countries/" + quote(demo["country_name"], safe="")
                require(
                    request("POST", "/countries", 201, json=demo).json() == demo,
                    "Create response is incorrect",
                )
                require(
                    len(request("GET", "/countries", 200).json()) == 21,
                    "API must allow creating a 21st country",
                )
                require(request("GET", path, 200).json() == demo, "Synthetic GET differs")
                request(
                    "POST",
                    "/countries",
                    409,
                    json={**demo, "country_name": " " + demo["country_name"] + " "},
                )
                details = {"capital": "Updated Demo Capital", "population": 2000, "area": 150.0}
                require(
                    request("PUT", path, 200, json=details).json()
                    == {"country_name": demo["country_name"], **details},
                    "PUT did not replace details while preserving the key",
                )
                request("POST", "/countries", 422, json={**demo, "population": 1.5})
                require(request("DELETE", path, 204).content == b"", "DELETE has a response body")
                request("GET", path, 404)
                request("PUT", path, 404, json=details)
                request("DELETE", path, 404)
                require(
                    request("GET", "/countries", 200).json() == expected,
                    "Synthetic CRUD changed the original source records",
                )
                print("Synthetic CRUD removed; all original 20 records are intact")
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                if server.poll() is None:
                    server.terminate()
                    try:
                        server.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
                print("Stopped this check's Uvicorn process")
    print("PASS: genuine live source → SQLite → real HTTP API → client → CSV and PNG")


if __name__ == "__main__":
    main()
