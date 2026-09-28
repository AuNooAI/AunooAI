"""The LLM cost ledger must say which feature spent the money.

`llm_usage_log` recorded every call but attributed almost none of them. Over the
seven days to 2026-08-19, wileytest logged 186,048 calls costing $109.25 and
filed 185,899 of them — 99.9% — under `use_case = 'unknown'`. The ledger could
answer "what did we spend" and not "on what", which is the question it was built
for after the July 2026 AWS bill.

The cause: `_guess_use_case()` reads the call stack from inside a litellm
callback, and litellm runs its callbacks on its own worker threads, where none
of the app's frames are present. Synchronous calls sometimes got lucky. Async
calls — which is most of this codebase, 50 `acompletion` sites against 19
`completion` — never did.

No money is spent here. The synchronous tests use litellm's `mock_response`.
The asynchronous ones cannot: `mock_response` short-circuits litellm's logging,
so no ledger row is produced at all and the test would prove nothing. They point
at a closed local port instead, which fails in milliseconds without leaving the
machine and still exercises the real logging path.
"""

import asyncio

import pytest

from app.services import llm_usage_logger as ledger


@pytest.fixture
def captured(monkeypatch):
    """Collect the rows the ledger would insert, without a queue or a database."""
    rows = []
    monkeypatch.setattr(ledger, "_enqueue", rows.append)
    return rows


@pytest.fixture
def sentinel_caller(monkeypatch):
    """Stand in for the stack walk with a value we can follow through the plumbing.

    The real `_guess_use_case()` only reports frames under `app/`, and a test
    lives in `tests/`, so it would return "unknown" here no matter how well the
    tagging worked. Replacing it isolates the thing that was broken: whether the
    value captured at call time reaches the callback at all. Its own `app/`
    scoping is covered by TestStackWalk below.
    """
    monkeypatch.setattr(ledger, "_guess_use_case", lambda: "services.probe:caller")
    return "services.probe:caller"


@pytest.fixture
def tagging(monkeypatch):
    """Install call-site tagging and take it back off afterwards.

    litellm is process-global, so a leaked wrapper would follow the rest of the
    suite around.
    """
    import litellm

    from litellm.router import Router

    originals = {n: getattr(litellm, n) for n in ("completion", "acompletion")}
    router_originals = {n: getattr(Router, n) for n in ("completion", "acompletion")}
    prior_success = list(litellm.success_callback)
    prior_failure = list(litellm.failure_callback)
    # Both, as install() registers them — a call that fails only reaches the
    # failure callback, and the failure rows are the ones worth attributing.
    litellm.success_callback = [ledger._on_success]
    litellm.failure_callback = [ledger._on_failure]
    ledger._install_call_site_tagging()
    yield
    for name, fn in originals.items():
        setattr(litellm, name, fn)
    for name, fn in router_originals.items():
        setattr(Router, name, fn)
    litellm.success_callback = prior_success
    litellm.failure_callback = prior_failure


MOCK = dict(model="gpt-4o-mini", messages=[{"role": "user", "content": "x"}], mock_response="ok")

#: A closed local port. Fails in milliseconds, never leaves the machine, and —
#: unlike mock_response — goes through litellm's real logging path.
DEAD_ENDPOINT = dict(model="gpt-4o-mini", messages=[{"role": "user", "content": "x"}],
                     api_key="sk-not-a-real-key", api_base="http://127.0.0.1:9", timeout=3)


def _use_case(row):
    return row[0]


class TestCallSiteTagging:
    def test_the_tag_survives_the_hop_onto_litellms_logging_thread(
            self, sentinel_caller, tagging, captured):
        """litellm copies `metadata` into `litellm_params`, which is the only
        thing that reaches a callback running on another thread."""
        import litellm

        def briefing_compose_caller():
            return litellm.completion(**MOCK)

        briefing_compose_caller()
        _drain()
        assert captured, "no ledger row was produced"
        assert _use_case(captured[-1]) == sentinel_caller

    def test_an_async_call_is_attributed(self, sentinel_caller, tagging, captured):
        """The case that was always 'unknown' in production.

        The trailing sleep is not padding: litellm schedules its async callback
        as a task on the running loop, so a loop that stops the moment the
        completion returns drops the ledger row. The server's loop runs for the
        life of the process; short-lived loops in scripts do not.
        """
        import litellm

        async def curate_the_briefing():
            try:
                await litellm.acompletion(**DEAD_ENDPOINT)
            except Exception:  # noqa: BLE001 — the failure is the point
                pass

        async def keep_the_loop_alive():
            await curate_the_briefing()
            await asyncio.sleep(3)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(keep_the_loop_alive())
        finally:
            loop.close()
        assert captured, "no ledger row was produced"
        assert _use_case(captured[-1]) == sentinel_caller

    def test_a_failed_call_is_still_attributed(self, sentinel_caller, tagging, captured):
        """Outages are the rows most worth attributing — they say which feature
        was down, not just that something was."""
        import litellm

        async def keep_the_loop_alive():
            try:
                await litellm.acompletion(**DEAD_ENDPOINT)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(3)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(keep_the_loop_alive())
        finally:
            loop.close()
        assert captured and captured[-1][9] == "error"
        assert _use_case(captured[-1]) == sentinel_caller

    def test_a_router_call_is_attributed(self, sentinel_caller, tagging, captured):
        """AIModelFactory routes through litellm's Router, which hands the work to
        its own scheduler rather than calling from the caller's frame. Wrapping
        only the module-level functions left these rows unattributed — and on
        wileytest the Router path carries the relevance fallback, the biggest
        LLM volume on the box."""
        from litellm.router import Router

        router = Router(model_list=[{
            "model_name": "nova-lite",
            "litellm_params": {"model": "gpt-4o-mini", "api_key": "sk-not-a-real-key",
                               "api_base": "http://127.0.0.1:9", "timeout": 3},
        }])

        async def relevance_fallback_caller():
            try:
                await router.acompletion(model="nova-lite",
                                         messages=[{"role": "user", "content": "x"}])
            except Exception:  # noqa: BLE001
                pass

        async def keep_the_loop_alive():
            await relevance_fallback_caller()
            await asyncio.sleep(4)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(keep_the_loop_alive())
        finally:
            loop.close()
        assert captured, "no ledger row was produced"
        assert all(_use_case(row) == sentinel_caller for row in captured)

    def test_a_caller_that_imported_completion_directly_is_still_tagged(
            self, sentinel_caller, tagging, captured):
        """Twelve modules do `from litellm import completion` at import time, so
        the binding predates install() and setting the module attribute alone
        would miss them."""
        from litellm import completion  # resolved after tagging, as those modules are rebound

        def hybrid_relevance_caller():
            return completion(**MOCK)

        hybrid_relevance_caller()
        _drain()
        assert _use_case(captured[-1]) == sentinel_caller

    def test_callers_own_metadata_is_preserved(self, sentinel_caller, tagging, captured):
        import litellm

        def caller_with_metadata():
            return litellm.completion(**MOCK, metadata={"trace_id": "abc123"})

        caller_with_metadata()
        _drain()
        assert _use_case(captured[-1]) == sentinel_caller

    def test_an_explicit_use_case_is_not_overwritten(self, tagging, captured):
        import litellm

        def wrapper_that_knows_better():
            return litellm.completion(**MOCK, metadata={ledger._USE_CASE_KEY: "chosen:by_hand"})

        wrapper_that_knows_better()
        _drain()
        assert _use_case(captured[-1]) == "chosen:by_hand"

    def test_installing_twice_does_not_double_wrap(self, tagging):
        import litellm

        once = litellm.completion
        ledger._install_call_site_tagging()
        assert litellm.completion is once

    def test_tagging_failure_cannot_break_the_call(self, tagging, monkeypatch):
        """Logging must never be able to take an LLM call down with it."""
        import litellm

        monkeypatch.setattr(ledger, "_guess_use_case",
                            lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert litellm.completion(**MOCK).choices[0].message.content == "ok"


class TestUseCaseResolution:
    def test_it_reads_the_tag_from_litellm_params(self):
        kwargs = {"litellm_params": {"metadata": {ledger._USE_CASE_KEY: "services.x:go"}}}
        assert ledger._use_case_from(kwargs) == "services.x:go"

    def test_it_reads_the_tag_from_top_level_metadata(self):
        kwargs = {"metadata": {ledger._USE_CASE_KEY: "services.y:go"}}
        assert ledger._use_case_from(kwargs) == "services.y:go"

    def test_the_failure_callback_also_reads_the_tag(self):
        kwargs = {"litellm_params": {"metadata": {ledger._USE_CASE_KEY: "services.z:go"}}}
        row = ledger._extract(kwargs, None, None, None, "error", "boom")
        assert row[0] == "services.z:go" and row[9] == "error"

    def test_an_untagged_call_falls_back_to_the_stack_walk(self, monkeypatch):
        monkeypatch.setattr(ledger, "_guess_use_case", lambda: "fallback:used")
        assert ledger._use_case_from({"litellm_params": {}}) == "fallback:used"

    @pytest.mark.parametrize("kwargs", [
        {}, {"metadata": None}, {"metadata": "not a dict"},
        {"litellm_params": None}, {"litellm_params": {"metadata": []}},
    ])
    def test_malformed_metadata_does_not_raise(self, kwargs, monkeypatch):
        monkeypatch.setattr(ledger, "_guess_use_case", lambda: "fallback")
        assert ledger._use_case_from(kwargs) == "fallback"

    def test_a_long_tag_is_truncated_to_the_column_width(self):
        kwargs = {"metadata": {ledger._USE_CASE_KEY: "x" * 500}}
        assert len(ledger._use_case_from(kwargs)) == 200


class TestStackWalk:
    """`_guess_use_case()` itself — it only ever reports frames under `app/`."""

    def test_a_non_app_caller_is_not_attributed(self):
        assert ledger._guess_use_case() == "unknown"

    def test_it_names_an_app_frame_as_module_colon_function(self, monkeypatch):
        import traceback

        FrameSummary = traceback.FrameSummary
        fake = [
            FrameSummary("/x/.venv/lib/site-packages/litellm/main.py", 1, "acompletion"),
            FrameSummary("/home/o/tenants/t/app/services/daily_briefing_compose_service.py", 1, "_curate"),
            FrameSummary("/home/o/tenants/t/app/services/llm_usage_logger.py", 1, "_tagged_kwargs"),
        ]
        monkeypatch.setattr(traceback, "extract_stack", lambda limit=None: fake)
        assert ledger._guess_use_case() == "services.daily_briefing_compose_service:_curate"


def _drain(seconds: float = 2.0):
    """litellm dispatches success callbacks onto its own threads; give them a moment."""
    import time
    time.sleep(seconds)


def test_async_calls_reach_the_ledger_once():
    """litellm calls plain success callbacks for sync calls only; the ledger
    registers a CustomLogger for async ones, once however often install runs."""
    import litellm

    from app.services import llm_usage_logger as L

    before = [c for c in litellm.callbacks if getattr(c, "_aunoo_ledger", False)]
    L._INSTALLED = False
    L.install()
    L._INSTALLED = False
    L.install()
    hooks = [c for c in litellm.callbacks if getattr(c, "_aunoo_ledger", False)]
    assert len(hooks) == 1
    assert hasattr(hooks[0], "async_log_success_event")
    assert not type(hooks[0]).__dict__.get("async_log_failure_event")
    for c in hooks:
        if c not in before:
            litellm.callbacks.remove(c)
