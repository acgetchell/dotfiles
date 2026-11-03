"""Optional per-invocation capture diagnostics, kept outside source evidence."""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


@dataclass(slots=True)
class PhaseTiming:
    """Inclusive elapsed time and failures, including unsuccessful Git queries."""

    calls: int = 0
    failed_calls: int = 0
    elapsed_seconds: float = 0.0


@dataclass(slots=True)
class CaptureTiming:
    """One invocation's diagnostics; no file identities or cached observations."""

    started: float = field(default_factory=time.perf_counter)
    phases: dict[str, PhaseTiming] = field(default_factory=dict)

    def as_raw(self, exit_code: int) -> dict[str, object]:
        """Serialize diagnostics independently of the manifest and receipt."""
        return {
            "format": "review-graph-capture-timing-v1",
            "exit_code": exit_code,
            "elapsed_seconds": time.perf_counter() - self.started,
            "phases": {name: asdict(value) for name, value in sorted(self.phases.items())},
        }


_CURRENT: ContextVar[CaptureTiming | None] = ContextVar("capture_timing", default=None)


@contextmanager
def collect_timings() -> Generator[CaptureTiming]:
    """Isolate diagnostics between invocations, including failed captures."""
    timing = CaptureTiming()
    token = _CURRENT.set(timing)
    try:
        yield timing
    finally:
        _CURRENT.reset(token)


@contextmanager
def phase(name: str) -> Generator[None]:
    """Accumulate inclusive wall time without changing exception behavior."""
    timing = _CURRENT.get()
    if timing is None:
        yield
        return
    measurement = timing.phases.setdefault(name, PhaseTiming())
    started = time.perf_counter()
    measurement.calls += 1
    try:
        yield
    except BaseException:
        measurement.failed_calls += 1
        raise
    finally:
        measurement.elapsed_seconds += time.perf_counter() - started


def timed_phase[**P, T](name: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Measure an existing operation while preserving its signature and semantics."""

    def decorate(function: Callable[P, T]) -> Callable[P, T]:
        @wraps(function)
        def measured(*args: P.args, **kwargs: P.kwargs) -> T:
            with phase(name):
                return function(*args, **kwargs)

        return measured

    return decorate
