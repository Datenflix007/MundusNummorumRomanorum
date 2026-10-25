# External data sources and licensing

## Online Coins of the Roman Empire (OCRE)

The import adapter uses only OCRE endpoints documented at
<https://numismatics.org/ocre/apis>:

- the documented Atom feed at `https://numismatics.org/ocre/feed/` to discover
  a bounded current set of canonical RIC identifiers;
- the documented `getNuds?identifiers=` API at
  `https://numismatics.org/ocre/apis/getNuds` to retrieve canonical NUDS/XML.

Each imported row keeps its OCRE record ID, canonical OCRE URI, OCRE title as
the original reference, maintenance-agency attribution, and the license URI
provided in the source NUDS/XML. The adapter requests a maximum of 200 records
per command and pauses 0.3 seconds between HTTP requests.

OCRE states that its database is available under the Open Database License
(ODbL). Consult the current OCRE terms and the ODbL before redistributing a
derived database. The project imports descriptive metadata only: it does not
download, store, or redistribute remote coin images, whose rights may differ.

## Test fixture

`tests/fixtures/ocre/ric.3.ant.1284A_as.xml` is a captured NUDS/XML response
for the real OCRE record `ric.3.ant.1284A_as`, retrieved on 2026-10-25 from
the documented individual-record XML endpoint. It contains no image file and
is retained solely for deterministic parser tests under the source's ODbL
metadata terms.

## CANOA

CANOA was considered but is intentionally not used in this phase. OCRE's
documented feed and NUDS/XML endpoints already provide both bounded discovery
and canonical type data, so no undocumented CANOA endpoint is assumed.
