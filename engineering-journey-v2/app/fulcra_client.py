"""Shared helper for obtaining an authenticated FulcraAPI client.

Centralizes credential loading so every module that talks to Fulcra does
it the same way, via the SDK (never the CLI or subprocess), and so tests
can inject a fake/mock client instead of hitting the real network.

This exact pattern was already proven in the flow-state-app-v2 reference
project (see its app/fulcra_client.py) -- it's copied here verbatim
rather than templated, because a fresh agent starting from an empty
sandbox will otherwise burn real iteration budget rediscovering the
correct FulcraCredentials/FulcraAPI construction sequence from scratch.
This is a known failure mode, not a hypothetical one: the first real
task run against a project scaffolded by an earlier version of this
starter kit (before this file existed) spent its ENTIRE iteration budget
on trial-and-error credential wiring -- calling FulcraCredentials() with
no arguments instead of FulcraCredentials.from_json(path.read_text()),
never calling refresh_access_token() -- and never got to write any real
feature code at all.
"""
import os
from pathlib import Path

from fulcra_api.core import FulcraAPI
from fulcra_api.credentials import FulcraCredentials

DEFAULT_CREDENTIALS_PATH = Path(
    os.environ.get(
        "FULCRA_CREDENTIALS_PATH",
        str(Path.home() / ".config" / "fulcra" / "credentials.json"),
    )
)


class FulcraAuthError(Exception):
    """Raised when a Fulcra API client cannot be constructed (e.g. missing
    or invalid local credentials)."""


def get_fulcra_client(credentials_path: "str | Path | None" = None) -> FulcraAPI:
    """Build an authenticated FulcraAPI client from locally cached
    credentials, refreshing the access token if it has expired.

    Args:
        credentials_path: override path to the credentials JSON file.
            Defaults to DEFAULT_CREDENTIALS_PATH (~/.config/fulcra/credentials.json
            or the FULCRA_CREDENTIALS_PATH env var).

    Raises:
        FulcraAuthError: if the credentials file is missing/unreadable or
            the token cannot be refreshed.
    """
    path = Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS_PATH

    if not path.is_file():
        raise FulcraAuthError(
            f"Fulcra credentials not found at {path}. Authenticate first "
            f"(see the fulcra-connect skill / `fulcra-api` login flow)."
        )

    try:
        creds = FulcraCredentials.from_json(path.read_text())
        client = FulcraAPI(credentials=creds)
        if creds.is_expired():
            client.refresh_access_token()
    except Exception as exc:
        raise FulcraAuthError(f"Failed to authenticate with Fulcra: {exc}") from exc

    return client
