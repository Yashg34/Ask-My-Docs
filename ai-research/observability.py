"""Observability: Logfire (app metrics) + LangSmith (graph tracing)."""

import os
from contextlib import contextmanager
from config import settings

# Set by setup_logfire().
_LOGIFIRE_ACTIVE = False


def logfire_active() -> bool:
    """Whether Logfire has been configured."""
    return _LOGIFIRE_ACTIVE


def get_logfire():
    """Return the `logfire` module if active, else None (callers guard with it)."""
    if not _LOGIFIRE_ACTIVE:
        return None
    import logfire
    return logfire


@contextmanager
def logfire_span(name: str, **tags):
    """Open a Logfire span if active; otherwise a no-op."""
    lf = get_logfire()
    if lf is None:
        yield
        return
    with lf.span(name, **tags):
        yield


def increment_counter(counter_name: str, value: int = 1):
    """Increment a named Logfire counter if active; otherwise a no-op."""
    lf = get_logfire()
    if lf is None:
        return
    try:
        lf.metric(f"{counter_name}_counter").add(value)
    except Exception as e:
        print(f"⚠️ Failed to record counter '{counter_name}': {e}")


def setup_logfire() -> bool:
    """Configure Logfire once at startup; skipped if LOGFIRE_TOKEN is empty."""
    global _LOGIFIRE_ACTIVE

    if not settings.LOGFIRE_TOKEN:
        print("⚪ Logfire disabled (no LOGFIRE_TOKEN set)")
        _LOGIFIRE_ACTIVE = False
        return False

    try:
        import logfire
        logfire.configure(token=settings.LOGFIRE_TOKEN)
        _LOGIFIRE_ACTIVE = True
        print("🔥 Logfire configured successfully")
        return True
    except Exception as e:
        print(f"⚠️ Failed to configure Logfire: {e}")
        _LOGIFIRE_ACTIVE = False
        return False


def instrument_fastapi(app) -> bool:
    """Instrument a FastAPI app with Logfire; call only after setup_logfire()."""
    try:
        import logfire
        logfire.instrument_fastapi(app)
        print("📡 FastAPI instrumented with Logfire")
        return True
    except Exception as e:
        print(f"⚠️ Failed to instrument FastAPI: {e}")
        return False


def setup_langsmith() -> bool:
    """Wire LangSmith tracing env vars from settings. Must run before the graph
    is compiled. Returns whether tracing is enabled."""
    if not settings.LANGSMITH_TRACING:
        print("⚪ LangSmith tracing disabled (LANGSMITH_TRACING=false)")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT

    if settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
        print(f"🌳 LangSmith tracing enabled (project: {settings.LANGSMITH_PROJECT})")
        return True
    else:
        print("⚠️ LANGSMITH_TRACING=true but no LANGSMITH_API_KEY set — tracing will not report")
        return True
