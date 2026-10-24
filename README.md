# Open Prop Protocol (OPP)

OPP is a file format and Python toolkit for packaging references to inanimate
props. A creative studio can verify the package and choose a reference that
shows how a prop should appear or be used in a shot. Props can range from handheld
objects to vehicles and sets. Instruments in Mondo Music Video are the first
integration target, not a limit on the protocol.

OPP is a sibling to [OAP](https://github.com/hodgemann/oap), the actor protocol.
It uses the same ZIP bundle approach, SHA-256 asset hashes, OAP-style Ed25519
DIDs and manifest signatures, and tiered delivery.

This is a v0.2 reference implementation. The concrete wire format is in
[the format specification](docs/FORMAT.md). The package creation workflow is
also documented as an [agent skill](skills/create-opp/SKILL.md).
See [the v0.2 release notes](docs/RELEASE_NOTES_0.2.md) for compatibility and migration.
The [MMV integration map](docs/MMV_INTEGRATION.md) describes how its current
instrument records can migrate; MMV does not yet consume `.opp` bundles.

## What is in an `.opp` file?

An `.opp` file is a ZIP archive with a `manifest.json` and the referenced files:

```text
red-guitar.opp
├── manifest.json
├── references/public/preview.png       # optional cleared preview
├── references/master/base.png           # object shape, materials, and scale
└── references/master/playing.png        # composite interaction examples
```

Every prop has at least one **base sheet**. **Interaction sheets** can show
several ways to hold or use the prop in one image. Each sheet has a label,
creator-defined tags, and an optional prompt modifier describing physical
contact. The manifest lists every asset with its SHA-256 hash and clearance.
Optional audio, 3D models, LoRAs, and embeddings can be listed with free-form
roles. Owner, license, and provenance information can also be recorded in the
manifest; the tool does not establish that those claims are true.

The usual flow is **draft → review → package → verify → import**. A host then
matches shot intent to an interaction sheet and falls back to a base sheet when
none fits. OPP deliberately has no fixed vocabulary of actions.

## Create a package

Run `pip install -e '.[crypto]'` or use `python -m opp` from this checkout.
An unsigned package works without `cryptography`; signing and signature checking
need the `crypto` extra.

```bash
# Choose the base image explicitly; other images become interaction sheets.
opp draft --images ./raw-prop-images --out ./prop-source \
  --id red-guitar --name 'Red guitar' --base base.png

# Review/edit prop-source/manifest.json before packaging. Add accurate tags,
# descriptive labels, optional prompt_modifier text and provenance/license.
opp package --source ./prop-source --out ./red-guitar.opp --tier full
opp verify --opp ./red-guitar.opp
opp import --opp ./red-guitar.opp --target ./local-props/red-guitar
```

`draft` reads top-level PNG, JPEG, and WebP images. It copies originals into
`references/master/`, makes one base sheet and one interaction sheet per remaining
image. To auto-tag composites, add `--model YOUR_VISION_MODEL` to the **draft**
command when a local Ollama-compatible `/api/chat` endpoint is running.
The model returns a list of tags for the whole composite and an optional prompt
modifier. Review its output: neither tags nor visual accuracy are guaranteed.
The draft manifest is ordinary JSON, so tags can be edited or overridden before
packaging. Add more base sheets, public previews, and generic assets by editing
the manifest and adding their files. No image conversion or watermarking occurs.

### Signing

```bash
opp identity
```

Store `_private` from that output securely outside the source tree in a file.
Set `prop.owner.did` and `prop.owner.public_key` in the draft manifest to the
corresponding values. Then:

```bash
opp package --source ./prop-source --out ./red-guitar-signed.opp \
  --tier full --sign-key-file ./private-key.txt
opp verify --opp ./red-guitar-signed.opp --require-signature
```

The CLI never reads a signing key from the package. A valid signature identifies
the signing key; it does not establish trust in its owner. Pass `--trusted-keys`
with a local JSON array of accepted public keys when the host needs an explicit
trust decision. `owner_trusted` reports that independent decision.

### Clearance

Each asset has `clearance: public` or `clearance: master`. A `preview` package
ships public assets only; a `full` package ships both. The signed manifest always
contains hashes for *all* source assets, so a later full delivery can be compared
to the preview manifest. To create a preview, add at least one actual public
preview image (for example a watermarked, reduced sheet) to the source manifest.
The packager does not invent public clearance for high-resolution originals.
In an editable source manifest, `sha256` can be `null`; `opp package` fills it
for every listed file before writing the bundle.

If an image or audio source may contain metadata you do not want to distribute,
use `opp.clean_asset(source, output)` before adding the cleaned file to the
source tree. It preserves pixels in single-frame, ordinary-depth PNGs and PCM
frames in WAVs while stripping ancillary metadata. PNG cleaning requires the
`images` extra (`pip install -e '.[images]'`). JPEG, WebP, 3D, model, and other
media need a creator-chosen cleaning workflow. Cleaning is explicit and never
part of verification or automatic packaging.

```json
{
  "file": "references/public/preview.png",
  "kind": "base",
  "label": "Watermarked overview",
  "tags": [],
  "prompt_modifier": null,
  "clearance": "public",
  "sha256": null
}
```

Every file in the bundle must be listed under `sheets` or `assets`, including
optional audio, 3D models, LoRAs, and embeddings. Generic assets use a free-form
`role` instead of a fixed media vocabulary. Interaction sheets use a free-form
list of semantic tags, with no standardized action list. A host can match a
requested use to those tags, use the whole composite as a concept anchor, and
fall back to a base sheet when there is no useful interaction match.

The Python helper `select_sheet(manifest, shot_use, clearance="master", score=None)`
offers a basic word match and base-sheet fallback. A host can pass its own semantic
`score(use, tags, label)` function for VLM or embedding matching; no action list
is built into OPP.

## Companion examples

[`opp-props`](https://github.com/hodgemann/opp-props) is the separate example
collection, analogous to OAP's `oap-actors`. It holds signed `.opp` packages of
the first two props, an electric guitar and stage keyboards, each with one
public base sheet. Use it to try `opp verify` and `opp import`, and pin a
release tag or hash rather than `main`. This reference implementation neither
fetches that collection nor trusts it by default; a valid signature identifies
the signing key but does not make that key trusted. No example prop assets are
included in this repository.

## Status and limits

The v0.2 packager provides plain ZIP bundles and two clearance levels. It does
not encrypt master references, generate watermarks, judge whether a VLM tag is
correct, or decide licensing/approval for a production. Those are host or owner
decisions. The full format is intended for studios to consume without depending
on MMV's current four-instrument catalog.

MIT licensed. The manifest signing convention is adapted from OAP's MIT-licensed
reference implementation. MMV's instrument code informed the first use case;
its bundled images and private data are not included.
