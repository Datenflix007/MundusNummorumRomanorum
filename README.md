# Mundus Nummorum Romanorum

#### Video Demo: https://youtu.be/Co8RhIjoL6c

#### Description:

Mundus Nummorum Romanorum (Roman Coin Atlas) is a local-first CS50P final
project for Roman coin identification and numismatic research. It combines a
Flask web application, local SQLite storage, and an import pipeline for
verified Online Coins of the Roman Empire (OCRE) reference types.

## Purpose and research scope

The application helps a researcher compare Roman imperial coin types without
altering the historical source record. The search form and JSON API can match
Latin inscriptions (legends), obverse and reverse descriptions, authorities,
mints, and RIC reference text. They can also narrow results by historical
period, material, denomination, authority, and mint. Every imported type
retains its canonical OCRE ID and a link back to its source record, so search
results remain traceable during numismatic research.

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

## OCRE and RIC reference data

After reviewing the source policy in [docs/SOURCES.md](docs/SOURCES.md), use
the complete import for a searchable OCRE catalog:

```powershell
python project.py import-ocre --full
```

It follows OCRE's own paginated Atom feed through the final server-provided
page, then retrieves each type's canonical NUDS/XML in bounded batches. The
official RDF dump named in OCRE's VoID metadata is a network fallback. This
can take substantial time. The import is resumable and idempotent, so it is
safe to run again after a network interruption.

For a quick local smoke test, the default remains a 100-record pilot from the
documented Atom feed (or supply up to 200 records explicitly):

```powershell
python project.py import-ocre --limit 100
```

The command is idempotent: a second run retains the original imported metadata
and reports existing canonical OCRE IDs as duplicates. It stores no remote
coin images. If OCRE is unavailable or returns malformed XML, the command exits
with an error rather than claiming a successful import.

OCRE supplies the imported numismatic reference data. Its canonical record IDs
and original-reference fields can contain Roman Imperial Coinage (RIC)
references, which the application preserves and searches as source metadata.
The project does not bundle an independent RIC corpus or present the reading
aids as new, citable RIC translations.

## Representative coin images

The detail page can load a small set of representative specimen thumbnails from
the corresponding OCRE record after you explicitly select the image button.
This does not download or store images locally, and no image request is made by
search results or imports. Each image remains hosted by its source institution
and is shown with OCRE's visible credit and a link to the specimen record.
Image rights can differ from OCRE's ODbL data license; review the credited
institution's terms before reuse. See [docs/SOURCES.md](docs/SOURCES.md).

## English and German reading aids

Use the `DE` / `EN` control in the header to choose the display language. Each
result card presents an expansion aid for every available obverse and reverse
legend on its right side. The card also lists both available OCRE image
descriptions separately, rather than choosing one side. English preserves the
imported OCRE descriptions. German output is clearly labelled as a rule-based
reading aid; it never changes the Latin legend or the stored OCRE source text,
and unfamiliar terms intentionally remain in their source language.

## Coin search API

The Python-backed JSON API searches imported reference coin types; it never
changes their historical source text. `GET /api/coins` accepts `q`,
`start_year`, `end_year`, `material`, `denomination`, `authority`, `mint`,
`sort` (`reference`, `authority`, `mint`, `date_start`, or `date_end`), `order`
(`asc` or `desc`), `limit` (1–100), and `page`.

```text
/api/coins?q=roma&material=bronze&start_year=-27&end_year=14&limit=25&page=1
```

Date filters use inclusive interval overlap. A query returns `200` with an
empty `items` list when no type matches, `400` for invalid query values, and
`500` only when SQLite cannot fulfill a request. `GET /api/coins/<id>` returns
one result with its canonical external ID and source URL.

Keyword expressions can combine terms without changing source text:

```text
Vespasian && Pax       # both terms must occur (AND)
Vespasian || Titus     # either term may occur (OR)
```

`&&` has precedence over `||`; parentheses are intentionally not supported.
Terms remain case-insensitive, partial, literal matches, so this is not a
fuzzy or automatic-identification feature.

## Project layout

```text
project.py       Flask entry point and CS50P helper functions
test_project.py  Unit tests for the helper functions
database/        SQLite schema, repository API, and synthetic test fixtures
services/        External-source adapters and import workflows
templates/       Server-rendered search, result, detail, and error templates
static/          CSS, JavaScript, and image assets for the web interface
tests/           Repository tests using temporary SQLite databases
docs/SOURCES.md  OCRE endpoints, provenance, and licensing policy
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

## Design decisions and known limitations

The application is local-first: SQLite keeps the catalog on the researcher's
machine, while OCRE imports are explicit, resumable operations. Imported source
fields are preserved instead of silently normalizing historical text; English
shows the source description, and German provides only a clearly labelled,
rule-based reading aid for legends and frequent image-description terms.

An initialized database starts without imported reference types, so users must
run an OCRE import before catalog searches return external coin data. Importing
OCRE records and requesting representative previews require network access;
the automated tests do not. Representative images remain at their credited
institutions and are neither downloaded nor stored by this project. Finally,
the application is a research and reading aid, not a substitute for a
scholarly attribution, authentication, or an independent RIC edition.
