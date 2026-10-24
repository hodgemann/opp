# OPP 0.2.0

OPP v0.2 aligns its version policy and optional media cleanup with OAP v0.2.
It preserves OPP's prop-specific base and interaction sheets, free-form tags,
public/master clearance, Ed25519 signing, and generic assets.

## Changes

- New drafts declare `opp_version: "0.2.0"`; the Python package is 0.2.0.
- Packaging and verification accept `0.1.x` and `0.2.x` manifests. An existing
  v0.1 source keeps its version and signature format. Unknown minor versions
  are rejected; extension fields remain allowed.
- `opp.clean_asset(source, output)` writes a metadata-free PNG or PCM WAV
  before hashing and signing. PNG support uses the optional `images` extra.
  The helper rejects formats or PNG variants it cannot preserve safely.

OPP v0.1 already provided top-level generic assets, strict archive checks,
signature requirements, local trust-key lookup, and overwrite-safe imports.
Those remain part of the v0.2 API; no migration of those fields is needed.

## Migration

Existing `.opp` v0.1 bundles can be verified and imported by v0.2. A source
manifest can stay at v0.1 when packaging for an older consumer; newly drafted
manifests use v0.2. Owners should review tags, clearance, and every cleaned
asset before signing. Cleaning does not happen during verification, and neither
the packager nor the verifier grants clearance or trusts a signer automatically.

No OPP package or repository publication is implied by this local release work.
