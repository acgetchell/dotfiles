"""Separate external log destinations from an audit's validation obligation."""

import re
import shlex
from pathlib import Path
from typing import Any


def obligation_identity(identity: dict[str, Any], repository: str) -> dict[str, Any]:
    """Normalize only declared external logs used as terminal stdout redirects."""
    commands = list(identity["commands"])
    artifacts = []
    for index, artifact in enumerate(identity["allowed_artifacts"]):
        path = artifact["path"]
        external = Path(path).is_absolute() and Path(path).resolve() == Path(path) and not Path(path).is_relative_to(Path(repository))
        suffix = re.compile(r" (?P<redirect>1?>) " + re.escape(shlex.quote(path)) + r"(?P<stderr> 2>&1)?$")
        matches = [position for position, command in enumerate(commands) if suffix.search(command)]
        if artifact["kind"] == "log" and artifact["repository_status"] == "outside-repository" and external and len(matches) == 1:
            position = matches[0]
            prefix = suffix.sub("", commands[position])
            # A path also used as an input/argument is semantically significant.
            if path not in prefix and all(path not in command for other, command in enumerate(commands) if other != position):
                commands[position] = suffix.sub(rf" \g<redirect> <external-log-{index}>\g<stderr>", commands[position])
                artifact = {**artifact, "path": f"<external-log-{index}>"}
        artifacts.append(artifact)
    return {
        **identity,
        "commands": commands,
        "allowed_artifacts": artifacts,
        # Scheduling governs when checks run, not which successful checks an
        # unchanged source judgment requires. Validators retain their exact unit.
        "execution_strategy": "<scheduling>",
        "independence_basis": "<scheduling>",
        "dependency_policy": "<scheduling>",
    }


def changed_identity_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Expose exact changed fields without weakening validator execution identity."""
    return sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
