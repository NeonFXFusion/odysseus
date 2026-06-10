"""Regression for issue #1707 — the agent tool-RAG force-included the entire
email toolset on any "tell me ..." query, crowding out the relevant tools so the
model believed it only had email tools and refused web/other tasks.

Root cause: `_KEYWORD_HINTS` in src/tool_index.py listed "tell" under the email
intent, and `get_tools_for_query` force-includes a hint's tools whenever any of
its keywords appears (word-boundary match). "tell" appears in a huge fraction of
requests (the reporter's was "visit <url> and tell me the title"), so email tools
were force-included for non-email queries.

These hints are deterministic string matching — no embeddings — so we can test
`get_tools_for_query` directly with retrieval stubbed out (no ChromaDB needed).
"""

from src.tool_index import ToolIndex, ALWAYS_AVAILABLE

_EMAIL_TOOLS = {
    "list_emails", "search_emails", "read_email", "extract_email_urls", "send_email", "reply_to_email",
    "bulk_email", "delete_email", "archive_email", "mark_email_read",
}


def _index_without_embeddings():
    """A ToolIndex whose retrieval returns nothing, so get_tools_for_query
    exercises only the deterministic base + keyword-hint logic."""
    ti = ToolIndex.__new__(ToolIndex)        # skip __init__ (no ChromaDB/fastembed)
    ti.retrieve = lambda query, k=8: []
    return ti


def test_tell_in_web_query_does_not_force_email_tools():
    """The #1707 repro: a web request that merely contains the word 'tell' must
    NOT drag in the email toolset."""
    ti = _index_without_embeddings()
    q = "visit https://www.youtube.com/user/PewDiePie and tell me the title of his latest video"
    tools = ti.get_tools_for_query(q)
    leaked = _EMAIL_TOOLS & tools
    assert not leaked, f"'tell me' must not force-include email tools, got {sorted(leaked)}"
    # web_search / web_fetch are always-available and must remain present.
    assert "web_search" in tools and "web_fetch" in tools


def test_genuine_email_query_still_gets_email_tools():
    """Removing 'tell' must not break real email intent — the actual email
    keywords still force-include the toolset."""
    ti = _index_without_embeddings()
    tools = ti.get_tools_for_query("reply to the unread email in my inbox")
    assert {"reply_to_email", "send_email", "search_emails", "read_email"} <= tools


def test_email_search_query_gets_search_tool():
    """Named mail search should surface the server-side search tool, not force
    the model to list recent messages and filter by hand."""
    ti = _index_without_embeddings()
    tools = ti.get_tools_for_query("search my email for EY invoice")
    assert "search_emails" in tools


def test_email_tracking_url_query_gets_email_url_tools_not_web():
    """A URL requested from email content is local mailbox work, not web search."""
    ti = _index_without_embeddings()
    q = "Find ebay message from emails and extract the tracking url then output the url if url unknown output all urls"
    tools = ti.get_tools_for_query(q, always_include={"__base__"})
    assert {"search_emails", "extract_email_urls"} <= tools
    assert "web_search" not in tools


def test_find_company_email_surfaces_search_not_contact_resolution():
    """A company/sender in an email search must not be treated as a contact."""
    ti = _index_without_embeddings()
    tools = ti.get_tools_for_query("Find Amazon Prime email invitation", always_include={"__base__"})
    assert "search_emails" in tools
    assert "resolve_contact" not in tools


def test_plain_tell_request_stays_minimal():
    """A bare 'tell me a joke' must not pull in email tools either."""
    ti = _index_without_embeddings()
    tools = ti.get_tools_for_query("tell me a joke")
    assert not (_EMAIL_TOOLS & tools)
    # Always-available baseline is still there.
    assert set(ALWAYS_AVAILABLE) <= tools
