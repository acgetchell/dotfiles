#!/usr/bin/env python3
"""Validate DOI metadata against Markdown bibliography entries.

The default checker is dependency-free; --citation-cff additionally uses PyYAML.
It verifies that DOI labels resolve
through DOI content negotiation and compares resolved titles, authors, and years
with the local bibliography text, catching the common trust failure where a live
DOI points to an unrelated paper.
"""

import argparse
import base64
import json
import math
import re
import ssl
import sys
import urllib.request
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from hashlib import sha256
from http.client import HTTPException
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bibliography_context import (
    collect_claims,
    collect_entry,
    inline_links,
    mask_images,
    publication_years,
    reference_definition,
    reference_definitions,
    reference_uses,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from bibliography_context import CitationClaims, ReferenceDefinition

STOPWORDS = {"a", "an", "and", "are", "as", "by", "for", "from", "in", "into", "is", "it", "of", "on", "or", "the", "to", "using", "with"}
_CONTRIBUTOR_ROLE = re.compile(
    r"\b(?:translated|edited|compiled|illustrated|adapted|annotated|revised|translation|foreword|introduction|preface)\W+by\b"
    r"|\(\s*(?:translators?|editors?|compilers?|illustrators?|trans\.?|eds?\.?)\s*\)",
    re.IGNORECASE,
)
_DOI_URL = re.compile(r"https://doi\.org/(\S+)", re.IGNORECASE)
_DOI_AUTOLINK = re.compile(r"<https://doi\.org/([^<>\x00-\x20]+)>", re.IGNORECASE)


class AuditStatus(StrEnum):
    """Finite set of validation outcomes emitted by the audit."""

    OK = "OK"
    MISMATCH = "MISMATCH"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class Doi:
    """A syntactically plausible DOI label parsed from Markdown."""

    value: str

    @classmethod
    def parse(cls, raw: str) -> Doi:
        """Parse a raw DOI-ish string into a non-empty DOI label."""
        value = raw.strip().strip(".,;")
        value = re.sub(r"^https?://doi\.org/", "", value, flags=re.ASCII | re.IGNORECASE)
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
    badge_only: bool = False
    claims: CitationClaims | None = None

    @property
    def bibliographic_claims(self) -> str:
        """Use parsed visible claims while retaining raw entries for provenance."""
        return self.entry if self.claims is None else self.claims.text

    @property
    def context_only(self) -> bool:
        """Recognize links and citation pointers without discarding unknown prose."""
        return self._context_only(self.bibliographic_claims, ())

    def _context_only(self, entry: str, pointer_extensions: tuple[str, ...]) -> bool:
        """Strip link syntax while retaining words that can assert an identity."""
        definition = reference_definition(self.entry)
        if definition is not None:
            # Parsed titles are literal text. Keep a caller's extracted pointer
            # suffix instead of restoring the complete citation instructions.
            text = entry if self.claims is not None else definition[2]
        elif self.claims is None:
            text = mask_images(entry, include_links=True)
            text = re.sub(r"\[([^\]]*)\]\([^\s]+\)", r"\1", text)
        else:
            text = entry
        text = re.sub(r"(?i:https://doi\.org/)" + re.escape(self.doi.value), "", text).replace(self.doi.value, "")
        text = re.sub(r"CITATION\.cff", "", text, flags=re.IGNORECASE)
        # A deliberately small vocabulary: unknown names, dates, and titles must
        # go through the ordinary bibliography checks, never a canonical bypass.
        pointer_words = {
            "doi",
            "see",
            "for",
            "the",
            "this",
            "software",
            "project",
            "citation",
            "citations",
            "canonical",
            "metadata",
            "in",
            "of",
            "to",
            "and",
            "version",
            "concept",
            "citing",
            "cite",
            "please",
            "use",
            "repository",
            "below",
            "above",
            "tagged",
            "release",
            "releases",
            "archive",
            "archived",
            "on",
            "zenodo",
            "under",
            "all",
            "versions",
            "are",
        }
        return set(re.findall(r"\w+", text.casefold())) <= pointer_words.union(pointer_extensions)

    def canonical_pointer_context(self, citation: SoftwareCitation) -> bool:
        """Recognize citation instructions only when their named software agrees."""
        claims = self.bibliographic_claims
        request = re.match(r"If you use (.+?) in your work, cite the software using\s+", claims, flags=re.IGNORECASE)
        if request is None or identity_text(request[1]) not in {identity_text(citation.title), identity_text(citation.title.partition(":")[0])}:
            return False
        return self._context_only(
            claims[request.end() :],
            ("include", "used", "so", "others", "can", "identify", "same", "covers", "specific", "from", "corresponding", "record", "when", "an", "exact"),
        )


def identity_text(value: str) -> str:
    """Normalize punctuation and case without dropping identity-bearing words."""
    return re.sub(r"\W+", " ", value.casefold()).strip()


@dataclass(frozen=True, slots=True)
class SoftwareCitation:
    """Complete canonical software identity and the exact CFF bytes used."""

    path: str
    digest: str
    doi: Doi
    title: str
    authors: tuple[str, ...]
    year: str
    content: bytes

    @classmethod
    def load(cls, path: Path) -> SoftwareCitation:
        """Parse only root software metadata, never preferred-citation/references."""
        try:
            import yaml  # noqa: PLC0415
        except ImportError as exc:
            msg = "--citation-cff requires PyYAML; use uv run --with PyYAML"
            raise ValueError(msg) from exc
        content = path.read_bytes()
        try:
            raw = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            msg = f"invalid CITATION.cff YAML: {exc}"
            raise ValueError(msg) from exc
        if not isinstance(raw, dict) or raw.get("type", "software") != "software":
            msg = "CITATION.cff must contain root software metadata"
            raise ValueError(msg)
        title, doi = raw.get("title"), raw.get("doi")
        if not isinstance(title, str) or not identity_text(title) or not isinstance(doi, str):
            msg = "CITATION.cff requires a title and root DOI"
            raise ValueError(msg)
        released = raw.get("date-released")
        if isinstance(released, str):
            released = date.fromisoformat(released)
        if type(released) is not date:
            msg = "CITATION.cff requires a date-released calendar date"
            raise ValueError(msg)
        authors = raw.get("authors")
        if not isinstance(authors, list) or not authors:
            msg = "CITATION.cff requires authors"
            raise ValueError(msg)
        names = tuple(author.get("family-names") or author.get("name") if isinstance(author, dict) else None for author in authors)
        if any(not isinstance(name, str) or not identity_text(name) for name in names):
            msg = "CITATION.cff authors require family-names or entity names"
            raise ValueError(msg)
        return cls(
            str(path.resolve()), "sha256:" + sha256(content).hexdigest(), Doi.parse(doi), title, tuple(str(name) for name in names), str(released.year), content
        )

    def to_json_object(self) -> dict[str, object]:
        """Expose the checked identity alongside its file digest."""
        return {"path": self.path, "digest": self.digest, "doi": self.doi.value, "title": self.title, "authors": list(self.authors), "year": self.year}


def _reported_doi(raw: dict[str, Any]) -> str | None:
    """Return None for an absent CSL DOI field and raise TypeError for a present non-string value."""
    if "DOI" not in raw:
        return None
    value = raw["DOI"]
    if not isinstance(value, str):
        msg = "DOI metadata field DOI must be a string"
        raise TypeError(msg)
    return value


@dataclass(frozen=True, slots=True)
class CslMetadata:
    """Parsed DOI metadata needed for citation relevance checks."""

    title: str
    year: str | None
    container: str | None
    author_families: tuple[str, ...]
    date_provenance: tuple[tuple[str, str], ...] = ()
    authors_complete: bool = False
    reported_doi: str | None = None

    def contradicts_doi(self, expected: Doi) -> bool:
        """A present resolver claim must identify the linked DOI."""
        if self.reported_doi is None:
            return False
        try:
            resolved = Doi.parse(self.reported_doi)
        except ValueError:
            return True
        return resolved.value.casefold() != expected.value.casefold()

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> CslMetadata:
        """Parse CSL JSON from DOI content negotiation."""
        title = plain_text(raw.get("title"))
        if not title:
            msg = "DOI metadata did not contain a title"
            raise ValueError(msg)

        container = plain_text(raw.get("container-title")) or None
        dates = tuple((field, year) for field in DATE_FIELDS if (year := date_year(raw.get(field))) is not None)
        year = next((year for field, year in dates if field in PUBLICATION_DATE_FIELDS), None)
        raw_authors = raw.get("author")
        authors = author_families(raw_authors)
        authors_complete = isinstance(raw_authors, list) and bool(authors) and len(authors) == len(raw_authors)
        return cls(
            title=title,
            year=year,
            container=container,
            author_families=authors,
            date_provenance=dates,
            authors_complete=authors_complete,
            reported_doi=_reported_doi(raw),
        )


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
    local_status: AuditStatus | None = None
    canonical_software: SoftwareCitation | None = None
    date_provenance: tuple[tuple[str, str], ...] = ()
    mismatched_fields: tuple[str, ...] = ()
    local_years: tuple[str, ...] = ()

    def to_json_object(self) -> dict[str, object]:
        """Return a JSON-serializable report object."""
        result: dict[str, object] = {
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
            "date_provenance": dict(self.date_provenance),
            "mismatched_fields": list(self.mismatched_fields),
            "local_years": list(self.local_years),
        }
        if self.local_status is not None:
            result["local_status"] = self.local_status.value
        if self.canonical_software is not None:
            result["canonical_software"] = self.canonical_software.to_json_object()
        return result


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


def _definition_content(parsed: tuple[ReferenceDefinition, ...]) -> dict[int, list[str]]:
    """Keep destination and title fragments on their physical source lines."""
    definition_content: dict[int, list[str]] = {}
    for definition in parsed:
        for idx in range(definition.start, definition.end):
            definition_content[idx] = []
        definition_content[definition.destination_line].append(definition.destination)
        for offset, title_line in enumerate(definition.title.splitlines()):
            definition_content[definition.title_line + offset].append(title_line)
    return definition_content


def extract_entries(markdown: str) -> list[DoiEntry]:
    """Return bibliography occurrences in source-line order, with one-based line numbers.

    Collapse case-insensitive repeats of a DOI on the same line. Keep occurrences
    on different lines so each can be checked against its own citation context.
    """
    lines = markdown.splitlines()
    entries: list[DoiEntry] = []
    seen: set[tuple[str, int]] = set()
    parsed = reference_definitions(lines)
    definition_content = _definition_content(parsed)
    inline_content, remainder = extract_inline_dois("\n".join(lines), parsed)
    residual_lines = remainder.split("\n")

    reference_content: dict[int, list[str]] = {}
    for use in reference_uses(lines, parsed):
        if match := _DOI_URL.match(use.destination):
            reference_content.setdefault(use.line, []).append(match[1])

    for idx, line in enumerate(lines):
        if idx in definition_content:
            candidates = [raw for text in definition_content[idx] for raw in doi_candidates_from_line(text)]
        else:
            candidates = [
                *(match[1] for match in _structured_doi_matches(line)),
                *doi_candidates_from_line(residual_lines[idx]),
                *inline_content.get(idx, []),
                *reference_content.get(idx, []),
            ]
        for raw in candidates:
            try:
                doi = Doi.parse(raw)
            except ValueError:
                continue
            key = (doi.value.lower(), idx + 1)
            if key in seen:
                continue
            seen.add(key)
            paragraph = collect_entry(lines, idx, parsed)
            # Identify image-only badges while preserving ordinary citation text.
            without_badges = mask_images(paragraph, parsed, include_links=True)
            badge_only = without_badges != paragraph and not re.search(r"\w", without_badges)
            entries.append(DoiEntry(doi=doi, line=idx + 1, entry=paragraph, badge_only=badge_only, claims=collect_claims(lines, idx, parsed)))

    return entries


def _structured_doi_matches(line: str) -> list[re.Match[str]]:
    """Retain explicit DOI labels even when their inline links are consumed."""
    return [*re.finditer(r"DOI:\s*\[([^\]]+)\]", line, flags=re.IGNORECASE), *re.finditer(r"DOI:\s*<https://doi\.org/([^>]+)>", line, flags=re.IGNORECASE)]


def doi_candidates_from_line(line: str) -> list[str]:
    """Extract raw DOI candidates from one Markdown line."""
    structured = _structured_doi_matches(line)
    candidates: list[str] = [match[1] for match in structured]
    inline, line = extract_inline_dois(line)
    candidates.extend(raw for values in inline.values() for raw in values)
    for match in sorted(structured, key=lambda match: match.start(), reverse=True):
        line = line[: match.start()] + " " * (match.end() - match.start()) + line[match.end() :]
    if "doi.org/" in line.casefold():
        candidates.extend(raw_doi_urls(line))
    return candidates


def extract_inline_dois(text: str, parsed: tuple[ReferenceDefinition, ...] = ()) -> tuple[dict[int, list[str]], str]:
    """Bind inline DOI occurrences to physical lines before masking consumed links."""
    destinations: dict[int, list[str]] = {}
    links = inline_links(text, parsed)
    for link in links:
        if match := _DOI_URL.match(link.destination):
            destinations.setdefault(link.line, []).append(match[1])
        else:
            for offset, label_line in enumerate(mask_images(link.text, parsed).split("\n")):
                destinations.setdefault(link.text_line + offset, []).extend(raw_doi_urls(label_line))
    for link in sorted(links, key=lambda link: link.start, reverse=True):
        text = text[: link.start] + re.sub(r"[^\n]", " ", text[link.start : link.end]) + text[link.end :]
    return destinations, text


def raw_doi_urls(line: str) -> list[str]:
    """Extract DOI labels from raw URLs outside structured Markdown links."""
    values: list[str] = []
    cursor = 0
    for autolink in _DOI_AUTOLINK.finditer(line):
        values.extend(trim_raw_url_doi(match[1]) for match in _DOI_URL.finditer(line, cursor, autolink.start()))
        values.append(autolink[1])
        cursor = autolink.end()
    values.extend(trim_raw_url_doi(match[1]) for match in _DOI_URL.finditer(line, cursor))
    return values


def trim_raw_url_doi(value: str) -> str:
    """Trim punctuation that commonly follows a raw DOI URL in prose."""
    while value.endswith((".", ",", ";")):
        value = value[:-1]
    return value


def fetch_csl_json(doi: Doi, timeout: float) -> dict[str, Any]:
    """Resolve one DOI through content negotiation."""
    request = urllib.request.Request(
        f"https://doi.org/{doi.value}", headers={"Accept": "application/vnd.citationstyles.csl+json", "User-Agent": "scientific-citation-audit/1.0"}
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
    if not isinstance(value, str):
        return ""
    text = value
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


PUBLICATION_DATE_FIELDS = ("published-print", "published", "published-online", "issued")
DATE_FIELDS = (*PUBLICATION_DATE_FIELDS, "created", "deposited", "indexed", "updated")


def date_year(issued: object) -> str | None:
    """Extract a valid calendar year without treating deposit dates as publication."""
    if not isinstance(issued, dict):
        return None
    parts = issued.get("date-parts")
    if not isinstance(parts, list) or not parts:
        return None
    first_part = parts[0]
    if not isinstance(first_part, list) or not first_part:
        return None
    year = first_part[0]
    if type(year) in {int, str} and re.fullmatch(r"[1-9][0-9]{3}", str(year)):
        return str(year)
    return None


def issued_year(data: dict[str, Any]) -> str | None:
    """Retain the issued-field helper for callers inspecting CSL metadata."""
    return date_year(data.get("issued"))


def author_families(value: object) -> tuple[str, ...]:
    """Extract normalized author family names from CSL metadata."""
    if not isinstance(value, list):
        return ()
    families: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        family = item.get("family") or item.get("literal")
        normalized = plain_text(family) if isinstance(family, str) else ""
        if normalized:
            families.append(normalized)
    return tuple(families)


def tokens(text: str) -> set[str]:
    """Tokenize text for a conservative metadata-overlap check."""
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2 and token not in STOPWORDS}


def title_score(title: str, entry: str) -> float:
    """Return fraction of resolved title tokens present in local entry text."""
    title_tokens = tokens(title)
    if not title_tokens:
        return 0.0
    entry_tokens = tokens(entry)
    return len(title_tokens & entry_tokens) / len(title_tokens)


def author_score(author_names: Iterable[str], entry: str, title: str) -> float | None:
    """Match names only in the author-leading text before an identified title."""
    names = {normalized for name in author_names if (normalized := identity_text(name))}
    title_pattern = r"\W+".join(re.escape(word) for word in re.findall(r"\w+", title))
    if not names or not title_pattern:
        return None
    for match in re.finditer(rf"(?<!\w){title_pattern}(?!\w)", entry, flags=re.IGNORECASE):
        author_text = entry[: match.start()].rstrip(" \t*_`\"'\u201c\u2018[")
        if not any(character.isalpha() for character in author_text):
            continue
        # A title fragment inside a longer local title does not identify where
        # the authors end. Retain initials and author-date punctuation.
        if not author_text.endswith((".", ")")):
            return None
        # Mixed author/contributor prefixes need manual role attribution.
        if _CONTRIBUTOR_ROLE.search(author_text):
            return None
        normalized_authors = f" {identity_text(author_text)} "
        return sum(f" {name} " in normalized_authors for name in names) / len(names)
    return None


def validate_entry(
    entry: DoiEntry,
    timeout: float,
    min_title_score: float,
    fetcher: Callable[[Doi, float], dict[str, Any]] = fetch_csl_json,
    *,
    citation: SoftwareCitation | None = None,
) -> DoiResult:
    """Validate one DOI and compare metadata with the bibliography entry."""
    try:
        raw = fetcher(entry.doi, timeout)
        metadata = CslMetadata.parse(raw)
    except (HTTPException, OSError, TypeError, ValueError) as exc:
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

    publication_dates = {year for field, year in metadata.date_provenance if field in PUBLICATION_DATE_FIELDS}
    conflict = "resolver publication date fields disagree; inspect primary publication records" if len(publication_dates) > 1 else ""
    if entry.context_only or (citation is not None and entry.canonical_pointer_context(citation)):
        result = DoiResult(
            doi=entry.doi.value,
            line=entry.line,
            status=AuditStatus.MISMATCH if conflict else AuditStatus.INSUFFICIENT_CONTEXT,
            title_score=None,
            author_score=None,
            resolved_title=metadata.title,
            resolved_year=metadata.year,
            resolved_container=metadata.container,
            resolved_authors=metadata.author_families,
            message=conflict or "DOI resolves, but this link supplies no bibliographic context; compare its identity with CITATION.cff or primary metadata",
            date_provenance=metadata.date_provenance,
            mismatched_fields=("year",) if conflict else (),
        )
        return _reconcile_software(result, metadata, citation) if citation is not None else result

    claims = entry.bibliographic_claims
    resolved_title_score = title_score(metadata.title, claims)
    resolved_author_score = author_score(metadata.author_families, claims, metadata.title)
    problems: list[str] = []
    fields: list[str] = []
    local_years = publication_years(claims, entry.doi.value)
    if resolved_title_score < min_title_score:
        problems.append("resolved title has low overlap with local entry")
        fields.append("title")
    if resolved_author_score == 0.0:
        problems.append("resolved authors do not appear in local entry")
        fields.append("authors")
    if metadata.year is not None and local_years and metadata.year not in local_years:
        problems.append("resolved year does not appear in local entry; reconcile the cited edition or print issue with primary publication records")
        fields.append("year")
    if conflict:
        problems.append(conflict)
        if "year" not in fields:
            fields.append("year")
    if metadata.contradicts_doi(entry.doi):
        problems.append("resolved DOI differs from linked DOI")
        fields.append("doi")

    status = AuditStatus.OK if not problems else AuditStatus.MISMATCH
    message = "metadata matches local entry" if not problems else "; ".join(problems)
    if not problems and (resolved_author_score is None or not metadata.authors_complete or metadata.year is None or not local_years):
        status = AuditStatus.INSUFFICIENT_CONTEXT
        message = "citation or resolved metadata lacks complete authors or publication year; manual verification required"
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
        date_provenance=metadata.date_provenance,
        mismatched_fields=tuple(fields),
        local_years=local_years,
    )


def reconcile_software(result: DoiResult, metadata: CslMetadata, raw: dict[str, Any], citation: SoftwareCitation) -> DoiResult:
    """Reconcile pre-parsed bibliographic metadata with the DOI claim from its CSL response."""
    return _reconcile_software(result, replace(metadata, reported_doi=_reported_doi(raw)), citation)


def _reconcile_software(result: DoiResult, metadata: CslMetadata, citation: SoftwareCitation) -> DoiResult:
    """Check canonical identity only for entries without bibliographic claims."""
    problems = [result.message] if result.status == AuditStatus.MISMATCH else []
    if result.doi.casefold() != citation.doi.value.casefold():
        problems.append("linked DOI differs from canonical software DOI")
    if metadata.contradicts_doi(citation.doi):
        problems.append("resolved DOI differs from canonical software DOI")
    if identity_text(metadata.title) != identity_text(citation.title):
        problems.append("resolved title differs from canonical software title")
    if metadata.author_families and {identity_text(name) for name in metadata.author_families} != {identity_text(name) for name in citation.authors}:
        problems.append("resolved authors differ from canonical software authors")
    if metadata.year is not None and metadata.year != citation.year:
        problems.append("resolved year differs from canonical software year")
    if problems:
        status, message = AuditStatus.MISMATCH, "; ".join(problems)
    elif metadata.reported_doi is None or not metadata.authors_complete or metadata.year is None:
        status, message = AuditStatus.INSUFFICIENT_CONTEXT, "resolved software metadata lacks DOI, authors, or year"
    else:
        status, message = AuditStatus.OK, "software identity matches explicit CITATION.cff metadata"
    return replace(result, status=status, message=message, local_status=result.status, canonical_software=citation)


def validate_entries(
    entries: Iterable[DoiEntry],
    timeout: float,
    min_title_score: float,
    fetcher: Callable[[Doi, float], dict[str, Any]] = fetch_csl_json,
    *,
    citation: SoftwareCitation | None = None,
) -> list[DoiResult]:
    """Return one audit result per entry in input order.

    By default, resolve metadata at doi.org with a request timeout in seconds.
    Reuse a fetcher's returned metadata for the same DOI spelling within this
    call. A fetch that raises leaves the next occurrence free to try again.
    """
    cache: dict[str, dict[str, Any]] = {}

    def cached_fetcher(doi: Doi, request_timeout: float) -> dict[str, Any]:
        """Reuse successful responses for the same DOI spelling within this audit and let failed fetches be retried."""
        if doi.value not in cache:
            cache[doi.value] = fetcher(doi, request_timeout)
        return cache[doi.value]

    return [validate_entry(entry, timeout, min_title_score, cached_fetcher, citation=citation) for entry in entries]


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
            f"{result.resolved_title or '-'}\t{result.message}"
        )


def json_report(markdown: Path, content: bytes, citation: SoftwareCitation | None, results: Sequence[DoiResult]) -> dict[str, object]:
    """Reference exact input bytes by SHA-256 from every occurrence in the report."""
    digest = "sha256:" + sha256(content).hexdigest()
    inputs = {digest: content}
    if citation is not None:
        inputs[citation.digest] = citation.content
    source = {"path": str(markdown.resolve()), "digest": digest}
    return {
        "format": "doi-report-v2",
        "captures": {key: base64.b64encode(data).decode("ascii") for key, data in inputs.items()},
        "results": [{**result.to_json_object(), "source": source} for result in results],
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path, help="Markdown bibliography file to audit")
    parser.add_argument("--timeout", type=parse_positive_timeout, default=20.0, help="per-DOI request timeout in seconds")
    parser.add_argument("--min-title-score", type=parse_unit_interval, default=0.45, help="minimum resolved-title token overlap for OK")
    parser.add_argument("--allow-empty", action="store_true", help="exit successfully when no DOI references are found")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--citation-cff", type=Path, help="explicit canonical software metadata for DOI badges and bare links (requires PyYAML)")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Print the audit report and return 1 if any DOI result needs attention.

    Return 2 for unreadable or invalid audit inputs or an empty bibliography.
    With --allow-empty, an empty bibliography produces an empty report and exits 0.
    """
    args = build_parser().parse_args(argv)

    try:
        markdown_bytes = args.markdown.read_bytes()
        markdown = markdown_bytes.decode("utf-8")
        citation = SoftwareCitation.load(args.citation_cff) if args.citation_cff else None
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"failed to read audit input: {exc}", file=sys.stderr)
        return 2

    entries = extract_entries(markdown)
    if not entries and not args.allow_empty:
        message = f"no DOI references found in {args.markdown}"
        print(message, file=sys.stderr)
        return 2

    results = validate_entries(entries, args.timeout, args.min_title_score, citation=citation)

    if args.json:
        json.dump(json_report(args.markdown, markdown_bytes, citation, results), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_text_report(results)

    return 1 if any(result.status != AuditStatus.OK for result in results) else 0


def main() -> int:
    """Audit the bibliography named on the command line and return its exit status."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
