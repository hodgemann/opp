# Open Prop Protocol (OPP)

OPP packages visual and other references for inanimate props so a creative studio
can verify their origin and choose the right reference for a shot. It is a sibling
to [OAP](https://github.com/hodgemann/oap): ZIP bundles, SHA-256 asset hashes,
OAP-style Ed25519 DIDs and canonical manifest signatures, and tiered clearance.
Props of any size are supported. Instruments in Mondo Music Video are the first
integration target, not a limit on the protocol.

This is a v0.1 reference implementation. The concrete wire format is in
[the format specification](docs/FORMAT.md). The package creation workflow is
also documented as an [agent skill](skills/create-opp/SKILL.md).
The [MMV integration map](docs/MMV_INTEGRATION.md) describes how its current
instrument records can migrate; MMV does not yet consume `.opp` bundles.

## Create a package

Run `pip install -e '.[crypto]'` or use `python -m opp` from this checkout.
An unsigned package works without `cryptography`; signing and signature checking
need the `crypto` extra.

```bash
# Choose the base image explicitly; other images become interaction sheets.
opp draft --images ./raw-prop-images --out ./prop-source \
  --id red-guitar --name 'Red guitar' --base base.png

# Optionally have a locally running Ollama vision model tag every composite.
opp draft --images ./raw-prop-images --out ./prop-source \
  --id red-guitar --name 'Red guitar' --base base.png --model YOUR_VISION_MODEL

# Review/edit prop-source/manifest.json before packaging. Add accurate tags,
# descriptive labels, optional prompt_modifier text and provenance/license.
opp package --source ./prop-source --out ./red-guitar.opp --tier full
opp verify --opp ./red-guitar.opp
opp import --opp ./red-guitar.opp --target ./local-props/red-guitar
```

`draft` reads top-level PNG, JPEG, and WebP images. It copies originals into
`references/master/`, makes one base sheet and one interaction sheet per remaining
image, and optionally calls a **local** Ollama-compatible `/api/chat` endpoint.
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

`open-props` is the planned separate example collection, analogous to OAP's
`oap-actors`. The owner will supply and approve sample `.opp` files later. This
reference implementation neither fetches that collection nor trusts it by
default. No example prop assets are included here.

## Status and limits

The v0.1 packager provides plain ZIP bundles and two clearance levels. It does
not encrypt master references, generate watermarks, judge whether a VLM tag is
correct, or decide licensing/approval for a production. Those are host or owner
decisions. The full format is intended for studios to consume without depending
on MMV's current four-instrument catalog.

MIT licensed. The manifest signing convention is adapted from OAP's MIT-licensed
reference implementation. MMV's instrument code informed the first use case;
its bundled images and private data are not included.
