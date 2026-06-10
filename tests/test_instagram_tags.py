from src import instagram_tags as tags


def test_instagram_tags_are_owner_account_scoped(monkeypatch, tmp_path):
    db_path = tmp_path / "scheduled.db"
    monkeypatch.setattr(tags, "SCHEDULED_DB", db_path)

    tags.upsert_instagram_tag({
        "account_id": "ig-main",
        "owner": "alice",
        "thread_id": "thread-1",
        "message_id": "msg-1",
        "thread_title": "Camera order",
        "username": "seller",
        "text_preview": "Tracking is ready",
        "tags": ["urgent", "Shopping", "urgent"],
        "score": 3,
        "reason": "tracking update",
        "model_used": "test-model",
    })
    tags.upsert_instagram_tag({
        "account_id": "ig-main",
        "owner": "bob",
        "thread_id": "thread-1",
        "message_id": "msg-2",
        "tags": ["spam"],
        "score": 0,
    })

    rows = tags.get_instagram_tag_rows(owner="alice", account_id="ig-main")
    assert len(rows) == 1
    assert rows[0]["tags"] == ["urgent", "shopping"]

    thread = {
        "thread_id": "thread-1",
        "messages": [
            {"message_id": "msg-1", "text": "Tracking is ready"},
            {"message_id": "msg-2", "text": "Hidden from alice"},
        ],
    }
    attached = tags.attach_instagram_tags(thread, owner="alice", account_id="ig-main")

    assert attached["tags"] == ["urgent", "shopping"]
    assert attached["triage_score"] == 3
    assert attached["messages"][0]["triage_reason"] == "tracking update"
    assert "tags" not in attached["messages"][1]

    assert tags.clear_instagram_tags(owner="alice") == 1
    assert tags.get_instagram_tag_rows(owner="alice", account_id="ig-main") == []
    assert len(tags.get_instagram_tag_rows(owner="bob", account_id="ig-main")) == 1
