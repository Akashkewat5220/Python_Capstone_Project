# Verification record

Initial end-to-end verification completed on **12 October 2026** (Asia/Kolkata), on macOS with **Python 3.12.10**. Commands were run from the project root. For a fresh checkout, replace the example path below with your own project folder:

```bash
cd '/path/to/your/checkout'
```

The required live pipeline was exercised successfully with genuine source data. The initial verified database, CSV, and PNG contained exactly the first 20 countries selected from the source page, with no synthetic CRUD records left behind. These are generated local files and are not committed. Later API use may add countries; a fresh scrape into an empty database still seeds exactly 20. This record describes local verification before repository publication; it does not claim a GitHub-hosted CI result.

## Initial inspection and environment

The workspace was empty before implementation. The assignment PDF was accessible: its two pages were extracted and visually inspected. Its requirements were checked against the implementation contract. The live page was fetched and its actual `.country`, `.country-name`, `.country-capital`, `.country-population`, and `.country-area` HTML elements were inspected. Source text was handled as UTF-8.

Executed environment setup:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir requests beautifulsoup4 fastapi uvicorn pandas matplotlib pytest httpx ruff
```

Result: the project-local environment and all required packages were installed successfully. Exact runtime and development dependency versions, including transitive dependencies, were then recorded in the requirements files.

Executed verification of the pinned installation:

```bash
.venv/bin/python -m pip install --no-cache-dir -r requirements-dev.txt
.venv/bin/python -m pip check
```

Results: the pinned requirements were satisfied; `pip check` reported **`No broken requirements found.`** The selected NumPy and contourpy versions require Python 3.12 or newer, so the documented prerequisite for this pinned environment is Python 3.12+.

## Offline automated checks

Executed:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Results: the final run reported **103 tests passed in 12.64 seconds, with no warnings**; Ruff reported **`All checks passed!`**, and its final formatting check, including this record, reported **13 files already formatted**. Project Python files also compiled successfully. Tests use temporary databases/output directories and offline HTML fixtures rather than the live website.

| Behavior checked | Result |
| --- | --- |
| More than 20 containers selects exactly the first 20 in document order | Passed. |
| Whitespace, Unicode, zero population, scientific-notation area, and literal `"None"` capital | Passed. |
| Missing/malformed source fields, too few containers, duplicates, and fetching errors | Clear failures; no partial seed. |
| Natural-key CRUD, duplicate rejection, missing records, and persistence across connections | Passed. |
| Atomic seed, repeated seed, and preservation of unrelated manual countries | Passed. |
| All five API endpoints, empty list, expected `404`/`409`/`422`, and bodyless `204` | Passed. |
| Strict numeric validation, immutable PUT name, extra fields, and encoded names | Passed. |
| Client HTTP success/failure, invalid JSON/payload, and empty data | Passed. |
| CSV columns/counts, Unicode/literal strings, integer population, and no index | Passed. |
| Actual scatter X/Y data, zero values, PNG creation, and fresh empty-data chart | Passed. |

## Genuine live integration check

Executed separately from pytest:

```bash
.venv/bin/python -m scripts.verify_pipeline
```

Actual final result:

```text
PASS: genuine live source → SQLite → real HTTP API → client → CSV and PNG
```

The verifier fetched <https://www.scrapethissite.com/pages/simple/>, independently read the first 20 source containers, and compared every field with the seeded records. It used a fresh temporary database and a real Uvicorn subprocess, followed by the standalone `client.py` subprocess over HTTP. It cleaned up only its own server and temporary directory.

The server selected port **53221** for this run. The equivalent subprocess commands executed by the script were:

```bash
COUNTRY_DB_PATH='<temporary-directory>/countries.db' .venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 53221
.venv/bin/python client.py --base-url http://127.0.0.1:53221 --output-dir '<temporary-directory>'
```

`<temporary-directory>` represents the directory created and removed by the script; it is not a literal path to reuse. Future runs choose another available port and temporary directory automatically, so rerun the script itself.

| Live check | Actual result |
| --- | --- |
| Initial seed | Exactly 20 records, with every field equal to the selected live source values. |
| Schema inspection | `country_name` is the nonnull `TEXT` primary key; population and area have `INTEGER` and `REAL` storage. |
| Second seed | Exactly 20 unchanged records, with no duplicates. |
| `GET /countries` | `200`; all 20 objects equal the source records in documented name order. |
| `GET /countries/%C3%85land` | `200`; Unicode name and all fields preserved. |
| `GET /docs` and `GET /openapi.json` | Both `200`. |
| Standalone client | Printed the complete 20-row DataFrame and generated CSV and PNG through HTTP. |
| CSV | 20 data rows, exactly four required headers, no extra index, UTF-8, all values equal to the source. |
| PNG | Valid PNG, **1620 × 1080** pixels. |
| Cleanup | Own Uvicorn process stopped; temporary files removed. |

The same real server exercised CRUD with the synthetic name `Demo Student's Åland`, whose encoded path is `/countries/Demo%20Student%27s%20%C3%85land`:

| Operation | Actual result |
| --- | --- |
| Create synthetic country | `201`; returned the submitted record. |
| List after create | `200`; count increased to **21**, confirming 20 is not a database limit. |
| Read synthetic country | `200`; exact name and values preserved. |
| Create again with surrounding name whitespace | `409`, confirming normalized duplicate rejection. |
| Replace capital/population/area | `200`; replacement details returned and country name unchanged. |
| Create with fractional population | `422`. |
| Delete synthetic country | `204`; response body was empty. |
| Read, update, and delete the removed name | Each returned `404`. |
| Final list | `200`; the original 20 source records remained intact. |

## Final deliverable generation and inspection

After isolated verification, these commands generated the actual deliverables in the project folder:

```bash
.venv/bin/python scraper.py
.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

With that server running, in a second terminal:

```bash
cd '/path/to/your/checkout'
.venv/bin/python client.py
```

Results: scraping seeded exactly 20 genuine source countries. The real API served those records, and the client printed all 20 rows and generated the final CSV and scatter plot. The server started for this run was then stopped with `Ctrl+C`, and Uvicorn completed a clean shutdown.

The final artifacts were independently inspected:

| Artifact | Actual inspection result |
| --- | --- |
| `countries.db` | **12,288 bytes**; `PRAGMA integrity_check` returned `ok`; exactly 20 records; complete values equal the selected saved live HTML; correct natural primary key and numeric types. |
| `exported_countries.csv` | **747 bytes**; 20 rows; headers exactly `country_name,capital,population,area`; no index column; every value equal to the database/source; `Åland` and literal `"None"` preserved. |
| `population_vs_area.png` | **67,308 bytes**; valid PNG at **1620 × 1080**; image opened and visually inspected. |

The chart's title, Population X-axis, Area (sq. km) Y-axis, tick labels, and gridlines were readable. Axes are linear, with comma-formatted original values and no hidden scale multiplier. The zero-population Antarctica point at 14,000,000 sq. km is included; its large area makes the smaller countries cluster, as expected from the source values. No synthetic country remained in any final artifact.

All three files are at the project root. Their sizes describe this verified run; regenerated outputs may differ if the live practice-site dataset or dependency behavior changes.

### Repeat the final artifact inspection

The following source-download and inspection commands were executed during verification. The HTML snapshot is temporary and is not committed. Download it again before repeating the inspection; if the website changes, reseed and regenerate the outputs before comparing them with its new values.

```bash
curl --fail --show-error --silent --max-time 30 https://www.scrapethissite.com/pages/simple/ -o /private/tmp/capstone-source-initial.html
.venv/bin/python - <<'PY'
import csv
from pathlib import Path
import sqlite3

from bs4 import BeautifulSoup
from PIL import Image

from database import CountryDatabaseManager

root = Path.cwd()
soup = BeautifulSoup(
    Path('/private/tmp/capstone-source-initial.html').read_text(encoding='utf-8'),
    'html.parser',
)
expected = sorted([
    {
        'country_name': item.select_one('.country-name').get_text().strip(),
        'capital': item.select_one('.country-capital').get_text().strip(),
        'population': int(item.select_one('.country-population').get_text().strip()),
        'area': float(item.select_one('.country-area').get_text().strip()),
    }
    for item in soup.select('.country')[:20]
], key=lambda country: country['country_name'])
actual = [
    country.model_dump()
    for country in CountryDatabaseManager(root / 'countries.db').list_countries()
]
assert len(actual) == 20 and actual == expected
with sqlite3.connect(root / 'countries.db') as connection:
    assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    assert connection.execute(
        'SELECT DISTINCT typeof(population), typeof(area) FROM countries'
    ).fetchall() == [('integer', 'real')]
with (root / 'exported_countries.csv').open(encoding='utf-8', newline='') as stream:
    reader = csv.DictReader(stream)
    assert reader.fieldnames == ['country_name', 'capital', 'population', 'area']
    rows = list(reader)
assert len(rows) == 20
assert [
    {**row, 'population': int(row['population']), 'area': float(row['area'])}
    for row in rows
] == actual
assert next(row for row in rows if row['country_name'] == 'Antarctica')['capital'] == 'None'
assert any(row['country_name'] == 'Åland' for row in rows)
with Image.open(root / 'population_vs_area.png') as chart:
    assert chart.format == 'PNG' and chart.size == (1620, 1080)
    chart.verify()
print('PASS: final SQLite integrity, 20 exact live-source records, numeric storage types, CSV equality/headers/Unicode/None, genuine 1620x1080 PNG, no synthetic records')
for filename in ['countries.db', 'exported_countries.csv', 'population_vs_area.png']:
    print(f'{filename}: {(root / filename).stat().st_size} bytes')
PY
```

Actual result: the printed **PASS** line, followed by the three file sizes recorded above. The final table was compared in full, rather than accepting a row count alone.

## Permissions and access

Initial DNS/network requests and local server/socket operations were blocked by the execution sandbox. The required dependency installation, live fetching, integration run, final scrape, and local server/client operations succeeded after the specifically needed access was approved. Normal TLS verification remained enabled throughout. **No live-pipeline acceptance check remains blocked.**

## Repository checks before publication

Executed local repository setup:

```bash
git init -b main
git check-ignore .venv countries.db exported_countries.csv population_vs_area.png
```

Results: a local `main` repository was initialized. Ignore checks confirmed that the environment and generated artifacts are excluded from source control. The Git candidate list contained 20 source, documentation, configuration, and fixture files.

The [GitHub Actions workflow](.github/workflows/ci.yml) runs dependency consistency, Ruff lint/format, and the offline tests on Python 3.12. Its official actions are pinned to verified release commit SHAs: [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) and [setup-python v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0). The workflow token has read-only contents permission, and checkout does not persist credentials.

These results precede publication. Check the repository's **Actions** tab for the current GitHub-hosted CI result. [README.md](README.md#sharing-with-your-instructor-on-github) explains how to review and publish the project. The local implementation, offline checks, and genuine live pipeline were verified independently of GitHub publication.
