"""Check an injected TypeSafe API credential without printing secret material."""

import json
import os
import sys
from http.client import HTTPException
from typing import TYPE_CHECKING, override
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

if TYPE_CHECKING:
    from email.message import Message

MODELS_URL = "https://api.typesafe.ai/v1/models"
MAX_RESPONSE_BYTES = 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    """Keep the authorization header on the documented TypeSafe endpoint."""

    @override
    def redirect_request(self, req: Request, fp: object, code: int, msg: str, headers: Message, newurl: str) -> None:
        """Reject redirects instead of forwarding the credential elsewhere."""


def model_count(payload: object) -> int:
    """Validate the public model-list response before reporting success."""
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        message = "Invalid model-list response."
        raise TypeError(message)
    models = payload["models"]
    if not models or any(not isinstance(model, dict) or not isinstance(model.get("name"), str) or not model["name"] for model in models):
        message = "No usable models in the response."
        raise ValueError(message)
    return len(models)


def main() -> int:
    """Validate credential access, reporting only status and model count."""
    api_key = os.environ.get("TYPESAFE_API_KEY", "")
    if not api_key or api_key.startswith("op://"):
        print("Supply TYPESAFE_API_KEY through your secret provider; resolve 1Password references with just typesafe-local.", file=sys.stderr)
        return 2
    if any(character.isspace() for character in api_key):
        print("TYPESAFE_API_KEY contains whitespace; check the stored credential.", file=sys.stderr)
        return 2

    request = Request(MODELS_URL, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    try:
        # urllib honors HTTPS_PROXY, including a cloud environment's secret proxy.
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200:
                message = "Unexpected HTTP status."
                raise ValueError(message)
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            message = "Oversized model-list response."
            raise ValueError(message)
        count = model_count(json.loads(body))
    except HTTPError as error:
        # Error bodies, headers, and exception strings may contain credentials.
        print(f"TypeSafe authentication check failed (HTTP {error.code}); response details withheld.", file=sys.stderr)
        error.close()
        return 1
    # Semgrep 1.178 requires parentheses for three or more exception types.
    except (URLError, OSError, HTTPException):  # fmt: skip
        print("Could not connect to TypeSafe; check network access, certificates, and proxy settings.", file=sys.stderr)
        return 1
    except TypeError, ValueError:
        print("TypeSafe returned an invalid model-list response; response details withheld.", file=sys.stderr)
        return 1

    print(f"TypeSafe authentication succeeded: {count} model(s) available. No inference request was made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
