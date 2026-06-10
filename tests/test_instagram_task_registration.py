from src.builtin_actions import BUILTIN_ACTION_INFO, BUILTIN_ACTIONS
from src.task_scheduler import HOUSEKEEPING_DEFAULTS, TaskScheduler


def test_instagram_tags_task_is_registered():
    assert "check_instagram_urgency" in BUILTIN_ACTIONS
    assert "check_instagram_urgency" in BUILTIN_ACTION_INFO

    defaults = HOUSEKEEPING_DEFAULTS["check_instagram_urgency"]
    assert defaults["name"] == "Instagram Tags"
    assert defaults["schedule"] == "cron"
    assert defaults["ship_paused"] is True

    assert "check_instagram_urgency" in TaskScheduler._SILENT_ACTIONS
    assert "check_instagram_urgency" in TaskScheduler._MODEL_BACKED_ACTIONS
