"""Conservative benchmark recipe equivalence without executing repository recipes."""

import re
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkCommand:
    """Exact Cargo target, feature, and execution-mode selections."""

    targets: tuple[str, ...]
    features: frozenset[str]
    all_features: bool
    cargo_context: tuple[str, ...]
    cargo_arguments: tuple[str, ...]
    harness_arguments: tuple[str, ...]

    @property
    def mode(self) -> str:
        """Name the requested behavior without removing harness arguments."""
        if "--no-run" in self.cargo_arguments:
            return "build-only"
        return "test" if "--test" in self.harness_arguments else "timing"


def benchmark_identity(command: str) -> BenchmarkCommand | None:  # noqa: C901
    """Retain all target selections and arguments on both sides of Cargo's --."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if len(words) < 2 or Path(words[0]).name != "cargo" or "bench" not in words:
        return None
    index = words.index("bench")
    context = tuple(words[:index])
    arguments = words[index + 1 :]
    harness: tuple[str, ...] = ()
    if "--" in arguments:
        split = arguments.index("--")
        harness = tuple(arguments[split + 1 :])
        arguments = arguments[:split]
    targets: list[str] = []
    features: set[str] = set()
    remaining: list[str] = []
    all_features = False
    cursor = 0
    while cursor < len(arguments):
        word = arguments[cursor]
        if word in {"--bench", "--features", "-F"}:
            cursor += 1
            if cursor == len(arguments):
                return None
            value = arguments[cursor]
            if word == "--bench":
                targets.append(value)
            else:
                features.update(filter(None, re.split(r"[\s,]+", value)))
        elif word.startswith("--bench="):
            targets.append(word.partition("=")[2])
        elif word.startswith("--features=") or (word.startswith("-F") and word != "-F"):
            value = word.partition("=")[2] if word.startswith("--features=") else word[2:]
            features.update(filter(None, re.split(r"[\s,]+", value)))
        elif word == "--all-features":
            all_features = True
        else:
            remaining.append(word)
        cursor += 1
    return BenchmarkCommand(tuple(sorted(set(targets))), frozenset(features), all_features, context, tuple(remaining), harness)


def benchmark_recipes(repository: Path) -> dict[str, tuple[str, str]]:
    """Recognize a single literal Cargo command with an optional variadic argument."""
    path = repository / "justfile"
    if not path.is_file():
        return {}
    recipes: dict[str, tuple[str, str]] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"(bench-[\w-]+)(?:\s+([*+]\w+))?:\s*", line)
        if match is None:
            continue
        body: list[str] = []
        for following in lines[index + 1 :]:
            if following and not following[0].isspace():
                break
            if following.strip() and not following.lstrip().startswith("#"):
                body.append(following.strip().removeprefix("@"))
        if len(body) == 1:
            recipes[match[1]] = (body[0], match[2] or "")
    return recipes


def equivalent_recipe(requested: BenchmarkCommand, recipe: tuple[str, str], name: str) -> str | None:
    """Require a recipe only when its literal expansion preserves requested behavior."""
    command, variadic = recipe
    parameter = variadic[1:]
    forwarded: tuple[str, ...] = ()
    if parameter:
        marker = re.compile(r"{{\s*" + re.escape(parameter) + r"\s*}}")
        if len(marker.findall(command)) != 1:
            return None
        base = benchmark_identity(marker.sub("", command))
        if base is None:
            return None
        if re.search(r"--\s*{{\s*" + re.escape(parameter), command):
            forwarded = requested.harness_arguments
        else:
            # Only append arguments; never discard recipe options or infer arbitrary Just expressions.
            if requested.cargo_arguments[: len(base.cargo_arguments)] != base.cargo_arguments:
                return None
            forwarded = requested.cargo_arguments[len(base.cargo_arguments) :]
            if requested.harness_arguments:
                forwarded += ("--", *requested.harness_arguments)
        command = marker.sub(lambda _match: shlex.join(forwarded), command)
        if variadic.startswith("+") and not forwarded:
            return None
    if benchmark_identity(command) != requested:
        return None
    return shlex.join(("just", name, *forwarded))
