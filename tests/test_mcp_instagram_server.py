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


def test_instagram_login_prefers_sessionid_over_password(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def login_by_sessionid(self, sessionid):
            calls.append(("sessionid", sessionid))
            return True

        def login(self, username, password):
            calls.append(("password", username, password))
            return True

    monkeypatch.setattr(ig, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ig, "_resolve_account", lambda account=None: {
        "id": "main",
        "name": "Main IG",
        "username": "alice",
        "password": "pw",
        "sessionid": "sid",
    })
    monkeypatch.setattr(ig.InstagramPrivateProvider, "_import_client", lambda self: FakeClient)

    ig.InstagramPrivateProvider().login()

    assert calls == [("sessionid", "sid")]


def test_instagram_login_falls_back_to_password_after_bad_sessionid(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def login_by_sessionid(self, sessionid):
            calls.append(("sessionid", sessionid))
            raise RuntimeError("bad session")

        def login(self, username, password):
            calls.append(("password", username, password))
            return True

    monkeypatch.setattr(ig, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ig, "_resolve_account", lambda account=None: {
        "id": "main",
        "name": "Main IG",
        "username": "alice",
        "password": "pw",
        "sessionid": "sid",
    })
    monkeypatch.setattr(ig.InstagramPrivateProvider, "_import_client", lambda self: FakeClient)

    ig.InstagramPrivateProvider().login()

    assert calls == [("sessionid", "sid"), ("password", "alice", "pw")]


def test_instagram_login_blacklist_error_mentions_sessionid_and_proxy(monkeypatch, tmp_path):
    class FakeClient:
        def login(self, username, password):
            raise RuntimeError(
                "You can log in with your linked Facebook account. "
                "If you are sure that the password is correct, then change your IP address, "
                "because it is added to the blacklist of the Instagram Server"
            )

    monkeypatch.setattr(ig, "SESSION_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ig, "_resolve_account", lambda account=None: {
        "id": "main",
        "name": "Main IG",
        "username": "alice",
        "password": "pw",
        "sessionid": "",
    })
    monkeypatch.setattr(ig.InstagramPrivateProvider, "_import_client", lambda self: FakeClient)

    with pytest.raises(RuntimeError) as excinfo:
        ig.InstagramPrivateProvider().login()

    message = str(excinfo.value)
    assert "sessionid cookie" in message
    assert "residential proxy/new IP" in message


def test_instagrapi_xma_patch_allows_instagram_deep_link_target_url():
    instagrapi = pytest.importorskip("instagrapi")
    _ = instagrapi

    ig._patch_instagrapi_xma_target_url()

    from instagrapi.extractors import extract_media_v1_xma

    media = extract_media_v1_xma({
        "target_url": "instagram://media_viewer?media_id=123&entry_point=direct",
        "title_text": "Shared reel",
        "preview_url": "https://cdn.example.invalid/preview.jpg",
        "preview_url_mime_type": "image/jpeg",
    })

    assert media is not None
    assert media.title == "Shared reel"
    assert str(media.video_url).startswith("https://cdn.example.invalid/preview.jpg")


def test_instagrapi_xma_patch_drops_app_deep_link_without_http_fallback():
    instagrapi = pytest.importorskip("instagrapi")
    _ = instagrapi

    ig._patch_instagrapi_xma_target_url()

    from instagrapi.extractors import extract_media_v1_xma

    assert extract_media_v1_xma({
        "target_url": "instagram://media_viewer?media_id=123&entry_point=direct",
        "title_text": "Shared reel",
    }) is None
