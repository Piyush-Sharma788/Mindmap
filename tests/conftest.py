"""Offline guarantees for the whole test suite: no credentials, no network."""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE",
                "GEMINI_API_KEY", "GOOGLE_API_KEY",
                "MINDMAP_PROVIDER", "MINDMAP_MODEL", "MINDMAP_MODEL_GENERATE", "MINDMAP_MODEL_GROW", "MINDMAP_EFFORT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MINDMAP_NO_DOTENV", "1")  # a developer's .env must never leak into tests


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def guard(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Network access is forbidden in tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
