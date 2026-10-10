"""Append-only request accounting; missing measurements never become zero cost."""

import argparse
import fcntl
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from review_graph_integrity import digest_json

if TYPE_CHECKING:
    from collections.abc import Callable


class AccountingInputError(ValueError):
    """Expose a safe diagnostic containing no caller-supplied values or paths."""


def digest(value: object) -> str:
    """Identify exact JSON inputs, rejecting non-finite numbers."""
    return digest_json(value, allow_nan=False)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            msg = "duplicate JSON field"
            raise AccountingInputError(msg)
        result[key] = value
    return result


def parse_json(content: str | bytes) -> dict[str, Any]:
    """Decode strict JSON without accepting duplicate fields or non-finite values."""
    value = json.loads(content, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        msg = "JSON input must be an object"
        raise TypeError(msg)
    digest(value)
    return value


def read_json(path: Path) -> dict[str, Any]:
    """Read a bounded JSON object without duplicate fields."""
    if path.stat().st_size > 4_194_304:
        msg = "JSON input exceeds four MiB"
        raise AccountingInputError(msg)
    return parse_json(path.read_text(encoding="utf-8"))


def measure_call(callback: Callable[[], int], ledger: Path, *, stage: str, scope_digest: str) -> int:
    """Measure a deterministic runtime operation, separately from coordinator inference."""
    if ledger.resolve().is_relative_to(Path.cwd().resolve()):
        msg = "usage ledger must be outside the reviewed repository"
        raise ValueError(msg)
    request_id = start_request(ledger, stage=stage, provider="deterministic-runtime", model=None, scope_digest=scope_digest)
    started = time.monotonic()
    status = "failed"
    try:
        code = callback()
        status = "succeeded" if code == 0 else "failed"
        return code
    finally:
        finish_request(
            ledger,
            request_id,
            status=status,
            usage={
                "input_tokens": 0,
                "output_tokens": 0,
                "elapsed_seconds": time.monotonic() - started,
                "cost_usd": 0,
                "cost_basis": "measured",
                "measurement_source": "deterministic process only; excludes coordinator inference and compute charges",
            },
        )


def write_json(path: Path, value: object) -> None:
    """Create a private artifact without replacing an earlier result."""
    content = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)


def append_event(path: Path, event: dict[str, Any]) -> None:
    """Durably append one event, including before starting a paid request."""
    content = json.dumps(event, sort_keys=True, allow_nan=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def start_request(path: Path, *, stage: str, provider: str, model: str | None, scope_digest: str) -> str:
    """Reserve an attempt so interrupted work remains visible in summaries."""
    request_id = str(uuid.uuid4())
    append_event(
        path,
        {"event": "started", "id": request_id, "stage": stage, "provider": provider, "model": model, "scope_digest": scope_digest, "started_at": time.time()},
    )
    return request_id


def _nonnegative_finite_number(value: object) -> bool:
    if not isinstance(value, int | float) or type(value) not in {int, float}:
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def measurements(value: dict[str, Any]) -> dict[str, Any]:
    """Validate portable provider measurements without inventing usage or prices."""
    result: dict[str, Any] = {}
    for name in ("input_tokens", "output_tokens", "cached_input_tokens"):
        count = value.get(name)
        if count is not None and (type(count) is not int or count < 0):
            raise AccountingInputError(f"{name} must be a nonnegative integer or null")
        result[name] = count
    for name in ("elapsed_seconds", "cost_usd"):
        number = value.get(name)
        if number is not None and not _nonnegative_finite_number(number):
            raise AccountingInputError(f"{name} must be a nonnegative finite number or null")
        result[name] = number
    basis = value.get("cost_basis", "unavailable")
    if not isinstance(basis, str) or basis not in {"measured", "estimated", "unavailable"}:
        msg = "cost_basis must be measured, estimated, or unavailable"
        raise AccountingInputError(msg)
    if basis != "unavailable" and result["cost_usd"] is None:
        msg = "cost_basis must be unavailable when cost_usd is null; measured or estimated requires a supplied cost_usd"
        raise AccountingInputError(msg)
    if basis == "unavailable" and result["cost_usd"] is not None:
        msg = "cost_basis must be measured or estimated when cost_usd is supplied; unavailable requires null cost_usd"
        raise AccountingInputError(msg)
    result["cost_basis"] = basis
    source = value.get("measurement_source")
    if not isinstance(source, str) or not source.strip():
        msg = "measurement_source is required and must be a nonempty string, including for unavailable measurements"
        raise AccountingInputError(msg)
    result["measurement_source"] = source
    return result


def finish_request(path: Path, request_id: str, *, status: str, usage: dict[str, Any]) -> None:
    """Record only sanitized measurement fields; never headers or error bodies."""
    if status not in {"succeeded", "failed", "cancelled"}:
        msg = "invalid request status"
        raise ValueError(msg)
    append_event(path, {"event": "finished", "id": request_id, "status": status, "finished_at": time.time(), **measurements(usage)})


def summarize(paths: list[Path]) -> dict[str, Any]:
    """Group actual attempts by stage/provider/model; retain partial totals explicitly."""
    starts: dict[str, dict[str, Any]] = {}
    ends: dict[str, dict[str, Any]] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line, object_pairs_hook=_unique_object)
            target = starts if event["event"] == "started" else ends if event["event"] == "finished" else None
            if target is None or event["id"] in target:
                msg = "unknown or duplicate usage event"
                raise ValueError(msg)
            target[event["id"]] = event
    if set(ends) - set(starts):
        msg = "usage completion has no matching start"
        raise ValueError(msg)
    groups: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for request_id, start in starts.items():
        key = (start["stage"], start["provider"], start["model"])
        group = groups.setdefault(
            key,
            {
                "stage": key[0],
                "provider": key[1],
                "model": key[2],
                "attempts": 0,
                "succeeded": 0,
                "failed": 0,
                "cancelled": 0,
                "unfinished": 0,
                "measured_cost_usd": 0.0,
                "estimated_cost_usd": 0.0,
                "unknown_cost_attempts": 0,
                "input_tokens_known": 0,
                "output_tokens_known": 0,
                "unknown_input_attempts": 0,
                "unknown_output_attempts": 0,
                "elapsed_seconds_known": 0.0,
                "unknown_elapsed_attempts": 0,
            },
        )
        group["attempts"] += 1
        end = ends.get(request_id)
        group[end["status"] if end is not None else "unfinished"] += 1
        usage = measurements(end) if end is not None else {"cost_basis": "unavailable"}
        for direction in ("input", "output"):
            count = usage.get(f"{direction}_tokens")
            group[f"unknown_{direction}_attempts" if count is None else f"{direction}_tokens_known"] += 1 if count is None else count
        elapsed = usage.get("elapsed_seconds")
        group["unknown_elapsed_attempts" if elapsed is None else "elapsed_seconds_known"] += 1 if elapsed is None else elapsed
        basis = usage["cost_basis"]
        group["unknown_cost_attempts" if basis == "unavailable" else f"{basis}_cost_usd"] += 1 if basis == "unavailable" else usage["cost_usd"]
    return {"schema_version": 1, "groups": list(groups.values()), "totals_are_partial": any(g["unknown_cost_attempts"] for g in groups.values())}


def _read_usage(path: Path) -> dict[str, Any]:
    try:
        return measurements(read_json(path))
    except AccountingInputError as error:
        raise AccountingInputError(f"--usage: {error}") from error
    except json.JSONDecodeError as error:
        msg = f"--usage: invalid JSON at line {error.lineno}, column {error.colno}"
        raise AccountingInputError(msg) from error
    except OSError as error:
        msg = "--usage: cannot read JSON file; supply a readable file path, not inline JSON"
        raise AccountingInputError(msg) from error
    except UnicodeError as error:
        msg = "--usage: JSON file must use UTF-8 encoding"
        raise AccountingInputError(msg) from error
    except TypeError as error:
        msg = "--usage: JSON input must be an object"
        raise AccountingInputError(msg) from error
    except RecursionError as error:
        msg = "--usage: invalid JSON: nesting exceeds parser limit"
        raise AccountingInputError(msg) from error
    except ValueError as error:
        msg = "--usage: invalid JSON: non-finite numbers or unsupported numeric ranges"
        raise AccountingInputError(msg) from error


def main(argv: list[str] | None = None) -> int:
    """Expose accounting for routing, specialists, validation, synthesis, and proof stages."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start")
    start.add_argument("--ledger", type=Path, required=True)
    start.add_argument("--stage", required=True)
    start.add_argument("--provider", required=True)
    start.add_argument("--model")
    start.add_argument("--scope-digest", required=True)
    finish = sub.add_parser(
        "finish",
        description="Record completion using measurements from a JSON file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Minimal usage.json when provider measurements are unknown:
{
  "input_tokens": null,
  "output_tokens": null,
  "cached_input_tokens": null,
  "elapsed_seconds": null,
  "cost_usd": null,
  "cost_basis": "unavailable",
  "measurement_source": "provider usage unavailable"
}
Pass its path with --usage usage.json (not inline JSON).
Missing numeric fields stay unknown; use zero only for a measured zero.
Token counts must be nonnegative integers; elapsed_seconds and cost_usd must
be nonnegative finite numbers. cost_basis is measured, estimated, or unavailable;
measured/estimated requires a numeric cost_usd, unavailable requires null.
measurement_source is required; identify the rate source for estimated costs.
Never infer tokens or costs from byte counts or account-wide allowances.""",
    )
    finish.add_argument("--ledger", type=Path, required=True)
    finish.add_argument("--id", required=True)
    finish.add_argument("--status", choices=("succeeded", "failed", "cancelled"), required=True)
    finish.add_argument("--usage", type=Path, required=True, metavar="JSON_FILE", help="path to a UTF-8 JSON file of measurements; see the example below")
    report = sub.add_parser("report")
    report.add_argument("ledgers", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            print(start_request(args.ledger, stage=args.stage, provider=args.provider, model=args.model, scope_digest=args.scope_digest))
        elif args.command == "finish":
            finish_request(args.ledger, args.id, status=args.status, usage=_read_usage(args.usage))
        else:
            print(json.dumps(summarize(args.ledgers), indent=2))
    except AccountingInputError as error:
        print(f"review_graph_usage: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("review_graph_usage: cannot read or write accounting file", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"review_graph_usage: invalid ledger JSON at line {error.lineno}, column {error.colno}", file=sys.stderr)
        return 2
    # Keep parentheses for Semgrep's exception-pattern parser.
    except (ValueError, KeyError, TypeError, UnicodeError):  # fmt: skip
        print("review_graph_usage: invalid accounting fields", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
