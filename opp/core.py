"""OPP v0.2 reference packager. Signing mirrors OAP's canonical JSON convention."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import ntpath
import os
import re
import shutil
import tempfile
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.2.0"
CLEARANCE = {"public": 0, "master": 1}
TIERS = {"preview": "public", "full": "master"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    HAS_CRYPTO = True
except ImportError:  # cryptography is optional
    HAS_CRYPTO = False


def _b64e(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(manifest):
    unsigned = dict(manifest)
    unsigned.pop("signature", None)
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")


def generate_identity():
    """Return an OAP-compatible Ed25519 DID/keypair, or unsigned UUID identity."""
    if not HAS_CRYPTO:
        return {"did": f"oap:uuid:{uuid.uuid4()}", "public_key": None, "_private": None}
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
    return {"did": "oap:ed25519:" + _b64e(public), "public_key": _b64e(public), "_private": _b64e(private)}


def _sign(manifest, private_b64):
    if not HAS_CRYPTO:
        raise ValueError("signing requires cryptography")
    key = Ed25519PrivateKey.from_private_bytes(_b64d(private_b64))
    public = _b64e(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    owner = manifest["prop"]["owner"]
    if owner.get("public_key") != public or owner.get("did") != "oap:ed25519:" + public:
        raise ValueError("signing key does not match prop.owner DID and public_key")
    manifest["signature"] = {"algorithm": "ed25519", "value": _b64e(key.sign(_canonical(manifest))),
                             "signed_at": _now()}


def _verify_signature(manifest):
    signature = manifest.get("signature") or {}
    value = signature.get("value")
    if not value:
        return False, "unsigned"
    if signature.get("algorithm") != "ed25519":
        return False, "unsupported signature algorithm"
    if not HAS_CRYPTO:
        return False, "cryptography unavailable"
    owner = manifest["prop"]["owner"]
    public = owner.get("public_key")
    if not public or owner.get("did") != "oap:ed25519:" + public:
        return False, "owner DID/public_key mismatch"
    try:
        Ed25519PublicKey.from_public_bytes(_b64d(public)).verify(_b64d(value), _canonical(manifest))
        return True, "signature valid"
    except (ValueError, TypeError) as exc:
        return False, f"signature invalid: {exc}"
    except Exception:
        return False, "signature invalid"


def _safe_name(name):
    return (isinstance(name, str) and bool(name) and "\\" not in name and "\x00" not in name
            and not name.startswith("/") and not ntpath.splitdrive(name)[0]
            and all(part not in ("", ".", "..") for part in name.split("/")))


def _inside(root, name):
    root = Path(root).resolve()
    target = (root / name).resolve()
    return os.path.commonpath([str(root), str(target)]) == str(root)


def _refs(manifest):
    return manifest["sheets"] + manifest.get("assets", [])


def supports_version(version):
    """Accept v0.1 and v0.2 patch releases, as OAP v0.2 does."""
    return isinstance(version, str) and re.fullmatch(r"0\.(1|2)\.[0-9]+", version) is not None


def _validate(manifest):
    if not isinstance(manifest, dict) or not supports_version(manifest.get("opp_version")) or manifest.get("kind") != "opp.prop.manifest":
        raise ValueError("unsupported OPP manifest/version")
    prop = manifest.get("prop")
    if not isinstance(prop, dict) or not isinstance(prop.get("id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", prop["id"]):
        raise ValueError("prop.id must use lowercase letters, digits, underscores, or hyphens")
    if not isinstance(prop.get("name"), str) or not prop["name"].strip():
        raise ValueError("prop.name is required")
    if not isinstance(prop.get("owner"), dict):
        raise ValueError("prop.owner is required")
    sheets = manifest.get("sheets")
    assets = manifest.get("assets", [])
    if not isinstance(sheets, list) or not isinstance(assets, list) or not sheets:
        raise ValueError("at least one sheet and array assets are required")
    if not any(isinstance(s, dict) and s.get("kind") == "base" for s in sheets):
        raise ValueError("at least one base sheet is required")
    seen = set()
    for ref in _refs(manifest):
        if not isinstance(ref, dict) or not _safe_name(ref.get("file")):
            raise ValueError("unsafe or missing asset path")
        name = ref["file"]
        if name == "manifest.json" or name in seen:
            raise ValueError(f"reserved or duplicate asset path: {name}")
        seen.add(name)
        if ref.get("clearance") not in CLEARANCE:
            raise ValueError(f"invalid clearance: {name}")
        digest = ref.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError(f"invalid SHA-256: {name}")
    for sheet in sheets:
        if sheet.get("kind") not in ("base", "interaction"):
            raise ValueError("sheet kind must be base or interaction")
        if not isinstance(sheet.get("label"), str) or not sheet["label"].strip():
            raise ValueError("sheet label is required")
        if not isinstance(sheet.get("tags", []), list) or any(not isinstance(tag, str) or not tag.strip() for tag in sheet.get("tags", [])):
            raise ValueError("sheet tags must be nonempty strings")
        if sheet.get("prompt_modifier") is not None and not isinstance(sheet["prompt_modifier"], str):
            raise ValueError("prompt_modifier must be a string or null")
    for asset in assets:
        if not isinstance(asset.get("role"), str) or not asset["role"].strip():
            raise ValueError("generic asset role is required")


def _read_manifest(source):
    with (Path(source) / "manifest.json").open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    _validate(manifest)
    return manifest


def select_sheet(manifest, use, clearance="master", score=None):
    """Select an interaction composite, falling back to a base sheet.

    A host may supply its own semantic scorer: score(use, tags, label) -> number.
    The default only matches normalized words, leaving richer semantics to hosts.
    """
    _validate(manifest)
    if clearance not in CLEARANCE:
        raise ValueError("clearance must be public or master")
    sheets = [sheet for sheet in manifest["sheets"] if CLEARANCE[sheet["clearance"]] <= CLEARANCE[clearance]]
    if not sheets:
        return None
    words = set(re.findall(r"[a-z0-9]+", use.lower()))
    def default_score(query, tags, label):
        return len(words & set(re.findall(r"[a-z0-9]+", " ".join(tags + [label]).lower())))
    scorer = score or default_score
    interactions = [sheet for sheet in sheets if sheet["kind"] == "interaction"]
    if interactions:
        ranked = [(scorer(use, sheet.get("tags", []), sheet["label"]), sheet) for sheet in interactions]
        best_value, best_sheet = max(ranked, key=lambda pair: pair[0])
        if best_value > 0:
            return best_sheet
    return next((sheet for sheet in sheets if sheet["kind"] == "base"), None)


def package(source, output, tier="full", sign_key=None):
    """Build a tiered bundle; all listed source assets must exist before signing."""
    if tier not in TIERS:
        raise ValueError("tier must be preview or full")
    source = Path(source).resolve()
    output = Path(output).resolve()
    manifest = _read_manifest(source)
    payload = {}
    for ref in _refs(manifest):
        name = ref["file"]
        if not _inside(source, name):
            raise ValueError(f"asset escapes source: {name}")
        path = source / name
        if not path.is_file():
            raise ValueError(f"missing source asset: {name}")
        data = path.read_bytes()
        ref["sha256"] = _sha256(data)
        if CLEARANCE[ref["clearance"]] <= CLEARANCE[TIERS[tier]]:
            payload[name] = data
    if tier == "preview" and not any(sheet["kind"] == "base" and sheet["clearance"] == "public"
                                     for sheet in manifest["sheets"]):
        raise ValueError("preview tier needs a public base sheet")
    manifest["signature"] = {"algorithm": "ed25519", "value": None, "signed_at": None}
    if sign_key:
        _sign(manifest, sign_key)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for name, data in payload.items():
            archive.writestr(name, data)
    return {"output": str(output), "tier": tier, "included": ["manifest.json", *payload]}


def verify_package(path, strict=True, require_signature=False, trusted_keys=None):
    """Check manifest, paths, hashes, tier completeness and optional signer trust."""
    issues = []
    checked = 0
    signature_valid = False
    signature_message = "not checked"
    trusted = None if trusted_keys is None else False
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise ValueError("duplicate members or missing manifest.json")
            if any(item.is_dir() or not _safe_name(item.filename) for item in members):
                raise ValueError("unsafe or directory member")
            manifest = json.loads(archive.read("manifest.json"))
            _validate(manifest)
            refs = _refs(manifest)
            allowed = {"manifest.json", *(ref["file"] for ref in refs)}
            if strict:
                issues += [f"unlisted member: {name}" for name in names if name not in allowed]
            present = set(names)
            tier = "full" if any(ref["clearance"] == "master" and ref["file"] in present for ref in refs) else "preview"
            if not any(sheet["kind"] == "base" and sheet["file"] in present for sheet in manifest["sheets"]):
                issues.append("base sheet missing from bundle")
            for ref in refs:
                name = ref["file"]
                required = tier == "full" or ref["clearance"] == "public"
                expected = ref.get("sha256")
                if not expected:
                    issues.append(f"missing hash: {name}")
                if name not in present:
                    if required:
                        issues.append(f"missing asset: {name}")
                    continue
                if expected and _sha256(archive.read(name)) != expected:
                    issues.append(f"hash mismatch: {name}")
                checked += 1
            signature_valid, signature_message = _verify_signature(manifest)
            signed = bool((manifest.get("signature") or {}).get("value"))
            if require_signature and not signed:
                issues.append("signature required")
            if signed and not signature_valid:
                issues.append(signature_message)
            if trusted_keys is not None:
                trusted = manifest["prop"]["owner"].get("public_key") in trusted_keys
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        issues.append(f"invalid package: {exc}")
    return {"ok": not issues, "issues": issues, "checked": checked, "signature_valid": signature_valid,
            "signature": signature_message, "owner_trusted": trusted}


def import_package(path, target, require_signature=False, trusted_keys=None):
    result = verify_package(path, strict=True, require_signature=require_signature, trusted_keys=trusted_keys)
    if not result["ok"]:
        return {**result, "extracted": False}
    target = Path(target).resolve()
    if target.exists():
        raise ValueError(f"target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".opp-import-", dir=target.parent))
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                dest = stage / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(name))
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {**result, "extracted": True, "target": str(target)}


def _vlm_tags(image, model, url):
    """Ask a local Ollama-compatible chat endpoint for JSON tags for the whole sheet."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.scheme != "http":
        raise ValueError("VLM URL must be a local HTTP endpoint")
    prompt = ("Examine the complete composite prop reference sheet. Return JSON with keys "
              "tags (a list of multiple concise semantic strings describing every visible use, "
              "grip, contact point, and state) and prompt_modifier (one short physical interaction "
              "sentence or null). Do not invent interactions that are not visible.")
    request = urllib.request.Request(url, data=json.dumps({"model": model, "stream": False,
        "format": "json", "messages": [{"role": "user", "content": prompt,
        "images": [base64.b64encode(Path(image).read_bytes()).decode("ascii")]}]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read())
    analysis = json.loads(result["message"]["content"])
    tags = analysis.get("tags")
    modifier = analysis.get("prompt_modifier")
    if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise ValueError("VLM returned invalid tags")
    if modifier is not None and not isinstance(modifier, str):
        raise ValueError("VLM returned invalid prompt_modifier")
    return tags, modifier


def draft(images, output, prop_id, name, base, owner_name="", model=None,
          vlm_url="http://127.0.0.1:11434/api/chat"):
    """Create an editable source tree from raw images; base is explicit."""
    images = Path(images).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f"draft output already exists: {output}")
    if not images.is_dir():
        raise ValueError("images must be a directory")
    files = sorted(path for path in images.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)
    if not files or base not in [path.name for path in files]:
        raise ValueError("--base must name one image in the input directory")
    if any(path.is_symlink() for path in files):
        raise ValueError("input images must not be symlinks")
    manifest = {"opp_version": VERSION, "kind": "opp.prop.manifest",
        "prop": {"id": prop_id, "name": name, "description": "", "owner": {"name": owner_name,
        "did": None, "public_key": None}, "license": ""}, "sheets": [], "assets": [],
        "signature": {"algorithm": "ed25519", "value": None, "signed_at": None}}
    for path in files:
        kind = "base" if path.name == base else "interaction"
        tags, modifier = (_vlm_tags(path, model, vlm_url) if model and kind == "interaction" else ([], None))
        manifest["sheets"].append({"file": f"references/master/{path.name}", "kind": kind,
            "label": path.stem.replace("_", " "), "tags": tags, "prompt_modifier": modifier,
            "clearance": "master", "sha256": None})
    _validate(manifest)
    try:
        (output / "references" / "master").mkdir(parents=True)
        for path in files:
            shutil.copy2(path, output / "references" / "master" / path.name)
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise
    return {"output": str(output), "sheets": len(files), "needs_review": True}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="opp")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("identity")
    p = sub.add_parser("draft")
    for flag in ("images", "out", "id", "name", "base"):
        p.add_argument("--" + flag, required=True)
    p.add_argument("--owner-name", default="")
    p.add_argument("--model")
    p.add_argument("--vlm-url", default="http://127.0.0.1:11434/api/chat")
    p = sub.add_parser("package")
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tier", choices=list(TIERS), default="full")
    p.add_argument("--sign-key-file")
    for command in ("verify", "import"):
        p = sub.add_parser(command)
        p.add_argument("--opp", required=True)
        p.add_argument("--require-signature", action="store_true")
        p.add_argument("--trusted-keys")
        if command == "import":
            p.add_argument("--target", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "identity":
            result = generate_identity()
        elif args.command == "draft":
            result = draft(args.images, args.out, args.id, args.name, args.base, args.owner_name,
                           args.model, args.vlm_url)
        elif args.command == "package":
            key = Path(args.sign_key_file).read_text(encoding="utf-8").strip() if args.sign_key_file else None
            result = package(args.source, args.out, args.tier, key)
        else:
            keys = json.loads(Path(args.trusted_keys).read_text(encoding="utf-8")) if args.trusted_keys else None
            if keys is not None and (not isinstance(keys, list) or any(not isinstance(k, str) for k in keys)):
                raise ValueError("trusted keys must be a JSON array of public-key strings")
            result = verify_package(args.opp, require_signature=args.require_signature, trusted_keys=keys) if args.command == "verify" else import_package(
                args.opp, args.target, args.require_signature, keys)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok", True) else 1
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"opp: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
