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
    shell_expansion_free: bool

    @property
    def mode(self) -> str:
        """Name the requested behavior without removing harness arguments."""
        if "--no-run" in self.cargo_arguments:
            return "build-only"
        return "test" if "--test" in self.harness_arguments else "timing"


def _bench_subcommand(words: list[str]) -> int | None:
    """Find the first Cargo positional word after recognized global options."""
    index = 1
    if index < len(words) and words[index].startswith("+"):
        index += 1
    while index < len(words) and words[index].startswith("-"):
        word = words[index]
        if word in {"--color", "--config", "-Z", "-C"}:
            index += 2
        elif (
            word in {"--verbose", "--quiet", "--locked", "--offline", "--frozen"}
            or re.fullmatch(r"-[vq]+", word)
            or re.match(r"^(?:--(?:color|config)=.+|-[ZC].+)$", word)
        ):
            index += 1
        else:
            return None  # Unknown or informational options cannot prove benchmark execution.
    return index if index < len(words) and words[index] == "bench" else None


def benchmark_identity(command: str) -> BenchmarkCommand | None:  # noqa: C901
    """Retain all target selections and arguments on both sides of Cargo's --."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    index = _bench_subcommand(words) if words and Path(words[0]).name == "cargo" else None
    if index is None:
        return None
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
    shell_expansion_free = "\n" not in command and all(re.fullmatch(r"[A-Za-z0-9_./:=,+@%\-]+", word) is not None for word in words)
    return BenchmarkCommand(tuple(sorted(set(targets))), frozenset(features), all_features, context, tuple(remaining), harness, shell_expansion_free)


def _has_recipe_attributes(lines: list[str], index: int) -> bool:
    """Recognize attributes even when comments separate them from a recipe."""
    preceding = index - 1
    while preceding >= 0 and (not lines[preceding].strip() or lines[preceding].lstrip().startswith("#")):
        preceding -= 1
    return preceding >= 0 and lines[preceding].lstrip().startswith("[")


def benchmark_recipes(repository: Path) -> dict[str, tuple[str, str]]:
    """Recognize literal commands only where Just execution context is understood."""
    path = repository / "justfile"
    if not path.is_file():
        return {}
    recipes: dict[str, tuple[str, str]] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if any(re.match(r"^(?:set|export|unexport|import|mod)\b", line) for line in lines):
        return {}  # Global settings, exports, and imported recipes can change execution.
    for index, line in enumerate(lines):
        match = re.fullmatch(r"(bench-[\w-]+)(?:\s+([*+]\w+))?:\s*", line)
        if match is None:
            continue
        if _has_recipe_attributes(lines, index):
            continue  # Platform and execution attributes require more than a literal body.
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
        if (variadic.startswith("+") and not forwarded) or any(re.fullmatch(r"[A-Za-z0-9_./:=,+@%\-]+", argument) is None for argument in forwarded):
            return None  # Just interpolates raw values; shell quoting at invocation is lost.
        command = marker.sub(lambda _match: " ".join(forwarded), command)
    if not requested.shell_expansion_free or benchmark_identity(command) != requested:
        return None
    return shlex.join(("just", name, *forwarded))
