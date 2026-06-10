import json

import pytest

pytest.importorskip("mcp")

import mcp_servers.instagram_server as ig


def test_extract_instagram_urls_tracks_package_links():
    result = ig._extract_instagram_urls(
        "Track package: https://carrier.example/track?id=123 and logo https://cdn.example/logo.png"
    )

    assert result["extracted_urls"] == [
        "https://carrier.example/track?id=123",
        "https://cdn.example/logo.png",
    ]
    assert result["tracking_candidates"][0]["url"] == "https://carrier.example/track?id=123"


def test_instagram_account_config_redacts_credentials(monkeypatch, tmp_path):
    config_path = tmp_path / "instagram_accounts.json"
    config_path.write_text(
        json.dumps({
            "accounts": [{
                "id": "main",
                "name": "Main IG",
                "username": "alice",
                "password": "secret",
                "sessionid": "session-secret",
                "is_default": True,
            }]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(ig, "CONFIG_FILE", config_path)
    monkeypatch.setattr(ig, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ig, "_load_integrations_rows", lambda: [])
    monkeypatch.delenv("INSTAGRAM_PRIVATE_USERNAME", raising=False)
    monkeypatch.delenv("INSTAGRAM_USERNAME", raising=False)

    rows = [ig._public_account(row) for row in ig._load_accounts_raw()]

    assert rows == [{
        "id": "main",
        "name": "Main IG",
        "username": "alice",
        "provider": "instagrapi",
        "source": "legacy",
        "integration_id": "",
        "is_default": True,
        "has_password": True,
        "has_sessionid": True,
        "session_file": str((tmp_path / "sessions" / "alice.json").resolve()),
        "proxy_configured": False,
    }]
    assert "secret" not in json.dumps(rows)


def test_instagram_integration_account_config(monkeypatch, tmp_path):
    monkeypatch.setattr(ig, "CONFIG_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(ig, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ig, "_load_integrations_rows", lambda: [{
        "id": "intg_ig",
        "name": "Personal Instagram",
        "provider": "instagram_private",
        "preset": "instagram_private",
        "enabled": 1,
        "base_url": "instagram-private://bob",
        "api_key": json.dumps({"password": "pw", "sessionid": "sid"}),
        "proxy": "http://127.0.0.1:8080",
    }, {
        "id": "disabled",
        "provider": "instagram_private",
        "enabled": 0,
        "username": "disabled",
        "api_key": "secret",
    }])
    monkeypatch.delenv("INSTAGRAM_PRIVATE_USERNAME", raising=False)
    monkeypatch.delenv("INSTAGRAM_USERNAME", raising=False)

    rows = ig._load_accounts_raw()
    public = ig._public_account(rows[0])

    assert len(rows) == 1
    assert rows[0]["id"] == "intg_ig"
    assert rows[0]["username"] == "bob"
    assert rows[0]["password"] == "pw"
    assert rows[0]["sessionid"] == "sid"
    assert rows[0]["proxy"] == "http://127.0.0.1:8080"
    assert public["source"] == "integration"
    assert public["integration_id"] == "intg_ig"
    assert public["has_password"] is True
    assert public["has_sessionid"] is True
    assert "pw" not in json.dumps(public)


def test_instagram_attachment_resolves_chat_upload_original_filename(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    stored_dir = upload_root / "2026" / "06" / "10"
    stored_dir.mkdir(parents=True)
    upload_id = "2" * 32 + ".png"
    stored_path = stored_dir / upload_id
    stored_path.write_bytes(b"png")
    (upload_root / "uploads.json").write_text(
        json.dumps({
            "alice:hash": {
                "id": upload_id,
                "path": str(stored_path),
                "name": "janus.png",
                "original_name": "janus.png",
            }
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(ig, "UPLOAD_DIR", str(upload_root))
    prepared = ig._prepare_attachments([{"filename": "janus.png", "path": "janus.png"}])

    assert prepared[0]["path"] == stored_path.resolve()
    assert prepared[0]["filename"] == "janus.png"
    assert prepared[0]["content_type"] == "image/png"
