# OPP v0.1 bundle format

This document specifies the reference implementation's interoperable v0.1
wire format. OPP is general to inanimate props; its current Mondo
Music Video customer does not constrain prop types or interaction tags.

## Archive

An `.opp` file is a ZIP archive with `manifest.json` at its root. Every other
regular file is listed exactly once in `sheets` or `assets`; every listed source
asset has a lowercase hex SHA-256 digest. Member names use forward slashes and
relative paths without empty, `.` or `..` components. Implementations reject
duplicate names and unsafe paths. The reference implementation emits no
directory entries and rejects them on import.

The manifest has these required top-level fields:

| Field | Meaning |
| --- | --- |
| `opp_version` | Exact format version `0.1.0` for this implementation. |
| `kind` | `opp.prop.manifest`. |
| `prop` | `id`, `name`, `owner`; optional descriptive/license fields. |
| `sheets` | One or more sheet records, including at least one base sheet. |
| `assets` | Optional generic asset records with free-form `role`. |
| `signature` | Ed25519 signature record or an unsigned record. |

`prop.id` is a lowercase local identifier. `prop.owner` may carry `name`, OAP
compatible `did`, and `public_key`. A signed package requires both the DID and
public key to match the signing key. This is provenance, not automatic approval.

Each sheet has `file`, `kind` (`base` or `interaction`), `label`, `tags` (an array
of creator-defined strings), `prompt_modifier` (string or null), `clearance`, and
`sha256`. A base sheet shows the object and ideally its scale; an interaction
sheet may be a multi-panel composite showing several grips, contacts, states,
or uses. A sheet can carry many tags. There is no protocol action vocabulary.
Hosts may use the full composite as an anchor and choose matching sheets using
their own semantic model. If no interaction sheet matches, use a base sheet.

Each generic asset has `file`, free-form `role`, `clearance`, and `sha256`.
Examples include audio stems, 3D files, embeddings, and LoRAs. The manifest
lists them without prescribing a renderer or model.

## Clearance and delivery

`public` is for cleared previews; `master` is for high-resolution reference or
training data provided after production approval. The `preview` packaging tier
contains public files only and requires a public base sheet. The `full` tier
contains all files. Both tiers carry the same set of asset records and hashes in
their manifest. A verifier permits omitted master files in a preview, but
requires every public file and every listed hash. The reference implementation
does not watermark, encrypt, or grant clearance itself. Authors must supply the
actual preview images and choose clearance deliberately.

## Signing

OPP uses OAP's Ed25519 DID/key encoding and manifest signing convention.
`did` is `oap:ed25519:` plus the unpadded URL-safe base64 public key. The
signature is Ed25519 over UTF-8 JSON of the manifest **without** its `signature`
member, with keys sorted and compact separators `,` and `:`. The `signature`
object contains `algorithm: "ed25519"`, unpadded URL-safe base64 `value`, and
`signed_at`. An unsigned package uses `value: null`. SHA-256 binds the asset
bytes to the signed manifest. The signature proves control of a key; a studio
separately decides whether to trust that key.

The canonical JSON convention follows OAP's Python reference implementation.
Cross-language implementations should use fixtures before assuming arbitrary
floating-point or Unicode serialization is interoperable. OPP v0.1 manifests
should use ordinary JSON strings, integers, booleans, arrays, objects, and null.

## Example shape

```json
{
  "opp_version": "0.1.0",
  "kind": "opp.prop.manifest",
  "prop": {"id": "example-prop", "name": "Example prop", "owner": {
    "name": "Example Owner", "did": null, "public_key": null}},
  "sheets": [
    {"file": "references/master/base.png", "kind": "base", "label": "Overview",
     "tags": [], "prompt_modifier": null, "clearance": "master", "sha256": "..."},
    {"file": "references/master/handling.png", "kind": "interaction",
     "label": "Handling and opening", "tags": ["handle grip", "opening latch"],
     "prompt_modifier": "Fingers curl around the handle while the thumb presses the latch.",
     "clearance": "master", "sha256": "..."}
  ],
  "assets": [],
  "signature": {"algorithm": "ed25519", "value": null, "signed_at": null}
}
```

`sha256` is shown as `...` for readability; actual bundles require 64 lowercase
hexadecimal characters. The signing and verification code in `opp/core.py` is
the v0.1 reference implementation.
