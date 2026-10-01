"""Verify credential checks without accessing 1Password or the network."""

import io
from email.message import Message
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError

import pytest

import typesafe_check

if TYPE_CHECKING:
    from urllib.request import Request


class FakeResponse(io.BytesIO):
    """Provide the response context used by urllib."""

    status = 200


class FakeOpener:
    """Capture requests and provide controlled public responses or failures."""

    def __init__(self, result: bytes | Exception) -> None:
        """Store a response fixture without performing network operations."""
        self.result = result
        self.requests: list[Request] = []

    def open(self, request: Request, *, timeout: int) -> FakeResponse:
        assert timeout > 0
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return FakeResponse(self.result)


def install_opener(monkeypatch: pytest.MonkeyPatch, result: bytes | Exception) -> FakeOpener:
    """Replace networking while requiring the redirect restriction."""
    opener = FakeOpener(result)

    def build_opener(handler: typesafe_check.NoRedirect) -> FakeOpener:
        assert isinstance(handler, typesafe_check.NoRedirect)
        return opener

    monkeypatch.setattr(typesafe_check, "build_opener", build_opener)
    return opener


@pytest.mark.parametrize("credential", [None, "", "op://vault/item/field", "invalid\nheader"])
def test_missing_or_unresolved_credential_never_calls_api(monkeypatch: pytest.MonkeyPatch, credential: str | None) -> None:
    if credential is None:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("TYPESAFE_API_KEY", credential)
    opener = install_opener(monkeypatch, AssertionError("Network access is forbidden."))

    assert typesafe_check.main() == 2
    assert not opener.requests


def test_success_uses_injected_key_without_printing_it(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    marker = "test-only-credential"
    monkeypatch.setenv("TYPESAFE_API_KEY", marker)
    opener = install_opener(monkeypatch, b'{"models": [{"name": "jev-latest", "description": "private-response-marker"}]}')

    assert typesafe_check.main() == 0
    request = opener.requests[0]
    assert request.full_url == typesafe_check.MODELS_URL
    assert request.get_method() == "GET"
    assert request.data is None
    assert request.get_header("Authorization") == f"Bearer {marker}"
    output = capsys.readouterr()
    assert "1 model(s) available" in output.out
    assert marker not in output.out + output.err
    assert "private-response-marker" not in output.out + output.err


@pytest.mark.parametrize(
    "result",
    [
        b"private-response-marker",
        b'{"models": []}',
        b'{"models": [{"name": 123}]}',
        HTTPError(typesafe_check.MODELS_URL, 401, "private-response-marker", Message(), io.BytesIO(b"private-response-marker")),
        URLError("private-response-marker"),
    ],
)
def test_failures_do_not_echo_response_or_exception_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], result: bytes | Exception
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only-credential")
    install_opener(monkeypatch, result)

    assert typesafe_check.main() == 1
    output = capsys.readouterr()
    assert "private-response-marker" not in output.out + output.err
    assert "test-only-credential" not in output.out + output.err
    assert "succeeded" not in output.out
