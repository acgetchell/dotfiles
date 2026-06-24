#!/usr/bin/env python3
"""Validate DOI metadata against Markdown bibliography entries.

The checker is intentionally dependency-free. It verifies that DOI labels resolve
through DOI content negotiation and compares resolved titles, authors, and years
with the local bibliography text, catching the common trust failure where a live
DOI points to an unrelated paper.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "using",
    "with",
}


class AuditStatus(StrEnum):
    """Finite set of validation outcomes emitted by the audit."""

    OK = "OK"
    MISMATCH = "MISMATCH"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class Doi:
    """A syntactically plausible DOI label parsed from Markdown."""

    value: str

    @classmethod
    def parse(cls, raw: str) -> Doi:
        """Parse a raw DOI-ish string into a non-empty DOI label."""
        value = raw.strip().strip(".,;")
        if value.startswith("https://doi.org/"):
            value = value.removeprefix("https://doi.org/")
        if value.startswith("http://doi.org/"):
            value = value.removeprefix("http://doi.org/")
        if not value:
            msg = "DOI label was empty"
            raise ValueError(msg)
        if any(char.isspace() for char in value):
            msg = f"DOI label contains whitespace: {raw!r}"
            raise ValueError(msg)
        if not value.lower().startswith("10."):
            msg = f"DOI label must start with '10.': {raw!r}"
            raise ValueError(msg)
        return cls(value=value)


@dataclass(frozen=True, slots=True)
class DoiEntry:
    """A DOI occurrence and the bibliography entry that claims it."""

    doi: Doi
    line: int
    entry: str


@dataclass(frozen=True, slots=True)
class CslMetadata:
    """Parsed DOI metadata needed for citation relevance checks."""

    title: str
    year: str | None
    container: str | None
    author_families: tuple[str, ...]

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> CslMetadata:
        """Parse CSL JSON from DOI content negotiation."""
        title = plain_text(raw.get("title"))
        if not title:
            msg = "DOI metadata did not contain a title"
            raise ValueError(msg)

        container = plain_text(raw.get("container-title")) or None
        year = issued_year(raw)
        authors = author_families(raw.get("author"))
        return cls(title=title, year=year, container=container, author_families=authors)


@dataclass(frozen=True, slots=True)
class DoiResult:
    """Report row for one DOI occurrence."""

    doi: str
    line: int
    status: AuditStatus
    title_score: float | None
    author_score: float | None
    resolved_title: str | None
    resolved_year: str | None
    resolved_container: str | None
    resolved_authors: tuple[str, ...]
    message: str

    def to_json_object(self) -> dict[str, object]:
        """Return a JSON-serializable report object."""
        return {
            "doi": self.doi,
            "line": self.line,
            "status": self.status.value,
            "title_score": self.title_score,
            "author_score": self.author_score,
            "resolved_title": self.resolved_title,
            "resolved_year": self.resolved_year,
            "resolved_container": self.resolved_container,
            "resolved_authors": list(self.resolved_authors),
            "message": self.message,
        }


def parse_positive_timeout(raw: str) -> float:
    """Parse a positive finite request timeout."""
    value = float(raw)
    if not math.isfinite(value) or value <= 0.0:
        msg = f"timeout must be a positive finite number, got {raw!r}"
        raise argparse.ArgumentTypeError(msg)
    return value


def parse_unit_interval(raw: str) -> float:
    """Parse a finite threshold in the closed unit interval."""
    value = float(raw)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        msg = f"threshold must be a finite value in [0, 1], got {raw!r}"
        raise argparse.ArgumentTypeError(msg)
    return value


def extract_entries(markdown: str) -> list[DoiEntry]:
    """Extract DOI labels and nearby bibliography entries from Markdown text."""
    lines = markdown.splitlines()
    entries: list[DoiEntry] = []
    seen: set[tuple[str, int]] = set()

    for idx, line in enumerate(lines):
        candidates = doi_candidates_from_line(line)
        for raw in candidates:
            try:
                doi = Doi.parse(raw)
            except ValueError:
                continue
            key = (doi.value.lower(), idx + 1)
            if key in seen:
                continue
            seen.add(key)
            entries.append(DoiEntry(doi=doi, line=idx + 1, entry=collect_entry(lines, idx)))

    return entries


def doi_candidates_from_line(line: str) -> list[str]:
    """Extract raw DOI candidates from one Markdown line."""
    candidates: list[str] = []
    candidates.extend(re.findall(r"DOI:\s*\[([^\]]+)\]", line, flags=re.IGNORECASE))
    candidates.extend(re.findall(r"DOI:\s*<https://doi\.org/([^>]+)>", line, flags=re.IGNORECASE))
    candidates.extend(markdown_doi_link_destinations(line))
    if not candidates and "doi.org/" in line:
        candidates.extend(raw_doi_urls(line))
    return candidates


def markdown_doi_link_destinations(line: str) -> list[str]:
    """Extract DOI destinations from inline Markdown links with balanced parentheses."""
    destinations: list[str] = []
    marker = "](https://doi.org/"
    start = 0
    while True:
        marker_index = line.find(marker, start)
        if marker_index == -1:
            return destinations
        url_start = marker_index + len("](")
        cursor = url_start
        depth = 1
        while cursor < len(line):
            char = line[cursor]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    destination = line[url_start:cursor]
                    if destination.startswith("https://doi.org/"):
                        destinations.append(destination.removeprefix("https://doi.org/"))
                    start = cursor + 1
                    break
            cursor += 1
        else:
            return destinations


def raw_doi_urls(line: str) -> list[str]:
    """Extract DOI labels from raw URLs outside structured Markdown links."""
    raw_values = re.findall(r"https://doi\.org/(\S+)", line, flags=re.IGNORECASE)
    return [trim_raw_url_doi(value) for value in raw_values]


def trim_raw_url_doi(value: str) -> str:
    """Trim punctuation that commonly follows a raw DOI URL in prose."""
    while value.endswith((".", ",", ";")):
        value = value[:-1]
    return value


def collect_entry(lines: Sequence[str], doi_idx: int) -> str:
    """Collect the current bibliography item around a DOI line."""
    start = doi_idx
    while start > 0:
        prev = lines[start - 1]
        if not prev.strip():
            break
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", prev) and start - 1 != doi_idx:
            start -= 1
            break
        start -= 1

    end = doi_idx + 1
    while end < len(lines) and lines[end].strip():
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", lines[end]) and end > doi_idx + 1:
            break
        end += 1

    return " ".join(line.strip() for line in lines[start:end])


def fetch_csl_json(doi: Doi, timeout: float) -> dict[str, Any]:
    """Resolve one DOI through content negotiation."""
    request = urllib.request.Request(
        f"https://doi.org/{doi.value}",
        headers={
            "Accept": "application/vnd.citationstyles.csl+json",
            "User-Agent": "scientific-citation-audit/1.0",
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:  # noqa: S310
        payload = response.read().decode("utf-8", "replace")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        msg = f"DOI metadata response was not a JSON object for {doi.value}"
        raise TypeError(msg)
    return parsed


def plain_text(value: object) -> str:
    """Normalize CSL JSON title/container fields."""
    if isinstance(value, list):
        value = value[0] if value else ""
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def issued_year(data: dict[str, Any]) -> str | None:
    """Extract the first issued year from CSL JSON."""
    issued = data.get("issued")
    if not isinstance(issued, dict):
        return None
    parts = issued.get("date-parts")
    if not isinstance(parts, list) or not parts:
        return None
    first_part = parts[0]
    if not isinstance(first_part, list) or not first_part:
        return None
    year = first_part[0]
    if isinstance(year, int | str):
        return str(year)
    return None


def author_families(value: object) -> tuple[str, ...]:
    """Extract normalized author family names from CSL metadata."""
    if not isinstance(value, list):
        return ()
    families: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        family = item.get("family") or item.get("literal")
        normalized = plain_text(family)
        if normalized:
            families.append(normalized)
    return tuple(families)


def tokens(text: str) -> set[str]:
    """Tokenize text for a conservative metadata-overlap check."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def title_score(title: str, entry: str) -> float:
    """Return fraction of resolved title tokens present in local entry text."""
    title_tokens = tokens(title)
    if not title_tokens:
        return 0.0
    entry_tokens = tokens(entry)
    return len(title_tokens & entry_tokens) / len(title_tokens)


def author_score(author_names: Iterable[str], entry: str) -> float | None:
    """Return fraction of resolved author family names present in local entry text."""
    author_tokens = {token for name in author_names for token in tokens(name)}
    if not author_tokens:
        return None
    entry_tokens = tokens(entry)
    return len(author_tokens & entry_tokens) / len(author_tokens)


def validate_entry(
    entry: DoiEntry,
    timeout: float,
    min_title_score: float,
    fetcher: Callable[[Doi, float], dict[str, Any]] = fetch_csl_json,
) -> DoiResult:
    """Validate one DOI and compare metadata with the bibliography entry."""
    try:
        metadata = CslMetadata.parse(fetcher(entry.doi, timeout))
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        ssl.SSLError,
    ) as exc:
        return DoiResult(
            doi=entry.doi.value,
            line=entry.line,
            status=AuditStatus.FAIL,
            title_score=None,
            author_score=None,
            resolved_title=None,
            resolved_year=None,
            resolved_container=None,
            resolved_authors=(),
            message=f"{type(exc).__name__}: {exc}",
        )

    resolved_title_score = title_score(metadata.title, entry.entry)
    resolved_author_score = author_score(metadata.author_families, entry.entry)
    problems: list[str] = []
    if resolved_title_score < min_title_score:
        problems.append("resolved title has low overlap with local entry")
    if resolved_author_score == 0.0:
        problems.append("resolved authors do not appear in local entry")
    if metadata.year is not None and metadata.year not in entry.entry:
        problems.append("resolved year does not appear in local entry")

    status = AuditStatus.OK if not problems else AuditStatus.MISMATCH
    message = "metadata matches local entry" if not problems else "; ".join(problems)
    return DoiResult(
        doi=entry.doi.value,
        line=entry.line,
        status=status,
        title_score=resolved_title_score,
        author_score=resolved_author_score,
        resolved_title=metadata.title,
        resolved_year=metadata.year,
        resolved_container=metadata.container,
        resolved_authors=metadata.author_families,
        message=message,
    )


def validate_entries(
    entries: Iterable[DoiEntry],
    timeout: float,
    min_title_score: float,
    fetcher: Callable[[Doi, float], dict[str, Any]] = fetch_csl_json,
) -> list[DoiResult]:
    """Validate parsed DOI entries."""
    cache: dict[str, dict[str, Any]] = {}

    def cached_fetcher(doi: Doi, request_timeout: float) -> dict[str, Any]:
        if doi.value not in cache:
            cache[doi.value] = fetcher(doi, request_timeout)
        return cache[doi.value]

    return [validate_entry(entry, timeout, min_title_score, cached_fetcher) for entry in entries]


def print_text_report(results: Sequence[DoiResult]) -> None:
    """Emit a human-readable TSV-like report."""
    print(f"DOIs checked: {len(results)}")
    for result in results:
        title_score_text = "-" if result.title_score is None else f"{result.title_score:.2f}"
        author_score_text = "-" if result.author_score is None else f"{result.author_score:.2f}"
        print(
            f"{result.status.value}\tline={result.line}\t"
            f"title_score={title_score_text}\tauthor_score={author_score_text}\t"
            f"{result.doi}\t{result.resolved_year or '-'}\t"
            f"{result.resolved_title or result.message}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path, help="Markdown bibliography file to audit")
    parser.add_argument("--timeout", type=parse_positive_timeout, default=20.0, help="per-DOI request timeout in seconds")
    parser.add_argument(
        "--min-title-score",
        type=parse_unit_interval,
        default=0.45,
        help="minimum resolved-title token overlap for OK",
    )
    parser.add_argument("--allow-empty", action="store_true", help="exit successfully when no DOI references are found")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run the DOI audit command."""
    args = build_parser().parse_args(argv)

    try:
        markdown = args.markdown.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"failed to read {args.markdown}: {exc}", file=sys.stderr)
        return 2

    entries = extract_entries(markdown)
    if not entries:
        message = f"no DOI references found in {args.markdown}"
        if args.allow_empty:
            if args.json:
                print("[]")
            else:
                print("DOIs checked: 0")
            return 0
        print(message, file=sys.stderr)
        return 2

    results = validate_entries(entries, args.timeout, args.min_title_score)

    if args.json:
        json.dump([result.to_json_object() for result in results], sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_text_report(results)

    return 1 if any(result.status != AuditStatus.OK for result in results) else 0


def main() -> int:
    """CLI entry point."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
