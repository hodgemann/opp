---
name: create-opp
description: Create a verifiable Open Prop Protocol package from prop reference images, including composite interaction tagging, owner review, signing, and verification. Use for .opp prop bundles; do not use for OAP actor bundles or generic images alone.
---

# Create an OPP package

Read the repo [README](../../README.md) for CLI flags and clearance behavior.
Given a folder of prop images, identify the base sheet that shows geometry,
materials, and scale. If the choice is uncertain, ask the owner which image is
the base. Treat other composite sheets as interaction sheets; a single sheet may
carry many free-form tags. Do not force a fixed action vocabulary or assume an
instrument-sized prop.

Run `opp draft --images DIR --out SOURCE --id ID --name NAME --base FILE`.
When a local Ollama-compatible vision model is available and the owner wants
automatic tagging, add `--model MODEL`. Inspect every composite sheet, review
the returned tag list and prompt modifier against visible contact and object
states, and edit `SOURCE/manifest.json` as needed. If no local vision model is
available, write the tags manually from the images. The manifest is the review
surface; do not package until the owner has had a chance to correct tags and
clearance. Preserve owner-supplied license and provenance text.

Add public previews only from files the owner has cleared for public sharing.
Record them as `public` sheets; keep originals as `master`. Add any optional
audio, 3D, embedding, or model files to `assets` with a role and clearance.
Every packaged file must be in the manifest. Do not copy assets from MMV or OAP
unless the owner explicitly supplies them for this prop.

Use `opp identity` when a new signing identity is needed. Keep `_private` outside
the package and source folder; set the manifest owner's DID and public key to
the matching values. Run `opp package` with `--sign-key-file` when a key is
available. An unsigned bundle is acceptable when crypto is unavailable or the
owner opts out; report that clearly. Verify with `opp verify --opp FILE`, adding
`--require-signature` for a signed delivery. Import only after successful strict
verification, using `opp import --opp FILE --target DIR`.

When handing a bundle to a host, explain that signature validity and signer
trust are separate. The host should choose an interaction composite by semantic
match to shot intent and fall back to a base sheet. Do not publish or upload the
bundle or create the `open-props` repository without owner authorization.
