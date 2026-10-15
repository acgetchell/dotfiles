"""Conservative parsing of bounded readers; never execute or rewrite a ledger."""

import re
import shlex

_RG_FLAGS = frozenset(
    {
        "-n",
        "--line-number",
        "-i",
        "--ignore-case",
        "-s",
        "--case-sensitive",
        "-S",
        "--smart-case",
        "-F",
        "--fixed-strings",
        "-w",
        "--word-regexp",
        "-x",
        "--line-regexp",
        "-l",
        "--files-with-matches",
        "-c",
        "--count",
        "--count-matches",
        "--heading",
        "--no-heading",
        "--with-filename",
        "--no-filename",
        "-H",
        "-I",
        "--no-messages",
        "--hidden",
        "--no-ignore",
        "--no-config",
    }
)
_RG_COUNTS = frozenset({"-A", "-B", "-C", "-m", "--after-context", "--before-context", "--context", "--max-count"})


def shell_words(command: str) -> list[str] | None:
    """Reject substitution, compounds, redirects and ambiguous shell syntax."""
    if any(character in command for character in "`$\n\r"):
        return None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        lexer.whitespace_split = True
        lexer.commenters = ""  # An in-word hash is a filename character in the shell.
        words = list(lexer)
    except ValueError:
        return None
    return None if any(word and set(word) <= set(";&|<>()") for word in words) else words


def _rg_arguments(args: list[str]) -> list[str] | None:
    pattern = False
    index = 0
    while index < len(args):
        word = args[index]
        if word == "--":
            index += 1
            break
        if not word.startswith("-"):
            break
        if word in _RG_FLAGS:
            index += 1
            continue
        if word in _RG_COUNTS or word in {"-e", "--regexp", "--color"}:
            if index + 1 >= len(args):
                return None
            value = args[index + 1]
            if (word in _RG_COUNTS and not value.isdecimal()) or (word == "--color" and value not in {"never", "always", "auto", "ansi"}):
                return None
            pattern |= word in {"-e", "--regexp"}
            index += 2
            continue
        if re.fullmatch(r"-[ABCm]\d+|--(?:after-context|before-context|context|max-count)=\d+|--color=(?:never|always|auto|ansi)", word):
            index += 1
            continue
        return None
    if not pattern:
        index += 1
    return args[index:] if index < len(args) else None


def source_read_operands(command: str) -> tuple[str, ...] | None:  # noqa: C901, PLR0912, PLR0911 - finite command grammars fail closed.
    """Return explicit operands only for supported, read-only command forms."""
    words = shell_words(command)
    if words is None or len(words) < 2:
        return None
    name, args = words[0], words[1:]
    if name == "rg":
        operands = _rg_arguments(args)
    elif name == "sed":
        if args[:1] != ["-n"]:
            return None
        args = args[1:]
        if args[:1] == ["-e"]:
            args = args[1:]
        if not args or re.fullmatch(r"[1-9]\d*(?:,[1-9]\d*)?p", args[0]) is None:
            return None
        operands = args[1:]
    elif name == "jq":
        if args[:1] in (["-c"], ["-r"]):
            args = args[1:]
        if not args or re.fullmatch(r"\.[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", args[0]) is None:
            return None
        operands = args[1:]
    elif name in {"cat", "head", "tail", "wc", "ls"}:
        flags = {"cat": {"-n", "-b", "-s"}, "head": set(), "tail": set(), "wc": {"-l", "-c", "-w", "-m"}, "ls": {"-l", "-a", "-la", "-al", "-d"}}[name]
        while args and args[0].startswith("-") and args[0] != "--":
            word = args.pop(0)
            if word in flags:
                continue
            if name in {"head", "tail"} and word == "-n" and args and args[0].isdecimal():
                args.pop(0)
                continue
            if name in {"head", "tail"} and re.fullmatch(r"-\d+", word):
                continue
            return None
        operands = args
    else:
        return None
    if operands is None:
        return None
    if operands and operands[0] == "--":
        operands = operands[1:]
    if not operands or any(not path or path.startswith("-") or any(char in path for char in "*?[") for path in operands):
        return None
    return tuple(operands)
