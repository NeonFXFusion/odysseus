"""
instagram_server.py

MCP server exposing Instagram private-API tools through an optional
instagrapi provider. This is intentionally shaped like email_server.py:
search/list/read return stable IDs, extracted URL metadata lives on the
message/thread objects, and send tools can use Odysseus chat uploads.
"""

from __future__ import annotations

import asyncio
import html
import json
import mimetypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.constants import DATA_DIR as _DATA_DIR, UPLOAD_DIR


server = Server("instagram")

DATA_DIR = Path(_DATA_DIR)
PRIVATE_DIR = DATA_DIR / "instagram_private"
SESSION_DIR = PRIVATE_DIR / "sessions"
CONFIG_FILE = DATA_DIR / "instagram_accounts.json"
INSTAGRAM_MCP_ATTACHMENT_MAX_BYTES = int(
    os.environ.get("INSTAGRAM_MCP_ATTACHMENT_MAX_BYTES", str(25 * 1024 * 1024))
)
INSTAGRAM_INTEGRATION_PRESETS = {"instagram_private"}


def _clean_url_candidate(value) -> str:
    raw = html.unescape(str(value or "")).strip()
    if not raw:
        return ""
    raw = re.sub(r"[\x00-\x1f\x7f]+", "", raw).strip().strip("<>\"'")
    raw = re.sub(r"[.,;:!?]+$", "", raw)
    while raw.endswith(")") and raw.count(")") > raw.count("("):
        raw = re.sub(r"[.,;:!?]+$", "", raw[:-1])
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw


def _clean_url_context_text(value) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()[:240]


def _url_detail(url, source="text", context_type="standalone", context_text="") -> dict:
    context_text = _clean_url_context_text(context_text)
    if context_type not in {"alt", "button", "a_text", "standalone"}:
        context_type = "standalone"
    if context_type != "standalone" and not context_text:
        context_type = "standalone"
    return {
        "url": url,
        "source": source,
        "context_type": context_type,
        "context_text": context_text,
    }


_STATIC_URL_EXT_RE = re.compile(
    r"\.(?:avif|bmp|css|eot|gif|ico|jpe?g|js|map|png|svg|ttf|webp|woff2?)(?:[?#].*)?$",
    re.IGNORECASE,
)
_LOW_VALUE_URL_RE = re.compile(
    r"\b(?:impress|impression|openpixel|pixel|beacon|logo|unsubscribe|privacy|preferences?)\b",
    re.IGNORECASE,
)
_TRACKING_SIGNAL_RE = re.compile(
    r"\b(?:track|tracking|carrier|shipment|shipping|ship|delivery|delivered|package|parcel|order|"
    r"out\s+for\s+delivery|delivery\s+attempted|view\s+order|order\s+details)\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')


def _is_static_or_pixel_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    if _STATIC_URL_EXT_RE.search(parsed.path or ""):
        return True
    if _LOW_VALUE_URL_RE.search((parsed.netloc or "") + (parsed.path or "")):
        return True
    return False


def _extract_url_details_from_text(text: str | None, *, context_text: str = "") -> list[dict]:
    if not isinstance(text, str) or not text:
        return []
    try:
        from src.chat_helpers import extract_urls as _extract_urls
        urls = _extract_urls(text)
    except Exception:
        urls = _URL_RE.findall(text)
    details = []
    seen = set()
    for value in urls:
        url = _clean_url_candidate(value)
        if not url or url in seen:
            continue
        seen.add(url)
        details.append(_url_detail(url, "text", "standalone", context_text))
    return details


def _tracking_url_score(detail: dict) -> int:
    url = str((detail or {}).get("url") or "")
    if not url or _is_static_or_pixel_url(url):
        return 0
    parsed = urlparse(url)
    context = str((detail or {}).get("context_text") or "")
    haystack = " ".join([parsed.netloc, parsed.path, parsed.query, context])
    score = 0
    if _TRACKING_SIGNAL_RE.search(haystack):
        score += 5
    if re.search(r"\b(?:track|tracking|shipment|delivery|package|carrier)\b", haystack, re.IGNORECASE):
        score += 4
    if (detail or {}).get("context_type") in {"button", "a_text"}:
        score += 2
    if _LOW_VALUE_URL_RE.search(haystack):
        score -= 5
    return max(score, 0)


def _tracking_url_candidates(details: list[dict], limit: int = 8) -> list[dict]:
    scored = []
    for index, detail in enumerate(details or []):
        score = _tracking_url_score(detail)
        if score > 0:
            scored.append((score, -index, detail))
    scored.sort(reverse=True)
    return [detail for _score, _neg_index, detail in scored[:limit]]


def _extract_instagram_urls(text: str | None = None, extra_details: list[dict] | None = None) -> dict:
    by_url = {}
    order = []
    for detail in [*_extract_url_details_from_text(text), *(extra_details or [])]:
        url = _clean_url_candidate((detail or {}).get("url"))
        if not url:
            continue
        clean = _url_detail(
            url,
            (detail or {}).get("source", "text"),
            (detail or {}).get("context_type", "standalone"),
            (detail or {}).get("context_text", ""),
        )
        if url not in by_url:
            by_url[url] = clean
            order.append(url)
        elif clean.get("context_text") and not by_url[url].get("context_text"):
            by_url[url] = clean
    details = [by_url[url] for url in order]
    urls = [d["url"] for d in details]
    return {
        "urls": urls,
        "count": len(urls),
        "extracted_urls": urls,
        "url_count": len(urls),
        "url_details": details,
        "tracking_candidates": _tracking_url_candidates(details),
    }


def _format_url_detail_context(detail: dict) -> str:
    context_type = (detail or {}).get("context_type") or "standalone"
    context_text = _clean_url_context_text((detail or {}).get("context_text") or "")
    if context_type == "alt" and context_text:
        return f"alt: {context_text}"
    if context_type == "button" and context_text:
        return f"button: {context_text}"
    if context_type == "a_text" and context_text:
        return f"a text: {context_text}"
    return "standalone url"


def _format_url_lines(result: dict, *, indent: str = "", max_other: int = 40) -> list[str]:
    details = (result or {}).get("url_details") or [
        _url_detail(url, "text", "standalone", "")
        for url in ((result or {}).get("urls") or (result or {}).get("extracted_urls") or [])
    ]
    candidates = (result or {}).get("tracking_candidates") or []
    if not details and not candidates:
        return []
    lines = []
    candidate_urls = {d.get("url") for d in candidates}
    if candidates:
        lines.append(f"{indent}Likely tracking URL candidate(s): {len(candidates)}")
        lines.extend(f"{indent}- {d.get('url')} ({_format_url_detail_context(d)})" for d in candidates)
    other = [
        d for d in details
        if d.get("url") not in candidate_urls and not _is_static_or_pixel_url(d.get("url", ""))
    ]
    static_omitted = len([
        d for d in details
        if d.get("url") not in candidate_urls and _is_static_or_pixel_url(d.get("url", ""))
    ])
    lines.append(f"{indent}Found {len(details)} URL(s):")
    if candidates:
        lines.append(f"{indent}Other non-static URL(s): {len(other)}")
    else:
        lines.append(f"{indent}No obvious tracking URL candidate was detected; listing non-static URLs.")
    lines.extend(f"{indent}- {d.get('url')} ({_format_url_detail_context(d)})" for d in other[:max_other])
    if len(other) > max_other:
        lines.append(f"{indent}... {len(other) - max_other} more non-static URL(s) omitted")
    if static_omitted:
        lines.append(f"{indent}Omitted {static_omitted} static asset/pixel URL(s).")
    return lines


def _coerce_limit(value, default=20, minimum=1, maximum=100) -> int:
    try:
        num = int(value)
    except Exception:
        num = default
    return max(minimum, min(maximum, num))


def _obj_get(obj, *names, default=None):
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj.get(name)
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _obj_to_dict(obj) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for method in ("model_dump", "dict"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    data = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if not callable(value):
            data[name] = value
    return data


def _format_timestamp(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        num = float(value)
        if num > 10_000_000_000:
            num = num / 1000.0
        return datetime.fromtimestamp(num).isoformat()
    except Exception:
        return str(value)


def _preview(text: str, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def _config_value(row: dict, key: str, env_key: str | None = None) -> str:
    value = row.get(key)
    if value:
        return str(value)
    ref = row.get(f"{key}_env")
    if ref:
        return os.environ.get(str(ref), "")
    if env_key:
        return os.environ.get(env_key, "")
    return ""


def _instagram_setup_hint() -> str:
    return (
        "No Instagram private API account configured. Add one in "
        "Settings > Integrations > Add > Instagram."
    )


def _instagram_install_hint() -> str:
    return (
        "instagrapi is not installed in this runtime. Rebuild/reinstall with "
        "`pip install -r requirements.txt` so the default Instagram Private API "
        "integration can log in."
    )


def _instagram_login_hint(exc: Exception, *, method: str) -> RuntimeError:
    detail = str(exc or "").strip() or exc.__class__.__name__
    lower = detail.lower()
    if "facebook" in lower or "blacklist" in lower or "challenge" in lower or "checkpoint" in lower:
        hint = (
            "Instagram rejected private API password login. This is not an official API-key issue. "
            "Log in in a browser/app and approve any challenge, then paste a fresh sessionid cookie "
            "into Settings > Integrations > Instagram Private API, or configure a residential proxy/new IP."
        )
    elif method == "session ID":
        hint = (
            "Instagram rejected the session ID. Paste a fresh sessionid cookie from a browser where "
            "this account is already logged in, or remove the session ID and try password login."
        )
    else:
        hint = (
            "Instagram rejected private API login. Try a fresh sessionid cookie in Settings > "
            "Integrations > Instagram Private API, or configure the Proxy field."
        )
    return RuntimeError(f"{detail} {hint}")


def _http_urlish(value) -> str:
    text = str(value or "").strip()
    return text if re.match(r"^https?://", text, flags=re.IGNORECASE) else ""


def _patch_instagrapi_xma_target_url():
    """Allow Instagram app deep links in XMA shares without crashing instagrapi.

    instagrapi 2.9 maps XMA `target_url` to MediaXma.video_url, which is typed
    as Pydantic HttpUrl. Instagram sometimes sends app-only deep links such as
    `instagram://media_viewer?...`; preserving those as raw_xma is fine, but
    validating them as http(s) URLs breaks thread reads entirely.
    """
    try:
        import instagrapi.extractors as extractors
        from instagrapi.types import MediaXma
    except Exception:
        return
    original = getattr(extractors, "extract_media_v1_xma", None)
    if not callable(original) or getattr(original, "_odysseus_xma_patch", False):
        return

    def _safe_extract_media_v1_xma(data):
        media = dict(data or {})
        target_url = _http_urlish(media.get("target_url"))
        if target_url:
            return original(data)

        fallback_url = (
            _http_urlish(media.get("preview_url"))
            or _http_urlish(media.get("header_icon_url"))
            or _http_urlish(media.get("preview_image_url"))
        )
        if not fallback_url:
            return None
        return MediaXma(
            video_url=fallback_url,
            title=media.get("title_text", ""),
            preview_url=media.get("preview_url", ""),
            preview_url_mime_type=media.get("preview_url_mime_type", ""),
            header_icon_url=media.get("header_icon_url") or None,
            header_icon_width=media.get("header_icon_width", 0),
            header_icon_height=media.get("header_icon_height", 0),
            header_title_text=media.get("header_title_text", ""),
            preview_media_fbid=media.get("preview_media_fbid", ""),
        )

    _safe_extract_media_v1_xma._odysseus_xma_patch = True
    extractors.extract_media_v1_xma = _safe_extract_media_v1_xma


def _load_integrations_rows() -> list[dict]:
    try:
        from src.integrations import load_integrations
        rows = load_integrations()
    except Exception:
        return []
    return [row for row in rows if isinstance(row, dict)]


def _secret_blob(row: dict) -> dict:
    raw = row.get("api_key") or ""
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {"password": text}
    if isinstance(parsed, dict):
        return parsed
    return {"password": text}


def _username_from_integration(row: dict, secret: dict) -> str:
    for key in ("username", "account_username", "instagram_username"):
        value = row.get(key) or secret.get(key)
        if value:
            return str(value).strip().lstrip("@")
    raw_url = str(row.get("base_url") or "").strip()
    if raw_url:
        parsed = urlparse(raw_url)
        if parsed.scheme in {"instagram-private", "instagram"}:
            value = f"{parsed.netloc}{parsed.path}".strip("/")
            if value:
                return value.lstrip("@")
    return ""


def _load_integration_accounts() -> list[dict]:
    accounts = []
    for index, row in enumerate(_load_integrations_rows()):
        preset = str(row.get("preset") or "").strip().lower()
        provider = str(row.get("provider") or "").strip().lower()
        if preset not in INSTAGRAM_INTEGRATION_PRESETS and provider not in INSTAGRAM_INTEGRATION_PRESETS:
            continue
        enabled = row.get("enabled", True)
        if enabled is False or enabled == 0 or str(enabled).strip().lower() in {"0", "false", "no", "off"}:
            continue
        secret = _secret_blob(row)
        username = _username_from_integration(row, secret)
        account_id = str(row.get("id") or username or f"integration-{index + 1}")
        accounts.append({
            "id": account_id,
            "name": str(row.get("name") or username or "Instagram"),
            "username": username,
            "password": str(row.get("password") or secret.get("password") or ""),
            "sessionid": str(
                row.get("sessionid")
                or row.get("session_id")
                or secret.get("sessionid")
                or secret.get("session_id")
                or ""
            ),
            "session_file": str(row.get("session_file") or secret.get("session_file") or ""),
            "proxy": str(row.get("proxy") or secret.get("proxy") or ""),
            "is_default": bool(row.get("is_default") or not accounts),
            "_integration_id": account_id,
            "_source": "integration",
        })
    return accounts


def _load_accounts_raw() -> list[dict]:
    rows = _load_integration_accounts()
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = data.get("accounts") or [data]
            if isinstance(data, list):
                rows.extend(item for item in data if isinstance(item, dict))
        except Exception:
            pass

    env_username = os.environ.get("INSTAGRAM_PRIVATE_USERNAME") or os.environ.get("INSTAGRAM_USERNAME")
    if env_username:
        rows.append({
            "id": os.environ.get("INSTAGRAM_PRIVATE_ACCOUNT_ID") or "default",
            "name": os.environ.get("INSTAGRAM_PRIVATE_ACCOUNT_NAME") or env_username,
            "username": env_username,
            "password": os.environ.get("INSTAGRAM_PRIVATE_PASSWORD") or os.environ.get("INSTAGRAM_PASSWORD") or "",
            "sessionid": os.environ.get("INSTAGRAM_PRIVATE_SESSIONID") or os.environ.get("INSTAGRAM_SESSIONID") or "",
            "session_file": os.environ.get("INSTAGRAM_PRIVATE_SESSION_FILE") or "",
            "proxy": os.environ.get("INSTAGRAM_PRIVATE_PROXY") or os.environ.get("INSTAGRAM_PROXY") or "",
            "is_default": True,
        })

    normalized = []
    seen = set()
    for index, row in enumerate(rows):
        username = _config_value(row, "username")
        account_id = str(row.get("id") or row.get("name") or username or f"account-{index + 1}")
        if account_id in seen:
            continue
        seen.add(account_id)
        normalized.append({
            **row,
            "id": account_id,
            "name": str(row.get("name") or username or account_id),
            "username": username,
            "is_default": bool(row.get("is_default") or (not normalized)),
        })
    return normalized


def _public_account(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "username": row.get("username"),
        "provider": "instagrapi",
        "is_default": bool(row.get("is_default")),
        "has_password": bool(_config_value(row, "password")),
        "has_sessionid": bool(_config_value(row, "sessionid")),
        "session_file": str(_session_file_for(row)),
        "proxy_configured": bool(_config_value(row, "proxy")),
        "integration_id": row.get("_integration_id") or "",
        "source": row.get("_source") or "legacy",
    }


def _resolve_account(selector=None) -> dict:
    rows = _load_accounts_raw()
    if not rows:
        raise RuntimeError(_instagram_setup_hint())
    if not selector:
        for row in rows:
            if row.get("is_default"):
                return row
        return rows[0]
    wanted = str(selector).strip().lower()
    for row in rows:
        fields = [row.get("id"), row.get("name"), row.get("username")]
        if wanted in {str(v or "").strip().lower() for v in fields}:
            return row
    raise RuntimeError(f"Instagram account not found: {selector}")


def _session_file_for(row: dict) -> Path:
    configured = _config_value(row, "session_file")
    if configured:
        return Path(configured).expanduser().resolve()
    safe = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        str(row.get("_integration_id") or row.get("username") or row.get("id") or "default"),
    )
    return (SESSION_DIR / f"{safe}.json").resolve()


class InstagramPrivateProvider:
    """Thin instagrapi wrapper with stable Odysseus-shaped return objects."""

    def __init__(self, account=None):
        self.account = _resolve_account(account)
        self.client = None

    def _import_client(self):
        try:
            _patch_instagrapi_xma_target_url()
            from instagrapi import Client
            return Client
        except ModuleNotFoundError as exc:
            raise RuntimeError(_instagram_install_hint()) from exc

    def login(self):
        if self.client is not None:
            return self.client
        Client = self._import_client()
        cl = Client()
        proxy = _config_value(self.account, "proxy")
        if proxy and hasattr(cl, "set_proxy"):
            cl.set_proxy(proxy)

        username = _config_value(self.account, "username")
        password = _config_value(self.account, "password")
        sessionid = _config_value(self.account, "sessionid")
        session_file = _session_file_for(self.account)
        if session_file.exists() and hasattr(cl, "load_settings"):
            try:
                cl.load_settings(str(session_file))
            except Exception:
                pass

        attempts = []
        if sessionid and hasattr(cl, "login_by_sessionid"):
            attempts.append(("session ID", lambda: cl.login_by_sessionid(sessionid)))
        if username and password:
            attempts.append(("password", lambda: cl.login(username, password)))
        if not attempts:
            raise RuntimeError(
                f"Instagram account `{self.account.get('name')}` needs password or sessionid credentials."
            )
        last_error = None
        for method, attempt in attempts:
            try:
                ok = attempt()
                if ok is False:
                    raise RuntimeError(f"{method} login returned false")
                last_error = None
                break
            except Exception as exc:
                last_error = _instagram_login_hint(exc, method=method)
                if method == "session ID" and username and password:
                    continue
                raise last_error
        if last_error is not None:
            raise last_error

        if hasattr(cl, "dump_settings"):
            try:
                session_file.parent.mkdir(parents=True, exist_ok=True)
                cl.dump_settings(str(session_file))
                try:
                    os.chmod(session_file, 0o600)
                except Exception:
                    pass
            except Exception:
                pass
        self.client = cl
        return cl

    def account_label(self) -> str:
        username = self.account.get("username") or ""
        return f"{self.account.get('name') or username} ({username})" if username else str(self.account.get("name"))

    def list_threads(self, amount=20) -> list[dict]:
        cl = self.login()
        threads = cl.direct_threads(amount=_coerce_limit(amount, default=20, maximum=100))
        return [self._normalize_thread(thread) for thread in threads or []]

    def read_thread(self, thread_id: str, amount=20) -> dict:
        cl = self.login()
        thread = None
        if hasattr(cl, "direct_thread"):
            try:
                thread = cl.direct_thread(thread_id, amount=_coerce_limit(amount, default=20, maximum=100))
            except TypeError:
                thread = cl.direct_thread(thread_id)
        if thread is None:
            for item in cl.direct_threads(amount=100) or []:
                if str(_obj_get(item, "id", "thread_id", "pk", default="")) == str(thread_id):
                    thread = item
                    break
        if thread is None:
            raise RuntimeError(f"Instagram thread not found: {thread_id}")
        return self._normalize_thread(thread, include_messages=True)

    def search_messages(self, query: str, max_threads=20, max_messages_per_thread=30) -> list[dict]:
        needle = str(query or "").strip().lower()
        if not needle:
            return []
        out = []
        for thread in self.list_threads(amount=max_threads):
            full = thread
            try:
                full = self.read_thread(thread["thread_id"], amount=max_messages_per_thread)
            except Exception:
                pass
            thread_haystack = " ".join([
                full.get("thread_title", ""),
                " ".join(user.get("username", "") for user in full.get("users", [])),
            ]).lower()
            for msg in full.get("messages", []):
                haystack = " ".join([
                    thread_haystack,
                    msg.get("text", ""),
                    msg.get("from_username", ""),
                    msg.get("item_type", ""),
                ]).lower()
                if needle in haystack:
                    out.append({
                        **msg,
                        "thread_id": full.get("thread_id"),
                        "thread_title": full.get("thread_title"),
                        "account": self.account.get("name"),
                        "account_username": self.account.get("username"),
                    })
        return out

    def send_message(self, text: str, *, thread_id=None, username=None, user_id=None, attachments=None) -> dict:
        cl = self.login()
        text = str(text or "")
        if not text and not attachments:
            raise RuntimeError("Message text or attachments are required")
        thread_ids, user_ids = self._recipient_args(cl, thread_id=thread_id, username=username, user_id=user_id)
        sent = None
        if text:
            sent = cl.direct_send(text, thread_ids=thread_ids or None, user_ids=user_ids or None)
        sent_attachments = []
        for item in _prepare_attachments(attachments or []):
            method = "direct_send_video" if str(item.get("content_type", "")).startswith("video/") else "direct_send_photo"
            fn = getattr(cl, method, None)
            if not callable(fn):
                raise RuntimeError(f"instagrapi client does not support {method}")
            sent = fn(str(item["path"]), thread_ids=thread_ids or None, user_ids=user_ids or None)
            sent_attachments.append({
                "filename": item["filename"],
                "path": str(item["path"]),
                "content_type": item["content_type"],
            })
        return {
            "ok": True,
            "account": self.account.get("name"),
            "account_username": self.account.get("username"),
            "thread_id": thread_id,
            "username": username,
            "user_id": user_id,
            "message_id": str(_obj_get(sent, "id", "item_id", "pk", default="")) if sent is not None else "",
            "attachments": sent_attachments,
        }

    def _recipient_args(self, cl, *, thread_id=None, username=None, user_id=None) -> tuple[list[str], list[str]]:
        thread_ids = [str(thread_id)] if thread_id else []
        user_ids = [str(user_id)] if user_id else []
        if username:
            if not hasattr(cl, "user_id_from_username"):
                raise RuntimeError("instagrapi client cannot resolve username recipients")
            user_ids.append(str(cl.user_id_from_username(str(username).lstrip("@"))))
        if not thread_ids and not user_ids:
            raise RuntimeError("Provide thread_id, username, or user_id")
        return thread_ids, user_ids

    def _normalize_thread(self, thread, *, include_messages=True) -> dict:
        users = []
        for user in _obj_get(thread, "users", default=[]) or []:
            users.append({
                "id": str(_obj_get(user, "pk", "id", "user_id", default="")),
                "username": str(_obj_get(user, "username", default="")),
                "full_name": str(_obj_get(user, "full_name", default="")),
            })
        messages = []
        if include_messages:
            messages = [self._normalize_message(msg, users=users) for msg in (_obj_get(thread, "messages", default=[]) or [])]
        url_info = _merge_url_info([m for m in messages])
        return {
            "thread_id": str(_obj_get(thread, "id", "thread_id", "pk", default="")),
            "thread_title": str(_obj_get(thread, "thread_title", "title", default="")) or _thread_title_from_users(users),
            "users": users,
            "last_activity_at": _format_timestamp(_obj_get(thread, "last_activity_at", "last_permanent_item", default="")),
            "is_seen": bool(_obj_get(thread, "is_seen", default=False)),
            "messages": messages,
            **url_info,
        }

    def _normalize_message(self, msg, *, users=None) -> dict:
        data = _obj_to_dict(msg)
        text = str(_obj_get(msg, "text", default="") or "")
        extra_details = _link_details_from_message_dict(data)
        url_info = _extract_instagram_urls(text, extra_details=extra_details)
        user_id = str(_obj_get(msg, "user_id", default="") or "")
        username = _username_for_id(user_id, users or [])
        return {
            "message_id": str(_obj_get(msg, "id", "item_id", "client_context", default="")),
            "thread_id": str(_obj_get(msg, "thread_id", default="")),
            "from_user_id": user_id,
            "from_username": username,
            "timestamp": _format_timestamp(_obj_get(msg, "timestamp", "created_at", default="")),
            "item_type": str(_obj_get(msg, "item_type", "type", default="")),
            "text": text,
            "raw_type": type(msg).__name__,
            **url_info,
        }


def _thread_title_from_users(users: list[dict]) -> str:
    names = [u.get("username") or u.get("full_name") for u in users if u.get("username") or u.get("full_name")]
    return ", ".join(names[:4])


def _username_for_id(user_id: str, users: list[dict]) -> str:
    for user in users or []:
        if str(user.get("id") or "") == str(user_id):
            return str(user.get("username") or "")
    return ""


def _link_details_from_message_dict(data: dict) -> list[dict]:
    details = []
    for key in ("link", "reel_share", "media_share", "clip", "xma_share"):
        value = data.get(key)
        if not value:
            continue
        value_dict = _obj_to_dict(value)
        for url_key in ("url", "link_url", "web_uri", "permalink", "external_url"):
            url = value_dict.get(url_key)
            if url:
                label = value_dict.get("title") or value_dict.get("text") or value_dict.get("name") or key
                details.append(_url_detail(url, "instagram", "a_text", label))
    return details


def _merge_url_info(messages: list[dict]) -> dict:
    details = []
    for msg in messages or []:
        details.extend(msg.get("url_details") or [])
    info = _extract_instagram_urls("", extra_details=details)
    return {
        "extracted_urls": info["extracted_urls"],
        "url_count": info["url_count"],
        "url_details": info["url_details"],
        "tracking_candidates": info["tracking_candidates"],
    }


def _is_under_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _chat_upload_root() -> Path:
    return Path(UPLOAD_DIR).resolve()


def _find_chat_upload_path(upload_id: str) -> Path | None:
    upload_id = Path(str(upload_id or "").strip()).name
    if not upload_id:
        return None
    root = _chat_upload_root()
    index_path = root / "uploads.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(index, dict):
                for info in index.values():
                    if not isinstance(info, dict):
                        continue
                    names = {
                        str(info.get("id") or ""),
                        Path(str(info.get("path") or "")).name,
                        str(info.get("name") or ""),
                        str(info.get("original_name") or ""),
                        str(info.get("filename") or ""),
                    }
                    if upload_id not in names:
                        continue
                    stored = info.get("path")
                    if stored:
                        path = Path(stored).expanduser().resolve()
                        if path.exists() and path.is_file() and _is_under_path(path, root):
                            return path
        except Exception:
            pass
    if re.fullmatch(r"[0-9a-fA-F]{32}(?:\.[A-Za-z0-9]+)?", upload_id):
        direct = (root / upload_id).resolve()
        if direct.exists() and direct.is_file() and _is_under_path(direct, root):
            return direct
    try:
        for path in root.rglob(upload_id):
            resolved = path.resolve()
            if resolved.is_file() and _is_under_path(resolved, root):
                return resolved
    except Exception:
        pass
    return None


def _allowed_attachment_roots() -> list[Path]:
    roots = [Path(UPLOAD_DIR), Path("/tmp")]
    extra = os.environ.get("INSTAGRAM_MCP_ATTACHMENT_ROOTS", "")
    for part in extra.split(os.pathsep):
        if part.strip():
            roots.append(Path(part.strip()))
    return [p.expanduser().resolve() for p in roots]


def _resolve_attachment_path(value) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Attachment path is empty")
    upload = _find_chat_upload_path(raw)
    if upload:
        return upload
    path = Path(raw).expanduser()
    if not path.is_absolute():
        upload = _find_chat_upload_path(path.name)
        if upload:
            return upload
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Attachment not found: {raw}")
    roots = _allowed_attachment_roots()
    if not any(_is_under_path(path, root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise PermissionError(
            f"Attachment path is outside allowed Instagram MCP roots. Allowed roots: {allowed}."
        )
    return path


def _prepare_attachments(attachments) -> list[dict]:
    prepared = []
    total_size = 0
    for item in attachments or []:
        if isinstance(item, str):
            raw_path = item
            filename = ""
            content_type = ""
        elif isinstance(item, dict):
            raw_path = item.get("path") or item.get("upload_id") or item.get("id") or item.get("filename")
            filename = item.get("filename") or ""
            content_type = item.get("content_type") or ""
        else:
            raise ValueError("Attachments must be strings or objects")
        path = _resolve_attachment_path(raw_path)
        size = path.stat().st_size
        total_size += size
        if INSTAGRAM_MCP_ATTACHMENT_MAX_BYTES > 0 and total_size > INSTAGRAM_MCP_ATTACHMENT_MAX_BYTES:
            raise ValueError(
                f"Attachments exceed INSTAGRAM_MCP_ATTACHMENT_MAX_BYTES ({INSTAGRAM_MCP_ATTACHMENT_MAX_BYTES} bytes)"
            )
        guessed = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if not (guessed.startswith("image/") or guessed.startswith("video/")):
            raise ValueError(f"Instagram direct attachments must be image/* or video/*, got {guessed}")
        prepared.append({
            "path": path,
            "filename": filename or path.name,
            "content_type": guessed,
            "size": size,
        })
    return prepared


def _provider(account=None) -> InstagramPrivateProvider:
    return InstagramPrivateProvider(account=account)


def test_instagram_login(account=None) -> dict:
    provider = _provider(account)
    provider.login()
    return {
        "ok": True,
        "account": provider.account.get("name") or "",
        "username": provider.account.get("username") or "",
    }


def _format_message_row(msg: dict, index: int | None = None) -> list[str]:
    prefix = f"{index}. " if index is not None else ""
    title = msg.get("thread_title") or msg.get("message_id") or "Instagram message"
    lines = [f"{prefix}**{title}**"]
    if msg.get("from_username") or msg.get("from_user_id"):
        lines.append(f"   From: {msg.get('from_username') or msg.get('from_user_id')}")
    if msg.get("timestamp"):
        lines.append(f"   Date: {msg['timestamp']}")
    if msg.get("thread_id"):
        lines.append(f"   Thread ID: {msg['thread_id']}")
    if msg.get("message_id"):
        lines.append(f"   Message ID: {msg['message_id']}")
    if msg.get("account"):
        lines.append(f"   Account: {msg.get('account')} ({msg.get('account_username', '')})")
    if msg.get("text"):
        lines.append(f"   Text: {_preview(msg['text'])}")
    lines.extend(_format_url_lines(msg, indent="   ", max_other=12))
    return lines


@server.list_tools()
async def list_tools() -> list[Tool]:
    ACCOUNT_PROP = {
        "account": {
            "type": "string",
            "description": "Which Instagram account to use (name, username, or id). Omit for default.",
        },
    }
    ATTACHMENTS_PROP = {
        "attachments": {
            "type": "array",
            "items": {
                "anyOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "upload_id": {"type": "string"},
                            "filename": {"type": "string"},
                            "content_type": {"type": "string"},
                        },
                    },
                ],
            },
            "description": (
                "Optional image/video files to send. Pass Odysseus chat upload IDs, "
                "uploaded original filenames, or full local paths under allowed roots."
            ),
        },
    }
    return [
        Tool(
            name="list_instagram_accounts",
            description="List configured Instagram private API accounts. Credentials are never returned.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="list_instagram_threads",
            description=(
                "List recent Instagram DM threads via the private API. Returns thread IDs, participants, "
                "latest message previews, and extracted URL metadata when present."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Maximum threads to return (default: 20)", "default": 20},
                    **ACCOUNT_PROP,
                },
                "required": [],
            },
        ),
        Tool(
            name="search_instagram_messages",
            description=(
                "Search Instagram DM threads/messages server-side in this MCP tool instead of making the model "
                "manually filter thread listings. Returns thread_id, message_id, account, text, and URL metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to match in thread title, participant username, message text, or item type."},
                    "max_threads": {"type": "integer", "description": "How many recent threads to inspect (default: 20)", "default": 20},
                    "max_messages_per_thread": {"type": "integer", "description": "How many messages per thread to inspect (default: 30)", "default": 30},
                    **ACCOUNT_PROP,
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="read_instagram_thread",
            description=(
                "Read a specific Instagram DM thread by thread_id. Returns messages with stable message IDs "
                "and extracted URL metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Instagram DM thread ID from list/search results"},
                    "max_messages": {"type": "integer", "description": "Messages to read (default: 30)", "default": 30},
                    **ACCOUNT_PROP,
                },
                "required": ["thread_id"],
            },
        ),
        Tool(
            name="extract_instagram_urls",
            description=(
                "Extract HTTP/HTTPS URLs from text or an Instagram DM thread. Labels likely tracking URLs and "
                "returns extracted_urls, url_details, and tracking_candidates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Instagram DM thread ID to scan"},
                    "text": {"type": "string", "description": "Direct text to scan"},
                    "max_messages": {"type": "integer", "description": "Messages to scan from the thread (default: 50)", "default": 50},
                    **ACCOUNT_PROP,
                },
                "required": [],
            },
        ),
        Tool(
            name="send_instagram_message",
            description=(
                "Send an Instagram DM immediately via private API. Provide thread_id or username/user_id, message text, "
                "and optional image/video attachments from Odysseus uploads."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Existing DM thread ID"},
                    "username": {"type": "string", "description": "Recipient Instagram username, with or without @"},
                    "user_id": {"type": "string", "description": "Recipient Instagram numeric user ID"},
                    "text": {"type": "string", "description": "Message text"},
                    **ATTACHMENTS_PROP,
                    **ACCOUNT_PROP,
                },
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    arguments = arguments or {}
    try:
        if name == "list_instagram_accounts":
            rows = [_public_account(row) for row in _load_accounts_raw()]
            if not rows:
                return [TextContent(
                    type="text",
                    text=_instagram_setup_hint(),
                )]
            lines = [f"Found {len(rows)} Instagram account(s):\n"]
            for row in rows:
                star = " (default)" if row.get("is_default") else ""
                lines.append(
                    f"- **{row['name']}**{star}\n"
                    f"  username: {row.get('username') or '(unknown)'}\n"
                    f"  id: {row['id']}\n"
                    f"  provider: {row['provider']}\n"
                    f"  source: {row.get('source') or 'legacy'}\n"
                    f"  session file: {row['session_file']}"
                )
            return [TextContent(type="text", text="\n".join(lines))]

        if name == "list_instagram_threads":
            account = arguments.get("account")
            provider = _provider(account)
            threads = provider.list_threads(arguments.get("max_results", 20))
            if not threads:
                return [TextContent(type="text", text="No Instagram threads found.")]
            lines = [f"Found {len(threads)} Instagram thread(s):\n"]
            for i, thread in enumerate(threads, 1):
                users = ", ".join(u.get("username") for u in thread.get("users", []) if u.get("username"))
                lines.append(
                    f"{i}. **{thread.get('thread_title') or '(untitled thread)'}**\n"
                    f"   Participants: {users or '(unknown)'}\n"
                    f"   Thread ID: {thread.get('thread_id')}\n"
                    f"   Account: {provider.account_label()}"
                )
                messages = thread.get("messages") or []
                if messages:
                    latest = messages[0]
                    if latest.get("text"):
                        lines.append(f"   Latest: {_preview(latest.get('text'))}")
                lines.extend(_format_url_lines(thread, indent="   ", max_other=8))
            return [TextContent(type="text", text="\n".join(lines))]

        if name == "search_instagram_messages":
            account = arguments.get("account")
            provider = _provider(account)
            query = arguments.get("query", "")
            matches = provider.search_messages(
                query,
                max_threads=arguments.get("max_threads", 20),
                max_messages_per_thread=arguments.get("max_messages_per_thread", 30),
            )
            if not matches:
                return [TextContent(type="text", text=f'No Instagram messages matched "{query}".')]
            lines = [f'Found {len(matches)} Instagram message(s) matching "{query}":\n']
            for i, msg in enumerate(matches, 1):
                lines.extend(_format_message_row(msg, i))
            return [TextContent(type="text", text="\n".join(lines))]

        if name == "read_instagram_thread":
            account = arguments.get("account")
            provider = _provider(account)
            thread = provider.read_thread(arguments.get("thread_id"), amount=arguments.get("max_messages", 30))
            lines = [
                f"Thread: {thread.get('thread_title') or '(untitled thread)'}",
                f"Thread ID: {thread.get('thread_id')}",
                f"Account: {provider.account_label()}",
            ]
            users = ", ".join(u.get("username") for u in thread.get("users", []) if u.get("username"))
            if users:
                lines.append(f"Participants: {users}")
            lines.extend(_format_url_lines(thread, max_other=20))
            lines.append("\nMessages:")
            for i, msg in enumerate(thread.get("messages") or [], 1):
                lines.extend(_format_message_row(msg, i))
            return [TextContent(type="text", text="\n".join(lines))]

        if name == "extract_instagram_urls":
            if arguments.get("text") is not None:
                result = _extract_instagram_urls(arguments.get("text"))
                provider = None
            elif arguments.get("thread_id"):
                account = arguments.get("account")
                provider = _provider(account)
                thread = provider.read_thread(arguments.get("thread_id"), amount=arguments.get("max_messages", 50))
                result = thread
            else:
                return [TextContent(type="text", text="Error: provide text or thread_id")]
            lines = []
            if result.get("thread_id"):
                lines.append(f"Thread ID: {result['thread_id']}")
            if result.get("thread_title"):
                lines.append(f"Thread: {result['thread_title']}")
            if provider is not None:
                lines.append(f"Account: {provider.account_label()}")
            lines.extend(_format_url_lines(result, max_other=40))
            return [TextContent(type="text", text="\n".join(lines))]

        if name == "send_instagram_message":
            account = arguments.get("account")
            provider = _provider(account)
            result = provider.send_message(
                arguments.get("text", ""),
                thread_id=arguments.get("thread_id"),
                username=arguments.get("username"),
                user_id=arguments.get("user_id"),
                attachments=arguments.get("attachments") or [],
            )
            attach_note = (
                f" Attached {len(result.get('attachments') or [])} file(s)."
                if result.get("attachments") else ""
            )
            target = result.get("thread_id") or result.get("username") or result.get("user_id")
            return [TextContent(
                type="text",
                text=f"Sent Instagram message to {target} from {provider.account_label()}.{attach_note}",
            )]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
