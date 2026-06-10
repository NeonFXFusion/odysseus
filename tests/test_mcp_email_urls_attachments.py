import json
from email.message import EmailMessage

import pytest

pytest.importorskip("mcp")

import mcp_servers.email_server as es


def _message_bytes(html_body='<a href="https://www.ebay.com/order/track?item=123">Track package</a>'):
    msg = EmailMessage()
    msg["Subject"] = "Your package is now with its carrier!"
    msg["From"] = "eBay <ebay@ebay.com>"
    msg["To"] = "buyer@example.com"
    msg["Date"] = "Wed, 10 Jun 2026 01:34:29 -0700"
    msg["Message-ID"] = "<pkg-123@example.com>"
    msg.set_content("Plain body")
    msg.add_alternative(html_body, subtype="html")
    return msg.as_bytes()


class _FakeImap:
    def __init__(self, raw_message):
        self.raw_message = raw_message
        self.fetch_items = []

    def select(self, folder, readonly=True):
        return "OK", []

    def uid(self, command, *args):
        if command == "SEARCH":
            return "OK", [b"42"]
        if command == "FETCH":
            self.fetch_items.append(args[-1])
            return "OK", [(b"42 (BODY[] {123}", self.raw_message)]
        raise AssertionError(command)

    def logout(self):
        return "OK", []


def test_resolve_account_accepts_display_label_with_email(monkeypatch):
    rows = [{
        "id": "acct-1",
        "name": "neon.uvled@gmail.com",
        "imap_user": "neon.uvled@gmail.com",
        "from_address": "neon.uvled@gmail.com",
        "is_default": 1,
    }]
    monkeypatch.setattr(es, "_list_accounts_raw", lambda: rows)

    assert es._resolve_account("neon.uvled@gmail.com <neon.uvled@gmail.com>")["id"] == "acct-1"
    assert es._resolve_account("eBay Inbox <neon.uvled@gmail.com>")["id"] == "acct-1"


def test_result_account_selector_prefers_email_for_followups():
    item = {
        "_account": "neon.uvled@gmail.com",
        "_account_email": "neon.uvled@gmail.com",
        "_account_id": "acct-1",
    }

    assert es._result_account_selector(item) == "neon.uvled@gmail.com"


def test_extract_email_urls_trims_css_font_declarations():
    result = es._extract_email_urls(
        html_body=(
            "<style>@font-face{src:url(https://ir.ebaystatic.com/font.eot);"
            "src:url(https://ir.ebaystatic.com/font.woff2)format('woff2')}</style>"
            '<a href="https://www.ebay.com/order/track?item=123">Track package</a>'
        )
    )

    assert "https://ir.ebaystatic.com/font.eot" in result["urls"]
    assert all("format(" not in url and "src:url" not in url for url in result["urls"])
    assert result["tracking_candidates"][0]["url"] == "https://www.ebay.com/order/track?item=123"


def test_tracking_candidates_ignore_static_assets_and_pixels():
    result = es._extract_email_urls(
        html_body="""
            <img alt="eBay logo" src="https://secureir.ebaystatic.com/logo.png">
            <img src="https://www.ebayadservices.com/marketingtracking/v1/impress">
            <a href="https://www.ebay.com/order/details?orderid=abc">View order details</a>
        """
    )

    candidate_urls = [detail["url"] for detail in result["tracking_candidates"]]
    assert candidate_urls == ["https://www.ebay.com/order/details?orderid=abc"]


def test_extract_email_urls_reads_html_attrs_and_text():
    result = es._extract_email_urls(
        text_body="Plain link: https://plain.example/path.",
        html_body="""
            <a href="https://html.example/a?x=1&amp;y=2">open</a>
            <a class="btn primary" href="https://button.example/pay">Pay now</a>
            <a href="https://image-link.example"><img alt="Logo link" src="https://cdn.example/logo.png"></a>
            <img alt="Product image" src="https://cdn.example/image.png">
            Visible https://visible.example/ok).
            <a href="javascript:alert(1)">bad</a>
        """,
    )

    assert result["urls"] == [
        "https://plain.example/path",
        "https://html.example/a?x=1&y=2",
        "https://button.example/pay",
        "https://image-link.example",
        "https://cdn.example/logo.png",
        "https://cdn.example/image.png",
        "https://visible.example/ok",
    ]
    assert result["url_details"] == [
        {
            "url": "https://plain.example/path",
            "source": "text",
            "context_type": "standalone",
            "context_text": "",
        },
        {
            "url": "https://html.example/a?x=1&y=2",
            "source": "html",
            "context_type": "a_text",
            "context_text": "open",
        },
        {
            "url": "https://button.example/pay",
            "source": "html",
            "context_type": "button",
            "context_text": "Pay now",
        },
        {
            "url": "https://image-link.example",
            "source": "html",
            "context_type": "alt",
            "context_text": "Logo link",
        },
        {
            "url": "https://cdn.example/logo.png",
            "source": "html",
            "context_type": "alt",
            "context_text": "Logo link",
        },
        {
            "url": "https://cdn.example/image.png",
            "source": "html",
            "context_type": "alt",
            "context_text": "Product image",
        },
        {
            "url": "https://visible.example/ok",
            "source": "html",
            "context_type": "standalone",
            "context_text": "",
        },
    ]


def test_query_wants_email_urls_for_tracking_requests():
    assert es._query_wants_email_urls("eBay package tracking") is True
    assert es._query_wants_email_urls("invoice from EY") is False


def test_format_email_url_lines_uses_tracking_candidates():
    result = es._extract_email_urls(
        html_body='<a href="https://www.ebay.com/order/track?item=123">Track package</a>'
    )

    lines = es._format_email_url_lines(result, indent="   ", max_other=5)

    assert "   Likely tracking URL candidate(s): 1" in lines
    assert "   - https://www.ebay.com/order/track?item=123 (a text: Track package)" in lines


def test_read_email_includes_extracted_url_metadata(monkeypatch):
    fake = _FakeImap(_message_bytes())
    monkeypatch.setattr(es, "_imap_connect", lambda account=None: fake)
    monkeypatch.setattr(es, "_load_config", lambda account=None: {
        "account_name": "Gmail",
        "imap_user": "buyer@example.com",
        "from_address": "buyer@example.com",
        "account_id": "acct-1",
    })

    result = es._read_email(uid="42", account="Gmail")

    assert result["extracted_urls"] == ["https://www.ebay.com/order/track?item=123"]
    assert result["url_count"] == 1
    assert result["tracking_candidates"][0]["url"] == "https://www.ebay.com/order/track?item=123"
    assert result["url_details"][0]["context_text"] == "Track package"


def test_search_emails_can_include_extracted_url_metadata(monkeypatch):
    fake = _FakeImap(_message_bytes())
    monkeypatch.setattr(es, "_imap_connect", lambda account=None: fake)
    monkeypatch.setattr(es, "_load_config", lambda account=None: {
        "account_name": "Gmail",
        "imap_user": "buyer@example.com",
        "from_address": "buyer@example.com",
        "account_id": "acct-1",
    })
    monkeypatch.setattr(es, "_get_cached_summaries", lambda: {})

    results = es._search_emails(
        "eBay package tracking",
        folders=["INBOX"],
        max_results=1,
        account="Gmail",
        include_urls=True,
    )

    assert fake.fetch_items == ["(BODY.PEEK[])"]
    assert results[0]["extracted_urls"] == ["https://www.ebay.com/order/track?item=123"]
    assert results[0]["tracking_candidates"][0]["url"] == "https://www.ebay.com/order/track?item=123"


def test_mcp_email_attachment_resolves_chat_upload_id(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    stored_dir = upload_root / "2026" / "06" / "10"
    stored_dir.mkdir(parents=True)
    upload_id = "0" * 32 + ".txt"
    stored_path = stored_dir / upload_id
    stored_path.write_text("attached", encoding="utf-8")
    (upload_root / "uploads.json").write_text(
        json.dumps({"alice:hash": {"id": upload_id, "path": str(stored_path), "name": "note.txt"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(es, "UPLOAD_DIR", str(upload_root))
    prepared = es._prepare_email_attachments([upload_id])

    assert prepared[0]["path"] == stored_path.resolve()
    assert prepared[0]["filename"] == upload_id
    assert prepared[0]["content_type"] == "text/plain"


def test_mcp_email_attachment_resolves_chat_upload_original_filename(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    stored_dir = upload_root / "2026" / "06" / "10"
    stored_dir.mkdir(parents=True)
    upload_id = "1" * 32 + ".png"
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

    monkeypatch.setattr(es, "UPLOAD_DIR", str(upload_root))
    prepared = es._prepare_email_attachments([{"filename": "janus.png", "path": "janus.png"}])

    assert prepared[0]["path"] == stored_path.resolve()
    assert prepared[0]["filename"] == "janus.png"
    assert prepared[0]["content_type"] == "image/png"
