"""
monitoring.py

Phase 6, Step 6.1: sets up Logfire (https://logfire.pydantic.dev/), the
observability tool we use to see what the system is actually doing in
production -- every LLM call, its latency, its token usage, its cost,
whether it succeeded or had to fall back to the backup model, all in
one dashboard instead of scattered across plain log files.

This module only sets up the CONNECTION to Logfire and exposes it for
other modules to use -- starting with llm_gateway.py in this step.
Wiring Logfire into FastAPI/SQLAlchemy themselves (so every HTTP
request and every DB query shows up too, not just LLM calls) happens
in Step 6.2 (main.py, database.py) -- this step is scoped to LLM call
visibility specifically.
"""

import logfire

from app.config import get_settings

_configured = False


def configure_monitoring():
    """
    Connects to Logfire using LOGFIRE_TOKEN from .env (see config.py).
    Safe to call more than once -- only actually configures once per
    process, so any module that needs monitoring can call this itself
    without needing to coordinate with whoever else already called it.

    BUG FIX: this used to read the token directly via
    os.getenv("LOGFIRE_TOKEN", ""), bypassing pydantic-settings
    entirely. config.py's Settings class loads .env via
    env_file=".env", but that ONLY populates the Settings object's own
    fields -- it does not inject values into the raw OS environment.
    Since nothing else in this codebase calls python-dotenv's
    load_dotenv() to do that injection globally, os.getenv() always
    returned "" no matter what was actually in .env, silently forcing
    Logfire into local-only mode regardless of a real token being set.
    Going through get_settings() (same as every other config value in
    this codebase) is what actually makes the token reachable.

    If no token is set (e.g. local development without a Logfire
    account yet), Logfire still works in a local-only mode: spans are
    still created and can still be inspected locally, they just aren't
    sent anywhere. This means logfire.span() calls elsewhere in the
    code never need a None-check or try/except around them just because
    monitoring might not be "fully" set up -- they're always safe to use.
    """
    global _configured
    if _configured:
        return

    settings = get_settings()

    logfire.configure(
        token=settings.LOGFIRE_TOKEN or None,
        service_name="insightos-backend",
        send_to_logfire="if-token-present",
    )
    _configured = True