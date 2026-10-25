# Roman Coin Atlas

Roman Coin Atlas is a local-first CS50P final project foundation for researching
and cataloguing Roman imperial coin types. It currently provides a Flask health
endpoint, shared input-normalization helpers, and a local SQLite schema. It
does not import reference data or search OCRE yet.

## Requirements

- Python 3.12 or later
- Internet access only for installing dependencies (the test suite is local)

## Installation

Create and activate a virtual environment, then install the project
dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`
instead.

## Run the tests

```powershell
python -m pytest
```

The tests use only local code and do not make HTTP requests.

## Launch the application

```powershell
python project.py
```

Flask starts a local development server (normally at
`http://127.0.0.1:5000`). Confirm that it is running without a database by
opening `http://127.0.0.1:5000/health`, which returns:

```json
{"service":"roman-coin-atlas","status":"ok"}
```

## Initialize the local database

The following command is repeatable: it creates missing tables and indexes but
does not import any external data.

```powershell
python project.py init-db
```

Use a different SQLite file when needed:

```powershell
python project.py init-db --database .\database\catalog.sqlite
```

Dates are stored as integers: BCE years are negative, CE years are positive,
and year zero is invalid. For example, `-27` means 27 BCE and `14` means 14 CE.

`coin_types` contains externally sourced reference records and is intentionally
read-only through the normal specimen-management repository API. `found_coins`
contains user-entered specimens and may have no reference identification at all.
Specimen photographs are held separately in `coin_images`, with `obverse` and
`reverse` side values.

## Import an OCRE pilot catalog

After reviewing the source policy in [docs/SOURCES.md](docs/SOURCES.md), import
up to 200 real OCRE RIC types. The default pilot requests 100 records from
OCRE's documented Atom feed and NUDS/XML API:

```powershell
python project.py import-ocre --limit 100
```

The command is idempotent: a second run retains the original imported metadata
and reports existing canonical OCRE IDs as duplicates. It stores no remote
coin images. If OCRE is unavailable or returns malformed XML, the command exits
with an error rather than claiming a successful import.

## Project layout

```text
project.py       Flask entry point and CS50P helper functions
test_project.py  Unit tests for the helper functions
database/        SQLite schema, repository API, and synthetic test fixtures
services/        External-source adapters and import workflows
templates/       Reserved for server-rendered HTML templates
static/          Reserved for CSS, JavaScript, and image assets
tests/           Repository tests using temporary SQLite databases
```

## Data and source policy

Future external reference data will remain separate from user-entered
specimens. External inputs will be treated as untrusted, and each data source
will receive appropriate attribution and licensing review before it is added.
The fixture records in `database/fixtures.py` are explicitly synthetic test
data, not RIC records or historical claims. No third-party numismatic records
or images are bulk-distributed in this phase. The separate OCRE fixture is a
captured, licensed source response used only for parser tests; see
`docs/SOURCES.md`.
