# Mondo Music Video integration notes

Mondo Music Video 1.9 currently stores instrument references as
`mmv.instrument` version 1 records. The current app accepts exactly drums,
bass, guitar, and keyboards; it imports one cleaned PNG per design, preserves
the original bytes locally, records SHA-256, license, and provenance, and uses
the sheet as an extra renderer reference slot. Its instrument code keeps props
separate from OAP actors. OPP preserves that separation and broadens the model
to arbitrary props and multiple base or composite interaction sheets.

The first MMV adapter can map the selected `instrument.json` fields as follows:

| MMV field | OPP location |
| --- | --- |
| `id`, `name`, `description` | `prop.id`, `prop.name`, `prop.description` |
| `license`, `provenance` | `prop.license`, `prop.provenance` |
| cleaned `reference.png` | one `sheets` item with `kind: base` |
| reference SHA-256 | sheet `sha256`, recomputed when packaging |
| source/original image | optional master asset, only if approved for transfer |

An OPP importer in MMV should strictly verify the package before importing,
keep OAP actor verification independent, and store the selected OPP bundle or
its manifest and verified assets in the local private library. Production
previews should bind the chosen sheet hashes to consent and resume checks, as
the current instrument flow already binds its reference bytes. The planner can
choose a composite interaction sheet using shot intent and its free-form tags,
then fall back to a base sheet. Each selected sheet consumes a renderer reference
slot; MMV should account for actor and prop slots together before quoting.

Current MMV has no OPP import, multi-sheet selection, or prop-wide catalog yet.
This document is an integration map, not a claim that MMV supports `.opp` now.
No MMV assets or private library data are copied into this repository.
