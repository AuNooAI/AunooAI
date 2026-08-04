"""Keep the test suite away from the tenant's live prompt store.

PromptManager defaults its storage directory to the app's real data/prompts/,
so anything that builds a PromptManager during a test writes to the prompts the
running service uses. test_article_analyzer.py does exactly that: its
load_custom_templates() call persists the fixture templates, replacing
content_analysis with "Custom analysis prompt for {title}".

That happened to wbm on 2026-08-04. Every uncached article analysis failed for
two hours — the model was being asked to write an analysis prompt, so it
returned prose and none of the required fields. It stayed invisible because
most articles hit the analysis cache and never called the model.

Two guards here:

1. Every PromptManager built without an explicit storage_dir gets a temporary
   one instead of the live directory.
2. The live prompts are hashed before and after the session. If anything writes
   to them anyway, the run fails and says which file changed, rather than
   leaving a broken tenant behind.
"""

import hashlib
import os
from pathlib import Path

import pytest

from app.analyzers.prompt_manager import PromptManager

_LIVE_PROMPTS = Path(__file__).resolve().parent.parent / "data" / "prompts"
_original_init = PromptManager.__init__


def _fingerprint():
    """Content hash of every stored prompt, so a rewrite cannot go unnoticed."""
    out = {}
    if not _LIVE_PROMPTS.is_dir():
        return out
    for path in sorted(_LIVE_PROMPTS.rglob("*.json")):
        try:
            out[str(path.relative_to(_LIVE_PROMPTS))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        except OSError:
            continue
    return out


@pytest.fixture(scope="session", autouse=True)
def isolate_prompt_storage(tmp_path_factory):
    scratch = tmp_path_factory.mktemp("prompt_store")

    def _init(self, storage_dir=None):
        # An explicit directory is honoured; the default is redirected.
        return _original_init(self, storage_dir or str(scratch))

    PromptManager.__init__ = _init
    before = _fingerprint()
    try:
        yield scratch
    finally:
        PromptManager.__init__ = _original_init

    after = _fingerprint()
    changed = sorted(
        set(before) ^ set(after)
        | {k for k in set(before) & set(after) if before[k] != after[k]}
    )
    if changed:
        raise AssertionError(
            "The test run modified this tenant's LIVE prompt store at "
            f"{_LIVE_PROMPTS}: {changed}. Restore each current.json from the "
            "newest hash-named version file beside it that is not a test stub, "
            "then restart the service."
        )
