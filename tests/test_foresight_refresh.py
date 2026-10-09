"""The weekly foresight refresh: which runs are due, and when it stays off."""

from datetime import datetime

from app.tasks import foresight_refresh as fr
from app.model_tiers import default_model


def test_last_slot_is_the_previous_sunday_2am():
    # Friday 9 Oct 2026 14:00 -> Sunday 4 Oct 02:00
    assert fr.last_slot(datetime(2026, 10, 9, 14), 6, 2) == datetime(2026, 10, 4, 2)
    # Sunday before 02:00 still points at the week before
    assert fr.last_slot(datetime(2026, 10, 11, 1), 6, 2) == datetime(2026, 10, 4, 2)
    assert fr.last_slot(datetime(2026, 10, 11, 2), 6, 2) == datetime(2026, 10, 11, 2)


def test_due_catches_up_and_skips_fresh_runs():
    slot = datetime(2026, 10, 4, 2)
    newest = {
        ("consensus", "A"): datetime(2026, 9, 4, 12),   # a month old: due
        ("horizons", "A"): datetime(2026, 10, 5, 3),    # after the slot: not due
        ("consensus", "B"): None,                       # never run: due
    }
    assert sorted(fr.due(newest, slot)) == [("consensus", "A"), ("consensus", "B")]


def test_off_without_topics_or_profile(monkeypatch):
    monkeypatch.delenv("FORESIGHT_REFRESH_TOPICS", raising=False)
    monkeypatch.setenv("FORESIGHT_REFRESH_PROFILE_ID", "8")
    assert fr._settings() is None
    monkeypatch.setenv("FORESIGHT_REFRESH_TOPICS", "Brand Monitoring Oviva|Religion, Magic and Occultism")
    monkeypatch.delenv("FORESIGHT_REFRESH_PROFILE_ID")
    assert fr._settings() is None
    monkeypatch.setenv("FORESIGHT_REFRESH_PROFILE_ID", "8")
    s = fr._settings()
    assert s["topics"] == ["Brand Monitoring Oviva", "Religion, Magic and Occultism"]
    assert (s["profile_id"], s["model"], s["timeframe_days"]) == (8, default_model("standard"), 365)
