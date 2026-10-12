# Country Data Pipeline & Analytics System

[![Python checks](https://github.com/Akashkewat5220/Python_Capstone_Project/actions/workflows/ci.yml/badge.svg)](https://github.com/Akashkewat5220/Python_Capstone_Project/actions/workflows/ci.yml)

A Python capstone that reads the **first 20 countries in HTML document order** from [Scrape This Site](https://www.scrapethissite.com/pages/simple/), stores them in SQLite, serves them through FastAPI, and uses an HTTP client to print a Pandas DataFrame, export CSV, and draw a population-versus-area scatter plot.

```text
Live HTML → requests + BeautifulSoup → SQLite → FastAPI
                                              ↓ HTTP
                              requests client → Pandas → CSV + PNG
```

The source is a practice website. This project reproduces its displayed values; it does **not** claim to provide current national statistics. The 20-country limit applies to scraping, not to subsequent API CRUD operations.

## Quick start on macOS

Use Python **3.12 or newer**; development and verification use Python **3.12.10**. The pinned NumPy and ContourPy versions require at least 3.12. The commands below assume `python3.12` is installed. If your compatible interpreter has another name, replace that command accordingly. GitHub CI also uses Python 3.12; newer interpreters have not been verified here.

Clone the repository:

```bash
git clone https://github.com/Akashkewat5220/Python_Capstone_Project.git
cd Python_Capstone_Project
```

You can also choose **Code → Download ZIP** on GitHub and extract it. Open the project root: the folder containing `scraper.py`, `requirements-dev.txt`, and this README. In the commands below, replace `/path/to/your/checkout` with that folder's actual path. Keep the quotes if your folder path contains spaces.

In Terminal 1:

```bash
cd '/path/to/your/checkout'
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scraper.py
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Create `.venv` locally for each fresh checkout; it is excluded from Git because it contains installed libraries and paths specific to one computer. The requirements files let each contributor recreate the environment. `requirements-dev.txt` includes the runtime dependencies and the testing tools. For runtime use alone, install `requirements.txt` instead. On later runs, activate the existing environment and start from `python scraper.py`.

In Terminal 2:

```bash
cd '/path/to/your/checkout'
source .venv/bin/activate
python client.py
```

Visit <http://127.0.0.1:8000/docs> for Swagger UI. Keep Terminal 1 running while using the client or API. Stop your server with `Ctrl+C` when finished. Activating an environment applies only to that terminal; alternatively, use `.venv/bin/python` explicitly in each command.

Run the offline checks:

```bash
cd '/path/to/your/checkout'
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Actual commands, test results, live HTTP checks, and artifact inspections are recorded in [VERIFICATION.md](VERIFICATION.md). Ordinary tests use local fixtures and temporary databases, with no dependency on the live website.

## Files and responsibilities

The five application modules stay in one flat directory so the complete flow is easy to follow:

```text
.
├── scraper.py
├── database.py
├── schemas.py
├── api.py
├── client.py
├── scripts/
│   └── verify_pipeline.py
├── tests/
│   ├── conftest.py
│   ├── test_scraper.py
│   ├── test_database.py
│   ├── test_api.py
│   ├── test_client.py
│   └── fixtures/
│       └── countries.html
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── README.md
├── VERIFICATION.md
├── .gitignore
├── .gitattributes
└── .github/
    └── workflows/
        └── ci.yml
```

| File | Responsibility |
| --- | --- |
| `scraper.py` | Fetch HTML, parse the selected 20 records, and explicitly seed SQLite. |
| `database.py` | `CountryDatabaseManager`, parameterized CRUD, transactions, and database exceptions. |
| `schemas.py` | Shared Pydantic validation and request/response contracts. |
| `api.py` | Application factory, schema initialization, and five thin HTTP routes. |
| `client.py` | Fetch API data with `requests`, print the DataFrame, export CSV, and save the scatter plot. |
| `tests/` | Offline fixtures and behavior tests using temporary databases/output directories. |
| `scripts/verify_pipeline.py` | Explicit live check with a temporary database and real Uvicorn server. |
| `requirements.txt` | Exact, verified runtime dependency versions. |
| `requirements-dev.txt` | Runtime dependencies plus pytest, httpx, and Ruff. |
| `pyproject.toml` | Pytest and Ruff configuration. |
| `.github/workflows/ci.yml` | Python 3.12 test, lint, and format checks on GitHub. |
| `VERIFICATION.md` | Execution evidence and verification commands. |

Default paths are resolved relative to the project files, independent of the working directory that launches a command:

| Generated file | Default location |
| --- | --- |
| SQLite database | `countries.db` in your project root |
| CSV export | `exported_countries.csv` in your project root |
| Scatter plot | `population_vs_area.png` in your project root |

These artifacts and `.venv` are ignored by Git. A fresh checkout regenerates them through the commands above.

## Data contract and scraping

Every layer uses the same four fields, in this CSV/DataFrame column order:

| Field | Contract |
| --- | --- |
| `country_name` | Nonempty string after surrounding whitespace is trimmed; natural primary key. |
| `capital` | String with surrounding whitespace trimmed; an empty string is allowed. |
| `population` | Nonnegative integer, at most `9223372036854775807` to fit SQLite's signed 64-bit INTEGER. |
| `area` | Finite, nonnegative number, represented as a float in square kilometers. |

Names are matched **case-sensitively after trimming**. For example, `" Demo Country "` and `"Demo Country"` identify the same record, while `"demo country"` is a different name. Spelling, punctuation, and Unicode are preserved; there is no accent folding, case folding, or alternate-name lookup. Population and area reject boolean values; population rejects floating-point values and numeric strings in API/client data. Unexpected fields are rejected.

The source's literal capital string `"None"` remains a string. Zero population is valid, `1.4E7` is valid HTML area notation and becomes `14000000.0`, and accented names such as `Åland` remain intact throughout the pipeline. CSV consumers should preserve literal strings: for example, use `pd.read_csv('exported_countries.csv', keep_default_na=False)` if reloading with Pandas so `"None"` is not interpreted as a missing value.

The scraper selects `.country` containers, slices the first 20 in document order, then parses and validates **all** selected records. It does not skip an invalid selected country or substitute a later one. Missing fields, malformed numbers, duplicate selected names, or fewer than 20 containers fail the scrape without a partial seed. HTML parsing is separate from fetching so it can be tested offline. Fetching uses a finite timeout, HTTP status checks, and normal TLS verification.

`python scraper.py` is an explicit seed command. Imports and API startup never fetch the website. One transaction performs an explicit upsert: matching scraped countries are refreshed, missing ones are inserted, and unrelated manually created countries remain. Repeating seeding therefore does not duplicate countries; if unrelated records already exist, the total may exceed 20. Ordinary `create_country` and `POST` reject duplicates instead of applying this seed behavior.

Use a different database for an isolated demonstration:

```bash
python scraper.py --db /tmp/country-demo.db
COUNTRY_DB_PATH=/tmp/country-demo.db python -m uvicorn api:app --host 127.0.0.1 --port 8001
```

In another activated terminal:

```bash
python client.py --base-url http://127.0.0.1:8001 --output-dir /tmp/country-demo-output
```

The API honors `COUNTRY_DB_PATH`; `create_app(db_path=...)` also allows tests to choose a temporary database. Relative override paths are resolved to an absolute path. The API initializes the schema without seeding it, so an unseeded database returns an empty list.

## SQLite and OOP

The `countries` table uses this schema:

```sql
CREATE TABLE IF NOT EXISTS countries (
    country_name TEXT NOT NULL PRIMARY KEY
        CHECK (length(trim(country_name)) > 0),
    capital TEXT NOT NULL,
    population INTEGER NOT NULL
        CHECK (typeof(population) = 'integer' AND population >= 0),
    area REAL NOT NULL
        CHECK (area >= 0 AND area <= 1.7976931348623157e308)
);
```

Pydantic additionally validates the complete contract before database operations, including finite area values. A country name is a **natural primary key** because the assignment already supplies that unique identifier. No generated numeric ID is needed.

`CountryDatabaseManager` owns database operations; it does not scrape, serve HTTP, or plot. Each operation opens and reliably closes its own connection. Writes use explicit transactions, so committed data survives new connections and a failed batch rolls back together. There is no shared global connection across API requests.

| Method | Input and successful return | Expected failure behavior |
| --- | --- | --- |
| `initialize_schema()` | Create the table if needed; return `None`. | Database errors remain errors. |
| `create_country(country)` | Validated country; return the stored country. | Duplicate name raises `DuplicateCountryError`. |
| `list_countries()` | No arguments; return a list sorted by name using SQLite `BINARY` ordering. | An empty database returns `[]`. |
| `get_country(name)` | Trimmed name; return the stored country. | Missing name raises `CountryNotFoundError`. |
| `update_country(name, details)` | Complete capital/population/area replacement; return the updated country. | Missing name raises `CountryNotFoundError`. |
| `delete_country(name)` | Delete by name; return `None`. | Missing name raises `CountryNotFoundError`. |
| `upsert_seed(countries)` | Validated, unique batch; return the number of upserted records. | Invalid batch fails before writing; transaction failures roll back. |

List order is deterministic name order, which may differ from the HTML selection order. Selection is always performed before sorting.

All SQL that uses values uses placeholders and bound parameters. This separates data from SQL syntax, so names containing apostrophes work correctly and cannot change the query. Validation happens at the scraper/client boundary and in the database manager, while Pydantic provides FastAPI's normal `422` request validation.

## REST API

Swagger UI at `/docs` includes schemas, route descriptions, and synthetic examples. Responses use the same four country fields. `PUT` keeps the name immutable: it accepts exactly `capital`, `population`, and `area`, all required, and replaces those details completely. Rename by explicitly deleting and creating a record if needed.

| Endpoint | Successful response | Expected errors |
| --- | --- | --- |
| `GET /countries` | `200`, JSON array; `[]` if empty. | Unexpected server failures are server errors. |
| `GET /countries/{country_name}` | `200`, one country object. | `404` if absent. |
| `POST /countries` | `201`, created country object. | `409` duplicate normalized name; `422` invalid body. |
| `PUT /countries/{country_name}` | `200`, updated country object. | `404` absent; `422` invalid or incomplete body. |
| `DELETE /countries/{country_name}` | `204`, no response body. | `404` if absent. |

Blank names, negative/fractional population, boolean numeric values, nonfinite area, missing required fields, or unexpected body fields fail validation. Expected duplicate/missing errors are translated into HTTP responses without exposing SQL internals; unexpected failures do not become success responses.

A list response has this shape (illustrative synthetic data):

```json
[
  {
    "country_name": "Demo Student Country",
    "capital": "Demo Capital",
    "population": 1000,
    "area": 125.5
  }
]
```

The same country object is returned by successful single-country GET, POST, and PUT requests. A `404` or `409` uses a JSON `detail` message; a `422` contains FastAPI's structured field-validation details.

### Short CRUD demo

Use an isolated database/server as shown above if you want to keep your main deliverables unchanged. These commands use port 8001 and a synthetic country, then remove it.

```bash
curl -i -X POST http://127.0.0.1:8001/countries \
  -H 'Content-Type: application/json' \
  -d '{"country_name":"Demo Student Country","capital":"Demo Capital","population":1000,"area":125.5}'

curl -i 'http://127.0.0.1:8001/countries/Demo%20Student%20Country'

curl -i -X PUT 'http://127.0.0.1:8001/countries/Demo%20Student%20Country' \
  -H 'Content-Type: application/json' \
  -d '{"capital":"Updated Demo Capital","population":2000,"area":150.0}'

curl -i -X DELETE 'http://127.0.0.1:8001/countries/Demo%20Student%20Country'
curl -i http://127.0.0.1:8001/countries
```

Expected statuses are `201`, `200`, `200`, `204`, and `200`. Repeating POST before deletion returns `409`; reading or deleting the name after deletion returns `404`. To demonstrate `422` without changing data:

```bash
curl -i -X POST http://127.0.0.1:8001/countries \
  -H 'Content-Type: application/json' \
  -d '{"country_name":"Invalid Demo","capital":"Demo","population":-1,"area":1.0}'
```

Encode country names as URL path segments, not as raw strings containing spaces:

```bash
curl -i 'http://127.0.0.1:8000/countries/%C3%85land'
```

In Python, `quote` handles Unicode, spaces, and apostrophes:

```python
from urllib.parse import quote

import requests

name = "Demo Student's Åland"
encoded_name = quote(name, safe="")  # Demo%20Student%27s%20%C3%85land
response = requests.get(f"http://127.0.0.1:8000/countries/{encoded_name}", timeout=10)
print(response.status_code)  # 404 until this exact synthetic name is created
```

## Client, export, and chart

The standalone client calls `GET /countries` using `requests`, a finite timeout, and HTTP status checking. It validates the complete JSON payload before constructing the DataFrame. Connection errors, bad HTTP responses, invalid JSON, and contract violations produce clear failures; missing numeric values are not replaced with zero. The client never opens SQLite or scrapes HTML.

The DataFrame prints all rows with columns `country_name`, `capital`, `population`, `area`. Population remains integer-valued and area remains numeric. Export uses UTF-8, headers, and `index=False`.

The PNG uses the **same DataFrame** as the CSV. It plots every returned country, including zero-population records, with Population on the X-axis and Area (sq. km) on the Y-axis. Axes are linear and tick labels show unscaled numbers with comma separators; there is no hidden multiplier or scientific notation. The large area of Antarctica in the practice dataset can make smaller countries appear clustered, which is an expected consequence of plotting the supplied values on linear axes. Markers, title, labels, gridlines, tight layout, and a suitable PNG resolution make the output legible. Matplotlib uses a noninteractive backend and closes each figure, so no graphical display is required.

For an empty API response, the client prints a clear message, writes a CSV containing the four headers and no rows, and writes a fresh labeled **"No countries to plot"** PNG. This avoids presenting a chart from an earlier run as new data.

## Testing and verification

Tests check behavior across parsing, database persistence, API validation/statuses, and HTTP-client outputs. Fixtures contain more than 20 countries to verify selection order. Edge cases include whitespace, Unicode, zero population, scientific-notation area, and literal `"None"` capital values. Failure cases cover malformed/missing source fields, too few countries, fetching errors, duplicate/missing records, invalid API/client data, and empty datasets.

Temporary paths isolate tests from `countries.db`. Plot tests inspect the actual X/Y data and confirm a PNG is written. CSV tests verify headers, row counts, Unicode, literal capitals, and the absence of an index column. GitHub Actions runs the offline tests and Ruff checks on Python 3.12.

Live verification is separate: seed a fresh isolated database, compare it with the selected source records, seed again, start Uvicorn, request the endpoints through real HTTP, run `client.py`, inspect its exports, and exercise synthetic CRUD before checking that the original records remain. Final deliverables are generated from the genuine source data. See [VERIFICATION.md](VERIFICATION.md) for the actual executed commands and results, including any access limitation.

Run the complete isolated live check from the project root:

```bash
.venv/bin/python -m scripts.verify_pipeline
```

This command needs internet access and permission to bind a local port. It selects a free localhost port, starts and stops only its own server, and removes only its own temporary directory. It verifies all source fields, SQLite schema/storage types, repeat seeding, real HTTP endpoints/statuses, synthetic CRUD cleanup, CSV contents, and PNG integrity. It prints the entire 20-row client result. It does not overwrite your default deliverables. The source may change later; a changed layout or inconsistent responses should cause an honest verification failure.

## Viva explanation

- **OOP:** `CountryDatabaseManager` groups schema and CRUD responsibilities around one database path. Other modules ask it to manage storage instead of duplicating SQL.
- **Atomicity:** the entire validated seed batch is committed together. A failure cannot leave a partly seeded batch.
- **Parameterized SQL:** values are passed separately from query text, making quoted names safe and avoiding SQL injection.
- **HTTP validation:** Pydantic checks incoming request bodies before routes run; FastAPI reports invalid bodies as `422`. Routes map duplicate and missing records to `409` and `404`.
- **Client/server boundary:** only the server manages SQLite. The client consumes its public HTTP response and then performs local analysis/export, demonstrating the complete pipeline.
- **Reproducibility:** pinned dependencies, offline tests, documented commands, CI, and a separate execution record allow another person to reproduce and review the project.

## Sharing with your instructor on GitHub

Commit source, tests, documentation, dependency files, and CI. `.gitignore` excludes the local environment, generated database/CSV/PNG, and caches. Do not commit credentials or add personal tokens to scripts or URLs. The instructor can regenerate the three outputs; if your instructor also requests deliverable files, attach them to the submission or a GitHub release separately.

Cloning a repository already creates its Git metadata and `origin` remote. A ZIP download does not: if you want to publish a ZIP checkout as your own repository, first run `git init -b main` from its project root. Configure your real author identity for this repository if it is not already configured; replace both placeholders before running:

```bash
git config user.name 'YOUR_NAME'
git config user.email 'YOUR_GITHUB_EMAIL_OR_NOREPLY_ADDRESS'
```

These settings apply only to this repository. Then review and commit:

```bash
cd '/path/to/your/checkout'
git status --short
git diff
git add .
git diff --cached --stat
git commit -m 'Implement country data pipeline and analytics capstone'
```

For a local project without a remote, create an empty GitHub repository through GitHub's website, choose visibility appropriate for your course, and replace `YOUR_REPOSITORY_CLONE_URL` below with its actual HTTPS or SSH clone URL. Avoid adding a second README during repository creation when publishing this existing project.

```bash
git remote add origin 'YOUR_REPOSITORY_CLONE_URL'
git push -u origin main
```

If `origin` already exists, inspect `git remote -v` and use the correct existing remote instead of adding another one. Authenticate through your normal GitHub method. Share the repository URL with your instructor; for a private repository, grant the instructor access. Check the Actions tab for the CI result and include [VERIFICATION.md](VERIFICATION.md) in the review.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `ModuleNotFoundError` or missing executable | Activate `.venv` in that terminal and run `python -m pip install -r requirements-dev.txt`; use `.venv/bin/python` to avoid a different interpreter. |
| `python3.12: command not found` | Install Python 3.12 or use an available Python 3.12+ interpreter when creating `.venv`; these pinned dependencies do not support 3.11. |
| Client reports connection refused | Start Uvicorn first and confirm the client's `--base-url` matches its host/port. |
| Uvicorn reports address already in use | Choose another port, such as `8001`, and pass that port to the client. Stop only a server you started. |
| Scraper timeout, TLS, DNS, or HTTP error | Check internet access and source availability, then rerun. Keep TLS verification enabled; do not use fixture data as a claimed live result. |
| SQLite cannot open the database | Check that the parent directory exists and is writable, and inspect `COUNTRY_DB_PATH` or `--db`. Default paths use the project location. |
| API returns `[]` | The selected database has no records. Run the scraper against the same database path; API startup does not scrape. |
| More than 20 rows after seeding | Existing manually created countries are deliberately preserved. Use a fresh isolated database for a 20-row verification. |
| `409` when creating a country | The trimmed, case-sensitive name already exists; use PUT to replace its details. |
| Source layout changes | Inspect the live HTML and parser errors. Do not weaken validation or skip a malformed record to force success. |
| CSV displays `None` as missing in another tool | The CSV preserves the literal text; configure the reader's missing-value handling, such as Pandas `keep_default_na=False`. |

## Requirement-to-implementation checklist

| Assignment requirement | Implementation | Evidence |
| --- | --- | --- |
| Project-local environment and compatible dependencies | `.venv`, dependency files, setup instructions | Setup and dependency checks in `VERIFICATION.md`. |
| First 20 containers in document order; source edge cases; no partial seed | `scraper.py`, `schemas.py` | Parser/seed tests and isolated live comparison. |
| Natural key, full OOP CRUD, parameterized SQL, transactions, persistence | `database.py` | Temporary-database CRUD, rollback, persistence, and upsert tests. |
| Idempotent seed preserves unrelated countries | `upsert_seed`, explicit scraper command | Offline upsert tests and repeated live seed count. |
| Five FastAPI endpoints, useful docs, correct statuses/validation | `api.py`, `schemas.py` | API tests plus live HTTP CRUD in `VERIFICATION.md`. |
| Encoded spaces, apostrophes, and Unicode | Shared name contract and parameterized queries | Routing/database tests and examples above. |
| Requests-only client boundary and complete DataFrame | `client.py` | Client response/error tests and real-server client execution. |
| UTF-8 CSV, four columns, no index | `client.py`, `exported_countries.csv` | CSV tests and 20-row live artifact check. |
| Population X-axis, area Y-axis, zero values, labeled PNG | `client.py`, `population_vs_area.png` | Plot data tests and visual artifact inspection. |
| Empty-data and failure handling | Scraper, database, API, client | Offline edge-case tests. |
| Genuine final dataset without synthetic leftovers | `countries.db`, CSV, PNG | Final source/database/export comparison in `VERIFICATION.md`. |
| Beginner handover and GitHub-ready reproducibility | README, verification record, `.gitignore`, CI | Documented commands and offline GitHub Actions workflow. |
