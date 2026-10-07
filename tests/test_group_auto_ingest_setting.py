"""A group's own auto-ingest setting wins over the site setting; NULL inherits."""
from app.tasks import keyword_monitor as km


class _Facade:
    def __init__(self, groups):
        self.groups = groups

    def get_keyword_group_with_settings(self, gid):
        return self.groups.get(gid)


class _Db:
    def __init__(self, groups):
        self.facade = _Facade(groups)


def _monitor(site_on, groups):
    m = object.__new__(km.KeywordMonitor)
    m.db = _Db(groups)
    m.get_auto_ingest_settings = lambda: {"auto_ingest_enabled": site_on}
    return m


def test_group_off_overrides_site_on():
    assert _monitor(True, {1: {"auto_ingest_enabled": False}}).should_auto_ingest(1) is False


def test_group_on_overrides_site_off():
    assert _monitor(False, {1: {"auto_ingest_enabled": True}}).should_auto_ingest(1) is True


def test_null_group_setting_inherits_the_site():
    m = _monitor(True, {1: {"auto_ingest_enabled": None}})
    assert m.should_auto_ingest(1) is True and m.should_auto_ingest(None) is True
    assert _monitor(False, {1: {}}).should_auto_ingest(1) is False


def test_unreadable_group_falls_back_to_the_site():
    m = _monitor(True, {})
    m.db.facade.get_keyword_group_with_settings = lambda gid: (_ for _ in ()).throw(RuntimeError("db"))
    assert m.should_auto_ingest(1) is True
