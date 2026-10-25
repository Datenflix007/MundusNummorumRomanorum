# Roman Coin Atlas

Roman Coin Atlas is a local-first CS50P final project foundation for researching
and cataloguing Roman imperial coin types. Phase 1 deliberately provides only
the application skeleton and shared input-normalization helpers. It does not
import reference data, search OCRE, or store user specimens yet.

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

## Project layout

```text
project.py       Flask entry point and CS50P helper functions
test_project.py  Unit tests for the helper functions
database/        Reserved for local SQLite databases (not committed)
services/        Reserved for application service modules
templates/       Reserved for server-rendered HTML templates
static/          Reserved for CSS, JavaScript, and image assets
tests/           Reserved for additional test modules and fixtures
```

## Data and source policy

Future external reference data will remain separate from user-entered
specimens. External inputs will be treated as untrusted, and each data source
will receive appropriate attribution and licensing review before it is added.
No third-party numismatic records or images are included in this phase.
