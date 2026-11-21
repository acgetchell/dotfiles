"""Replay one benchmark trial in a fresh interpreter with the selected runtime's imports."""

import importlib
import json
import runpy
import sys
from pathlib import Path


def main(scripts: Path, fixture: Path, store: Path) -> None:
    """Verify the shared plan with this runtime and write its trial manifest to store."""
    driver = Path(__file__).resolve().with_name("review_graph_benchmark.py")
    sys.path.insert(0, str(scripts))
    runtime = importlib.import_module("review_graph_runtime")
    # The fixture owns today's skill paths and catalog. The runtime owns its
    # schema and evidence verification. Only the replay driver is shared.
    runtime.DEFAULT_SKILL_ROOT = driver.parents[2]
    runtime.DEFAULT_ROUTING_CATALOG = driver.parents[1] / "references/routing-catalog.json"
    document = json.loads(fixture.read_bytes())
    schema = json.loads(runtime._RUNTIME_OPERATION_INPUT_SCHEMA.read_bytes())  # noqa: SLF001 - the selected runtime's CLI contract.
    if "concurrent_worker_limit" not in schema["$defs"]["materialize-dispatches"]["properties"]:
        # Older materializers predate wave telemetry. The coordinator projects
        # the same four-slot schedule from the shared plan for the final report.
        document.pop("concurrent_worker_limit")

    # Early revisions predate the benchmark driver and some of its helpers.
    sys.path.append(str(driver.parent))
    replay = runpy.run_path(str(driver))["_trial"]
    replay(runtime, document, store)


if __name__ == "__main__":
    scripts_path, fixture_path, store_path = map(Path, sys.argv[1:])
    main(scripts_path, fixture_path, store_path)
