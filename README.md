# Roman Coin Atlas

Roman Coin Atlas is a local-first CS50P final project for researching and
cataloguing Roman imperial coin types. It includes a Flask health endpoint,
local SQLite storage, and a bounded import pipeline for verified OCRE reference
types.

## Requirements

- Python 3.12 or later
- Internet access only for installing dependencies (the test suite is local)

## Quickstart for Windows

The easiest way to prepare and launch the application is:

```powershell
.\quickstart.bat
```

The script creates `.venv` when necessary, installs dependencies, runs all
tests, initializes the local SQLite database, and starts Flask at
`http://127.0.0.1:5000`. Stop the local server with `Ctrl+C`.

To perform the same preparation without keeping a server process open, use:

```powershell
.\quickstart.bat --no-serve
```

## Manual setup (step by step)

Follow these steps instead of the Quickstart when you prefer to control each
command separately.

### 1. Create and activate the virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If Python 3.12 is not installed but another Python version newer than 3.12 is,
use `py -3` in the first command.

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`
instead.

### 3. Run the tests

```powershell
python -m pytest
```

The tests use only local code and do not make HTTP requests.

### 4. Initialize the local database

```powershell
python project.py init-db
```

The command is repeatable: it creates missing tables and indexes but does not
import external data.

### 5. Launch the application

```powershell
python project.py serve
```

Flask starts a local development server (normally at
`http://127.0.0.1:5000`). Confirm that it is running without a database by
opening `http://127.0.0.1:5000/health`, which returns:

```json
{"service":"roman-coin-atlas","status":"ok"}
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
