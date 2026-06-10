import json

import pytest

pytest.importorskip("mcp")

import mcp_servers.instagram_server as ig


@pytest.fixture(autouse=True)
def _instagram_request_test_defaults(monkeypatch):
    monkeypatch.setattr(ig, "INSTAGRAM_MCP_REMOTE_REQUEST_MIN_INTERVAL_SECONDS", 0.0)
    ig._REMOTE_REQUEST_LOCKS.clear()
    ig._REMOTE_REQUEST_LAST_AT.clear()


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


def test_instagram_message_normalization_includes_media_items(monkeypatch):
    provider = object.__new__(ig.InstagramPrivateProvider)
    msg = {
        "item_id": "m1",
        "thread_id": "t1",
        "user_id": "u1",
        "timestamp": 1_700_000_000,
        "item_type": "media",
        "text": "photo",
        "media": {
            "id": "media1",
            "media_type": 1,
            "thumbnail_url": "https://cdn.example.invalid/photo.jpg",
        },
    }

    normalized = provider._normalize_message(msg, users=[{
        "id": "u1",
        "username": "alice",
        "profile_pic_url": "https://cdn.example.invalid/alice.jpg",
    }])

    assert normalized["media_count"] == 1
    assert normalized["media_items"][0]["kind"] == "image"
    assert normalized["media_items"][0]["image_url"] == "https://cdn.example.invalid/photo.jpg"
    assert normalized["from_username"] == "alice"
    assert normalized["from_profile_pic_url"] == "https://cdn.example.invalid/alice.jpg"


def test_instagram_create_post_uses_photo_upload_for_feed_image(monkeypatch, tmp_path):
    image = tmp_path / "post.jpg"
    image.write_bytes(b"jpg")
    calls = []

    class FakeClient:
        def photo_upload(self, path, caption=""):
            calls.append(("photo_upload", path, caption))
            return {
                "pk": "123",
                "id": "123_456",
                "code": "ABC123",
                "media_type": 1,
                "thumbnail_url": "https://cdn.example.invalid/post.jpg",
                "caption_text": caption,
                "user": {"pk": "456", "username": "alice"},
            }

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"name": "Main IG", "username": "alice"}
    provider.login = lambda: FakeClient()
    monkeypatch.setattr(ig, "_prepare_attachments", lambda attachments: [{
        "path": image,
        "filename": "post.jpg",
        "content_type": "image/jpeg",
    }])

    result = provider.create_post(caption="hello", attachments=["post.jpg"], target="feed")

    assert calls == [("photo_upload", image, "hello")]
    assert result["media"]["url"] == "https://www.instagram.com/p/ABC123/"
    assert result["media"]["caption"] == "hello"


def test_instagram_cache_media_downloads_video_to_local_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(ig, "INSTAGRAM_MEDIA_CACHE_DIR", tmp_path / "instagram_media")
    calls = []

    class FakeClient:
        def video_download(self, media_pk, folder="", overwrite=True):
            calls.append(("video_download", media_pk, folder, overwrite))
            path = folder / "alice_123.mp4"
            path.write_bytes(b"video")
            return path

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"id": "main", "name": "Main IG", "username": "alice"}
    provider.login = lambda: FakeClient()

    result = provider.cache_media({
        "pk": "123",
        "media_type": 2,
        "kind": "video",
        "video_url": "https://cdn.example.invalid/video.mp4",
    })

    assert calls == [("video_download", 123, tmp_path / "instagram_media" / "main", False)]
    assert result["remote_video_url"] == "https://cdn.example.invalid/video.mp4"
    assert result["video_url"].startswith("/api/instagram/media-file/main/")
    assert result["local_video_url"] == result["video_url"]
    assert result["local_path"].endswith("alice_123.mp4")


def test_instagram_cache_media_falls_back_when_download_by_url_has_no_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(ig, "INSTAGRAM_MEDIA_CACHE_DIR", tmp_path / "instagram_media")
    calls = []

    class FakeResponse:
        headers = {"content-type": "video/mp4"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=8192):
            yield b"video"

    class FakeClient:
        request_timeout = 3

        def video_download_by_url(self, url, filename="", folder="", overwrite=True):
            calls.append(("video_download_by_url", url, filename))
            raise IndexError("list index out of range")

        def _send_public_request(self, url, stream=True, timeout=30):
            calls.append(("_send_public_request", url, stream, timeout))
            return FakeResponse()

        def _download_response_to_path(self, response, path):
            path.write_bytes(b"video")
            return path

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"id": "main", "name": "Main IG", "username": "alice"}
    provider.login = lambda: FakeClient()

    result = provider.cache_media({
        "kind": "video",
        "video_url": "https://cdn.example.invalid/signed-url-without-extension?token=1",
    })

    assert calls[0][0] == "video_download_by_url"
    assert calls[1][0] == "_send_public_request"
    assert result["local_path"].endswith(".mp4")
    assert result["video_url"].startswith("/api/instagram/media-file/main/")


def test_instagram_cache_media_force_refetches_existing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(ig, "INSTAGRAM_MEDIA_CACHE_DIR", tmp_path / "instagram_media")
    calls = []

    class FakeResponse:
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=8192):
            yield b"jpg"

    class FakeClient:
        request_timeout = 3

        def _send_public_request(self, url, stream=True, timeout=30):
            calls.append(url)
            return FakeResponse()

        def _download_response_to_path(self, response, path):
            path.write_bytes(b"jpg")
            return path

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"id": "main", "name": "Main IG", "username": "alice"}
    provider.login = lambda: FakeClient()

    item = {
        "pk": "123",
        "media_type": 1,
        "kind": "image",
        "image_url": "https://cdn.example.invalid/photo.jpg?token=1",
    }

    first = provider.cache_media(item)
    second = provider.cache_media(first)
    third = provider.cache_media(second, force=True)

    assert calls == [
        "https://cdn.example.invalid/photo.jpg?token=1",
        "https://cdn.example.invalid/photo.jpg?token=1",
    ]
    assert second["local_path"] == first["local_path"]
    assert third["local_path"] != first["local_path"]


def test_instagram_profile_picture_is_cached_to_local_url(monkeypatch, tmp_path):
    monkeypatch.setattr(ig, "INSTAGRAM_MEDIA_CACHE_DIR", tmp_path / "instagram_media")

    class FakeResponse:
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=8192):
            yield b"jpg"

    class FakeClient:
        request_timeout = 3

        def _send_public_request(self, url, stream=True, timeout=30):
            return FakeResponse()

        def _download_response_to_path(self, response, path):
            path.write_bytes(b"jpg")
            return path

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"id": "main", "name": "Main IG", "username": "alice"}
    provider.login = lambda: FakeClient()

    result = provider.cache_profile_picture_user({
        "id": "100",
        "username": "alice",
        "remote_profile_pic_url": "https://cdn.example.invalid/avatar?token=1",
    })

    assert result["remote_profile_pic_url"] == "https://cdn.example.invalid/avatar?token=1"
    assert result["profile_pic_url"].startswith("/api/instagram/media-file/main/profiles/")
    assert result["profile_pic_url"] == result["local_profile_pic_url"]
    assert result["local_profile_pic_path"].endswith(".jpg")


def test_instagram_profile_picture_cache_reuses_user_entry_without_refetch(monkeypatch, tmp_path):
    monkeypatch.setattr(ig, "INSTAGRAM_MEDIA_CACHE_DIR", tmp_path / "instagram_media")
    calls = []

    class FakeResponse:
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=8192):
            yield b"jpg"

    class FakeClient:
        request_timeout = 3

        def _send_public_request(self, url, stream=True, timeout=30):
            calls.append(url)
            return FakeResponse()

        def _download_response_to_path(self, response, path):
            path.write_bytes(b"jpg")
            return path

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"id": "main", "name": "Main IG", "username": "alice"}
    provider.login = lambda: FakeClient()

    first = provider.cache_profile_picture_user({
        "id": "100",
        "username": "alice",
        "remote_profile_pic_url": "https://cdn.example.invalid/avatar?token=1",
    })
    second = provider.cache_profile_picture_user({
        "id": "100",
        "username": "alice",
        "remote_profile_pic_url": "https://cdn.example.invalid/avatar?token=2",
    })

    assert calls == ["https://cdn.example.invalid/avatar?token=1"]
    assert second["profile_pic_url"] == first["profile_pic_url"]


def test_instagram_profile_picture_force_refetches_same_url(monkeypatch, tmp_path):
    monkeypatch.setattr(ig, "INSTAGRAM_MEDIA_CACHE_DIR", tmp_path / "instagram_media")
    calls = []

    class FakeResponse:
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=8192):
            yield b"jpg"

    class FakeClient:
        request_timeout = 3

        def _send_public_request(self, url, stream=True, timeout=30):
            calls.append(url)
            return FakeResponse()

        def _download_response_to_path(self, response, path):
            path.write_bytes(b"jpg")
            return path

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"id": "main", "name": "Main IG", "username": "alice"}
    provider.login = lambda: FakeClient()

    user = {
        "id": "100",
        "username": "alice",
        "remote_profile_pic_url": "https://cdn.example.invalid/avatar?token=1",
    }

    first = provider.cache_profile_picture_user(user)
    second = provider.cache_profile_picture_user(first, force=True)

    assert calls == [
        "https://cdn.example.invalid/avatar?token=1",
        "https://cdn.example.invalid/avatar?token=1",
    ]
    assert second["profile_pic_url"] != first["profile_pic_url"]


def test_instagram_remote_request_gate_rate_limits_same_account(monkeypatch):
    monkeypatch.setattr(ig, "INSTAGRAM_MCP_REMOTE_REQUEST_MIN_INTERVAL_SECONDS", 2.0)
    times = iter([100.0, 100.0, 100.5, 102.0])
    sleeps = []
    monkeypatch.setattr(ig.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(ig.time, "sleep", lambda seconds: sleeps.append(seconds))

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"id": "main", "name": "Main IG", "username": "alice"}

    assert provider._run_remote_request(lambda: "first") == "first"
    assert provider._run_remote_request(lambda: "second") == "second"
    assert sleeps == [1.5]


def test_instagram_list_stories_uses_reels_tray_when_no_username():
    class FakeClient:
        user_id = "42"

        def get_reels_tray_feed(self, reason="pull_to_refresh"):
            return {
                "tray": [{
                    "id": "100",
                    "user": {
                        "pk": "100",
                        "username": "alice",
                        "profile_pic_url": "https://cdn.example.invalid/alice.jpg",
                    },
                    "items": [{
                        "pk": "900",
                        "id": "900_100",
                        "media_type": 1,
                        "thumbnail_url": "https://cdn.example.invalid/story.jpg",
                    }],
                }],
            }

    provider = object.__new__(ig.InstagramPrivateProvider)
    provider.account = {"id": "main", "name": "Main IG", "username": "alice"}
    provider.login = lambda: FakeClient()

    stories = provider.list_stories()

    assert len(stories) == 1
    assert stories[0]["kind"] == "story"
    assert stories[0]["username"] == "alice"
    assert stories[0]["image_url"] == "https://cdn.example.invalid/story.jpg"
