import json
import subprocess
import sys
import wave
import zipfile
from pathlib import Path

import pytest

from opp import clean_asset, supports_version
from opp.core import HAS_CRYPTO, draft, generate_identity, import_package, package, select_sheet, verify_package


def source(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "base.png").write_bytes(b"base image")
    (images / "hands.png").write_bytes(b"interaction image")
    root = tmp_path / "source"
    draft(images, root, "prop-1", "Test prop", "base.png")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["sheets"][1]["tags"] = ["handle grip", "opening latch"]
    preview = root / "references" / "public" / "preview.png"
    preview.parent.mkdir()
    preview.write_bytes(b"cleared preview")
    manifest["sheets"].append({"file": "references/public/preview.png", "kind": "base",
                               "label": "Public overview", "tags": [], "prompt_modifier": None,
                               "clearance": "public", "sha256": None})
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def test_draft_requires_explicit_base_and_avoids_overwrite(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "one.png").write_bytes(b"image")
    with pytest.raises(ValueError, match="--base"):
        draft(images, tmp_path / "draft", "p", "P", "other.png")
    draft(images, tmp_path / "draft", "p", "P", "one.png")
    with pytest.raises(ValueError, match="already exists"):
        draft(images, tmp_path / "draft", "p", "P", "one.png")


def test_preview_full_hashes_import_and_tampering(tmp_path):
    root = source(tmp_path)
    preview = tmp_path / "preview.opp"
    full = tmp_path / "full.opp"
    package(root, preview, "preview")
    package(root, full, "full")
    assert verify_package(preview)["ok"]
    assert verify_package(full)["ok"]
    with zipfile.ZipFile(preview) as archive:
        assert "references/master/base.png" not in archive.namelist()
        assert "references/public/preview.png" in archive.namelist()
        assert archive.read("manifest.json")
    result = import_package(full, tmp_path / "installed")
    assert result["ok"] and result["extracted"]
    assert (tmp_path / "installed" / "references/master/hands.png").read_bytes() == b"interaction image"
    with pytest.raises(ValueError, match="already exists"):
        import_package(full, tmp_path / "installed")

    bad = tmp_path / "bad.opp"
    with zipfile.ZipFile(full) as original, zipfile.ZipFile(bad, "w") as changed:
        for member in original.namelist():
            changed.writestr(member, b"tampered" if member == "references/master/base.png" else original.read(member))
    assert any("hash mismatch" in issue for issue in verify_package(bad)["issues"])
    assert not import_package(bad, tmp_path / "bad-target")["extracted"]
    assert not (tmp_path / "bad-target").exists()


def test_missing_and_unlisted_assets_are_rejected(tmp_path):
    root = source(tmp_path)
    full = tmp_path / "full.opp"
    package(root, full)
    missing = tmp_path / "missing.opp"
    extra = tmp_path / "extra.opp"
    with zipfile.ZipFile(full) as original, zipfile.ZipFile(missing, "w") as changed:
        for name in original.namelist():
            if name != "references/public/preview.png":
                changed.writestr(name, original.read(name))
    assert any("missing asset" in issue for issue in verify_package(missing)["issues"])
    with zipfile.ZipFile(full) as original, zipfile.ZipFile(extra, "w") as changed:
        for name in original.namelist():
            changed.writestr(name, original.read(name))
        changed.writestr("extra.txt", "unlisted")
    assert any("unlisted member" in issue for issue in verify_package(extra)["issues"])


def test_omitted_master_still_needs_hash_and_public_base(tmp_path):
    root = source(tmp_path)
    preview = tmp_path / "preview.opp"
    package(root, preview, "preview")
    altered = tmp_path / "no-hash.opp"
    with zipfile.ZipFile(preview) as original, zipfile.ZipFile(altered, "w") as changed:
        manifest = json.loads(original.read("manifest.json"))
        manifest["sheets"][0]["sha256"] = None
        changed.writestr("manifest.json", json.dumps(manifest))
        changed.writestr("references/public/preview.png", original.read("references/public/preview.png"))
    assert any("missing hash" in issue for issue in verify_package(altered)["issues"])


def test_traversal_and_symlink_source_rejected(tmp_path):
    root = source(tmp_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["assets"] = [{"file": "../outside.txt", "role": "other", "clearance": "master", "sha256": None}]
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="unsafe"):
        package(root, tmp_path / "bad.opp")

    manifest["assets"][0]["file"] = "references/master/link.txt"
    manifest_path.write_text(json.dumps(manifest))
    (tmp_path / "outside.txt").write_bytes(b"private")
    (root / "references/master/link.txt").symlink_to(tmp_path / "outside.txt")
    with pytest.raises(ValueError, match="escapes"):
        package(root, tmp_path / "bad.opp")


@pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography unavailable")
def test_signature_identity_and_trust_are_separate(tmp_path):
    root = source(tmp_path)
    identity = generate_identity()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["prop"]["owner"].update({"did": identity["did"], "public_key": identity["public_key"]})
    manifest_path.write_text(json.dumps(manifest))
    signed = tmp_path / "signed.opp"
    package(root, signed, sign_key=identity["_private"])
    result = verify_package(signed, require_signature=True, trusted_keys=[])
    assert result["ok"] and result["signature_valid"] and result["owner_trusted"] is False
    assert verify_package(signed, trusted_keys=[identity["public_key"]])["owner_trusted"] is True
    with pytest.raises(ValueError, match="does not match"):
        package(root, tmp_path / "wrong.opp", sign_key=generate_identity()["_private"])


def test_unsigned_fallback_when_crypto_unavailable(tmp_path, monkeypatch):
    import opp.core as core
    root = source(tmp_path)
    monkeypatch.setattr(core, "HAS_CRYPTO", False)
    identity = core.generate_identity()
    assert identity["did"].startswith("oap:uuid:") and identity["_private"] is None
    bundle = tmp_path / "unsigned.opp"
    package(root, bundle)
    assert verify_package(bundle)["ok"]
    assert not verify_package(bundle, require_signature=True)["ok"]
    with pytest.raises(ValueError, match="requires cryptography"):
        package(root, tmp_path / "signed.opp", sign_key="fake-key")


def test_vlm_tags_whole_composite_and_are_editable(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    (images / "base.png").write_bytes(b"base")
    (images / "uses.png").write_bytes(b"many uses")
    calls = []
    def fake_tags(path, model, url):
        calls.append(Path(path).name)
        return ["handle grip", "open door", "turn key"], "Hand wraps around handle."
    monkeypatch.setattr("opp.core._vlm_tags", fake_tags)
    root = tmp_path / "source"
    draft(images, root, "car", "Car", "base.png", model="local-vision")
    manifest = json.loads((root / "manifest.json").read_text())
    assert calls == ["uses.png"]
    assert manifest["sheets"][1]["tags"] == ["handle grip", "open door", "turn key"]
    assert manifest["sheets"][1]["prompt_modifier"] == "Hand wraps around handle."


def test_select_sheet_matches_use_or_falls_back_to_base(tmp_path):
    root = source(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    assert select_sheet(manifest, "opening latch")["kind"] == "interaction"
    assert select_sheet(manifest, "drive car")["kind"] == "base"
    assert select_sheet(manifest, "opening latch", clearance="public")["file"] == "references/public/preview.png"
    assert select_sheet(manifest, "car door", score=lambda use, tags, label: 10 if "opening latch" in tags else 0)["kind"] == "interaction"


def test_cli_draft_package_verify_import(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    (images / "base.png").write_bytes(b"base")
    root = tmp_path / "source"
    bundle = tmp_path / "prop.opp"
    target = tmp_path / "imported"
    commands = [
        ["draft", "--images", str(images), "--out", str(root), "--id", "prop", "--name", "Prop", "--base", "base.png"],
        ["package", "--source", str(root), "--out", str(bundle)],
        ["verify", "--opp", str(bundle)],
        ["import", "--opp", str(bundle), "--target", str(target)],
    ]
    for args in commands:
        result = subprocess.run([sys.executable, "-m", "opp", *args], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)
    assert (target / "references/master/base.png").read_bytes() == b"base"


def test_version_compatibility_and_new_drafts(tmp_path):
    root = source(tmp_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["opp_version"] == "0.2.0"
    assert supports_version("0.1.9") and supports_version("0.2.12")
    assert not supports_version("0.3.0") and not supports_version("0.2")
    manifest["opp_version"] = "0.1.0"
    manifest_path.write_text(json.dumps(manifest))
    bundle = tmp_path / "legacy.opp"
    package(root, bundle)
    assert verify_package(bundle)["ok"]
    manifest["opp_version"] = "0.3.0"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="unsupported"):
        package(root, tmp_path / "future.opp")


def test_clean_asset_preserves_pcm_and_png_pixels(tmp_path):
    image = pytest.importorskip("PIL.Image")
    png = tmp_path / "original.png"
    cleaned_png = tmp_path / "cleaned.png"
    pixels = image.new("RGBA", (2, 2), (20, 30, 40, 128))
    # A text chunk should be stripped while transparency and pixels survive.
    from PIL.PngImagePlugin import PngInfo
    metadata = PngInfo()
    metadata.add_text("Comment", "private note")
    pixels.save(png, pnginfo=metadata)
    assert clean_asset(str(png), str(cleaned_png)) == str(cleaned_png)
    with image.open(cleaned_png) as result:
        assert result.tobytes() == pixels.tobytes()
        assert "Comment" not in result.info
    with pytest.raises(ValueError, match="separate output"):
        clean_asset(str(png), str(png))

    wav = tmp_path / "original.wav"
    cleaned_wav = tmp_path / "cleaned.wav"
    frames = b"\x01\x00\x02\x00\x03\x00"
    with wave.open(str(wav), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        stream.writeframes(frames)
    clean_asset(str(wav), str(cleaned_wav))
    with wave.open(str(cleaned_wav), "rb") as stream:
        assert stream.readframes(3) == frames
        assert stream.getparams().framerate == 22050
