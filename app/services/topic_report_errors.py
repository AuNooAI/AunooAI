"""Topic Report error types.

Deliberately dependency-free. The resolver lives in ``topic_report_pptx``, which
imports ``python-pptx`` at module level, and not every tenant has that installed
— importing it from a route at module scope takes the whole app down on those
tenants. Route modules import the exception from here instead, and everything
that needs the resolver keeps importing it inside a function body, which is the
existing convention in this area.
"""


class MissingPinnedRun(Exception):
    """A report is pinned to a forecast run that no longer exists.

    Raised instead of falling back to the latest run, because switching the
    analysis under an existing report label is exactly what pinning prevents.
    Routes translate this into a 409 telling the caller to regenerate.
    """
