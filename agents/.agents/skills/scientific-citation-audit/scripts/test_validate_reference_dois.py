#!/usr/bin/env python3
"""Fixture tests for validate_reference_dois.py."""

import base64
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).with_name("validate_reference_dois.py")
SPEC = importlib.util.spec_from_file_location("validate_reference_dois", SCRIPT)
if SPEC is None or SPEC.loader is None:
    message = "validate_reference_dois.py could not be loaded"
    raise RuntimeError(message)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def metadata(title: str, *, family: str = "Shewchuk", year: int = 1997) -> dict[str, object]:
    """Return a minimal CSL-shaped metadata fixture."""
    return {"title": title, "author": [{"family": family, "given": "J. R."}], "issued": {"date-parts": [[year]]}, "container-title": "Fixture Journal"}


@pytest.mark.parametrize("title", [{"text": "Robust predicates"}, True, 1997, [{"text": "Robust predicates"}]])
def test_metadata_cannot_turn_nontext_titles_into_identity(title: object) -> None:
    raw = metadata("Robust predicates")
    raw["title"] = title
    with pytest.raises(ValueError, match="title"):
        MODULE.CslMetadata.parse(raw)


@pytest.mark.parametrize("field", ["family", "literal"])
@pytest.mark.parametrize("family", [{"text": "Shewchuk"}, True, 1997, ["Shewchuk"]])
def test_metadata_cannot_turn_nontext_authors_into_complete_identity(field: str, family: object) -> None:
    raw = metadata("Robust predicates")
    raw["author"] = [{field: family}]
    parsed = MODULE.CslMetadata.parse(raw)
    assert parsed.author_families == ()
    assert not parsed.authors_complete
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/test"), 1, "Shewchuk. Robust predicates. (1997).")
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: raw)
    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT


def test_metadata_preserves_text_lists_for_titles_and_containers() -> None:
    raw = metadata("Robust predicates")
    raw["title"] = ["<i>Robust predicates</i>"]
    raw["container-title"] = ["Fixture Journal"]
    parsed = MODULE.CslMetadata.parse(raw)
    assert parsed.title == "Robust predicates"
    assert parsed.container == "Fixture Journal"
    assert parsed.author_families == ("Shewchuk",)
    assert parsed.authors_complete


@pytest.mark.parametrize("doi", ["10.1007/example", "10.12345/paper.2018", "10.1007/example.2018"])
def test_doi_digits_and_link_destinations_are_not_publication_years(doi: str) -> None:
    entry = MODULE.extract_entries(f"Shewchuk. Robust predicates. (1997). DOI: [{doi}](https://doi.org/{doi}) [archive](https://example.org/2020)")[0]
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Robust predicates", year=2018))
    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.local_years == ("1997",)
    assert result.mismatched_fields == ("year",)


@pytest.mark.parametrize("marker", ["-", "+", "*", "1.", "1)"])
def test_adjacent_list_entries_keep_only_their_own_claims(marker: str) -> None:
    markdown = (
        f"{marker} Shewchuk. Robust predicates. (1997). DOI: https://doi.org/10.1007/example\n"
        f"{marker} Smith. Other paper. (2005). DOI: https://doi.org/10.12345/other\n"
    )
    entries = MODULE.extract_entries(markdown)
    assert len(entries) == 2
    first = MODULE.validate_entry(entries[0], 1.0, 0.45, lambda *_: metadata("Robust predicates"))
    second = MODULE.validate_entry(entries[1], 1.0, 0.45, lambda *_: metadata("Other paper", family="Smith", year=2005))
    assert first.status == second.status == MODULE.AuditStatus.OK
    assert first.local_years == ("1997",)
    assert second.local_years == ("2005",)


@pytest.mark.parametrize(
    ("doi", "title", "authors", "local_year", "resolver_year"),
    [
        ("10.24033/rhm.30", "La méthode de Cholesky", ["Brezinski"], 2005, 2018),
        ("10.56021/9781421407944", "Matrix Computations", ["Golub", "Van Loan"], 2013, 2012),
        *[
            ("10.1234/date-fixture", "Date provenance fixture", ["Fixture"], local, resolver)
            for local, resolver in ((1990, 2006), (2002, 2012), (2017, 2018), (2005, 2006))
        ],
    ],
)
def test_primary_publication_date_disagreements_retain_provenance(doi: str, title: str, authors: list[str], local_year: int, resolver_year: int) -> None:
    entry = MODULE.DoiEntry(MODULE.Doi.parse(doi), 1, f"{', '.join(authors)}. {title}. ({local_year}). DOI: {doi}")
    raw = {
        "title": title,
        "DOI": doi,
        "author": [{"family": name} for name in authors],
        "issued": {"date-parts": [[resolver_year]]},
        "created": {"date-parts": [[2020]]},
    }
    result = MODULE.validate_entry(entry, 1, 0.45, lambda *_: raw)
    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.mismatched_fields == ("year",)
    assert result.local_years == (str(local_year),)
    assert result.resolved_year == str(resolver_year)
    assert result.to_json_object()["date_provenance"] == {"issued": str(resolver_year), "created": "2020"}
    raw["published-print"] = {"date-parts": [[local_year]]}
    preferred = MODULE.validate_entry(entry, 1, 0.45, lambda *_: raw)
    assert preferred.resolved_year == str(local_year)
    assert preferred.status == MODULE.AuditStatus.MISMATCH
    assert "date fields disagree" in preferred.message


@pytest.mark.parametrize("field", ["created", "deposited", "indexed", "updated"])
def test_deposit_year_is_not_a_publication_year(field: str) -> None:
    raw = metadata("Example")
    del raw["issued"]
    raw[field] = {"date-parts": [[2020]]}
    parsed = MODULE.CslMetadata.parse(raw)
    assert parsed.year is None
    assert parsed.date_provenance == ((field, "2020"),)


@pytest.mark.parametrize("resolver", ["https://doi.org/", "HTTPS://doi.org/", "https://DOI.ORG/", "HtTpS://DoI.OrG/"])
def test_cff_pointer_above_concept_doi_has_insufficient_context(resolver: str) -> None:
    entry = MODULE.extract_entries(f"For citing this software, please see [CITATION.cff](CITATION.cff).\nConcept DOI: {resolver}10.5281/zenodo.18158926")[0]
    assert entry.context_only
    result = MODULE.validate_entry(entry, 1, 0.45, lambda *_: metadata("Linear Algebra Stack", family="Getchell", year=2026))
    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    release_pointer = MODULE.extract_entries(
        f"Tagged releases are archived on Zenodo under the all-versions concept DOI\n[10.5281/zenodo.18158926]({resolver}10.5281/zenodo.18158926)."
    )[0]
    assert release_pointer.context_only
    alternate = MODULE.extract_entries(f"Software releases archived on Zenodo; concept DOI: {resolver}10.5281/zenodo.18158926")[0]
    assert alternate.context_only
    bibliographic = MODULE.extract_entries(f"Getchell. Software releases archived on Zenodo (2026). DOI: {resolver}10.5281/zenodo.18158926")[0]
    assert not bibliographic.context_only


def test_extracts_doi_label_with_parentheses_and_angle_tokens() -> None:
    """DOI labels preserve full DOI text even when URLs are Markdown-hostile."""
    markdown = (
        "- Field. DOI: [10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H]"
        "(https://doi.org/10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H)"
    )

    entries = MODULE.extract_entries(markdown)

    assert len(entries) == 1
    assert entries[0].doi.value == "10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H"


def test_extracts_markdown_link_destination_with_balanced_parentheses() -> None:
    """Markdown DOI links with balanced parentheses are parsed as one destination."""
    markdown = "- Field. [doi](https://doi.org/10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H)"

    entries = MODULE.extract_entries(markdown)

    assert len(entries) == 1
    assert entries[0].doi.value == "10.1002/(SICI)1097-0207(20000210)47:4<887::AID-NME804>3.0.CO;2-H"


def test_extracts_raw_url_with_trailing_period() -> None:
    """Raw DOI URLs tolerate prose trailing punctuation."""
    markdown = "- Shewchuk. https://doi.org/10.1007/PL00009321."

    entries = MODULE.extract_entries(markdown)

    assert len(entries) == 1
    assert entries[0].doi.value == "10.1007/PL00009321"


def test_validation_flags_author_mismatch() -> None:
    """A matching title with unrelated local author text is still a mismatch."""
    entry = MODULE.DoiEntry(
        doi=MODULE.Doi.parse("10.1007/PL00009321"),
        line=1,
        entry="- Wrong, A. Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates. 1997.",
    )

    result = MODULE.validate_entry(
        entry,
        1.0,
        0.45,
        fetcher=lambda _doi, _timeout: metadata(
            "Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates", family="Shewchuk", year=1997
        ),
    )

    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.author_score == 0.0
    assert "authors" in result.message


def test_validation_accepts_matching_title_author_and_year() -> None:
    """Matching title, author, and year produce an OK result."""
    entry = MODULE.DoiEntry(
        doi=MODULE.Doi.parse("10.1007/PL00009321"),
        line=1,
        entry="- Shewchuk, J. R. Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates. 1997.",
    )

    result = MODULE.validate_entry(
        entry,
        1.0,
        0.45,
        fetcher=lambda _doi, _timeout: metadata(
            "Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates", family="Shewchuk", year=1997
        ),
    )

    assert result.status == MODULE.AuditStatus.OK


@pytest.mark.parametrize("missing_fields", [("author",), ("issued",), ("author", "issued")])
def test_incomplete_scholarly_metadata_requires_manual_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], missing_fields: tuple[str, ...]
) -> None:
    path = tmp_path / "REFERENCES.md"
    path.write_text("Shewchuk. Robust predicates. (1997). DOI: https://doi.org/10.1234/test\n", encoding="utf-8")
    raw = metadata("Robust predicates")
    for field in missing_fields:
        del raw[field]
    original = MODULE.validate_entries
    monkeypatch.setattr(MODULE, "validate_entries", lambda entries, timeout, score, **kwargs: original(entries, timeout, score, lambda *_: raw, **kwargs))

    assert MODULE.run([str(path), "--json"]) == 1
    output = capsys.readouterr()
    assert output.err == ""
    result = json.loads(output.out)[0]
    assert result["status"] == "INSUFFICIENT_CONTEXT"
    assert result["resolved_title"] == "Robust predicates"
    assert result["resolved_authors"] == ([] if "author" in missing_fields else ["Shewchuk"])
    assert result["resolved_year"] == (None if "issued" in missing_fields else "1997")
    assert result["mismatched_fields"] == []
    assert "manual verification" in result["message"]


@pytest.mark.parametrize(
    ("missing_field", "mismatch", "value", "expected_field"),
    [
        ("issued", "author", [{"family": "Wrong"}], "authors"),
        ("author", "issued", {"date-parts": [[1900]]}, "year"),
        ("author", "title", "Unrelated geometry", "title"),
    ],
)
def test_incomplete_scholarly_metadata_preserves_known_mismatches(missing_field: str, mismatch: str, value: object, expected_field: str) -> None:
    raw = metadata("Robust predicates")
    del raw[missing_field]
    raw[mismatch] = value
    entry = MODULE.extract_entries("Shewchuk. Robust predicates. (1997). DOI: https://doi.org/10.1234/test")[0]

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: raw)

    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.mismatched_fields == (expected_field,)


@pytest.mark.parametrize(
    ("resolved_author", "local_author", "matches"),
    [("Li", "Li", True), ("Wu", "Wu", True), ("Ng", "Ng", True), ("Li", "Liu", False), ("Van Loan", "Loan", False), ("García", "GARCÍA", True)],
)
def test_scholarly_authors_match_complete_names_without_title_token_filters(resolved_author: str, local_author: str, matches: bool) -> None:
    entry = MODULE.extract_entries(f"{local_author}. Robust predicates. (1997). DOI: https://doi.org/10.1234/test")[0]

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Robust predicates", family=resolved_author))

    assert result.status == (MODULE.AuditStatus.OK if matches else MODULE.AuditStatus.MISMATCH)
    assert result.author_score == (1.0 if matches else 0.0)
    assert result.mismatched_fields == (() if matches else ("authors",))


@pytest.mark.parametrize("local_author", ["Wrong", "Li"])
@pytest.mark.parametrize("citation", ["{author}. {title}. (1997).", "{author}, J. R. (1997). *{title}*.", "J. R. {author}. {title}. 1997."])
def test_title_surname_is_not_author_evidence(local_author: str, citation: str) -> None:
    title = "Li distribution and robust predicates"
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/test"), 1, citation.format(author=local_author, title=title))

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata(title, family="Li"))

    assert result.title_score == 1.0
    assert result.author_score == (1.0 if local_author == "Li" else 0.0)
    assert result.status == (MODULE.AuditStatus.OK if local_author == "Li" else MODULE.AuditStatus.MISMATCH)
    assert result.mismatched_fields == (() if local_author == "Li" else ("authors",))


@pytest.mark.parametrize("citation", ["Li distribution and robust predicates. 1997.", "Wrong. Li distribution with robust predicates. 1997."])
def test_missing_or_unidentified_author_context_requires_manual_verification(citation: str) -> None:
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/test"), 1, citation)

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Li distribution and robust predicates", family="Li"))

    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    assert result.author_score is None
    assert result.mismatched_fields == ()


def test_partial_title_match_does_not_extend_author_evidence_into_title() -> None:
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/test"), 1, "Wrong. Li robust predicates. 1997.")

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Robust predicates", family="Li"))

    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    assert result.author_score is None
    assert result.title_score == 1.0


@pytest.mark.parametrize("author", ["Li", "Wrong"])
def test_title_equal_to_surname_keeps_author_and_title_occurrences_separate(author: str) -> None:
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/test"), 1, f"{author}. Li. 1997.")

    result = MODULE.validate_entry(entry, 1.0, 0.0, lambda *_: metadata("Li", family="Li"))

    assert result.status == (MODULE.AuditStatus.OK if author == "Li" else MODULE.AuditStatus.MISMATCH)
    assert result.author_score == (1.0 if author == "Li" else 0.0)


@pytest.mark.parametrize(
    "prefix",
    [
        "Wrong. Translated by Li.",
        "Translated by Li.",
        "Wrong. **TRANSLATED BY** Li.",
        "Wrong. Edited by Li.",
        "Wrong. Li (translator).",
        "Wrong. Li (ed.).",
        "Li. Translated by Jones.",
    ],
)
def test_contributor_roles_do_not_supply_author_evidence(prefix: str) -> None:
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/test"), 1, f"{prefix} Robust predicates. 1997.")

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Robust predicates", family="Li"))

    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    assert result.author_score is None
    assert result.title_score == 1.0
    assert result.resolved_year == "1997"
    assert result.mismatched_fields == ()
    assert "manual verification" in result.message


@pytest.mark.parametrize("author", ["Li", "Editor"])
def test_contributor_words_outside_role_markers_do_not_hide_matching_authors(author: str) -> None:
    title = "Translated by the sea"
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/test"), 1, f"{author}. {title}. 1997.")

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata(title, family=author))

    assert result.status == MODULE.AuditStatus.OK
    assert result.author_score == 1.0


def test_contributor_ambiguity_preserves_a_definite_year_mismatch() -> None:
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/test"), 1, "Wrong. Translated by Li. Robust predicates. 1900.")

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Robust predicates", family="Li"))

    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.mismatched_fields == ("year",)
    assert result.author_score is None


@pytest.mark.parametrize(("local_year", "status"), [("", "INSUFFICIENT_CONTEXT"), ("(1997).", "OK"), ("(1900).", "MISMATCH")])
def test_scholarly_year_comparison_distinguishes_absence_from_conflict(local_year: str, status: str) -> None:
    entry = MODULE.extract_entries(f"Shewchuk. Robust predicates. {local_year} DOI: https://doi.org/10.1234/test")[0]

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Robust predicates"))

    assert result.status.value == status
    assert result.resolved_year == "1997"
    assert result.mismatched_fields == (("year",) if status == "MISMATCH" else ())
    if not local_year:
        assert result.local_years == ()
        assert "manual verification" in result.message


@pytest.mark.parametrize("incomplete_author", [{"given": "A."}, {}, {"family": "", "literal": ""}, None, "Unknown"])
def test_one_incomplete_resolver_author_prevents_scholarly_success(incomplete_author: object) -> None:
    raw = metadata("Robust predicates")
    raw["author"] = [{"family": "Shewchuk"}, incomplete_author]
    entry = MODULE.extract_entries("Shewchuk. Robust predicates. (1997). DOI: https://doi.org/10.1234/test")[0]

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: raw)

    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    assert result.resolved_authors == ("Shewchuk",)
    assert result.author_score == 1.0
    assert result.mismatched_fields == ()


@pytest.mark.parametrize("author", [{"family": "Li"}, {"literal": "Li"}, {"family": "", "literal": "Li"}])
def test_complete_author_records_accept_family_or_literal(author: dict[str, str]) -> None:
    raw = metadata("Robust predicates")
    raw["author"] = [author]
    entry = MODULE.DoiEntry(MODULE.Doi.parse("10.1234/example"), 1, "Li. (1997). Robust predicates. DOI: 10.1234/example")

    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: raw)

    assert result.status == MODULE.AuditStatus.OK
    assert result.resolved_authors == ("Li",)


def test_validation_reports_malformed_fetcher_response() -> None:
    """Malformed resolver data should produce a failed audit result."""
    entry = MODULE.DoiEntry(doi=MODULE.Doi.parse("10.1007/PL00009321"), line=1, entry="- Fixture entry.")

    def malformed_fetcher(_doi: object, _timeout: float) -> dict[str, object]:
        message = "DOI resolver response must be a JSON object"
        raise TypeError(message)

    result = MODULE.validate_entry(entry, 1.0, 0.45, fetcher=malformed_fetcher)

    assert result.status == MODULE.AuditStatus.FAIL
    assert result.message == "TypeError: DOI resolver response must be a JSON object"


@pytest.mark.parametrize("heading", ["# Project\n\n", "# Project\n", "### Project\n", "   ###### Project\n", "#\tProject\n", "#\n"])
def test_resolved_badge_needs_context_instead_of_reporting_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], heading: str
) -> None:
    path = tmp_path / "README.md"
    path.write_text(f"{heading}[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.123.svg)](https://doi.org/10.5281/zenodo.123)\n", encoding="utf-8")
    original = MODULE.validate_entries
    monkeypatch.setattr(
        MODULE,
        "validate_entries",
        lambda entries, timeout, score, **kwargs: original(entries, timeout, score, lambda *_: metadata("Project", family="Author", year=2026), **kwargs),
    )
    assert MODULE.run([str(path), "--json"]) == 1
    result = json.loads(capsys.readouterr().out)[0]
    assert result["status"] == "INSUFFICIENT_CONTEXT"
    assert result["line"] == heading.count("\n") + 1
    assert result["resolved_title"] == "Project"
    assert result["resolved_authors"] == ["Author"]
    assert result["title_score"] is None
    assert result["author_score"] is None
    assert "no bibliographic context" in result["message"]


def test_heading_after_badge_terminates_entry() -> None:
    badge = "[![DOI](https://example.org/badge.svg)](https://doi.org/10.1234/test)"
    entry = MODULE.extract_entries(f"{badge}\n## Unrelated section\nOther text.")[0]
    assert entry.entry == badge
    assert entry.badge_only


def test_badge_does_not_hide_contradictory_bibliographic_context() -> None:
    entry = MODULE.extract_entries("Wrong. Unrelated science. 2001.\n[![DOI](https://example.org/badge.svg)](https://doi.org/10.1234/test)")[0]
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: metadata("Actual title", year=2026))
    assert result.status == MODULE.AuditStatus.MISMATCH


def test_unresolved_badge_is_still_a_resolution_failure() -> None:
    entry = MODULE.extract_entries("[![DOI](https://example.org/badge.svg)](https://doi.org/10.1234/test)")[0]

    def unavailable(*_args: object) -> dict[str, object]:
        message = "resolver unavailable"
        raise TimeoutError(message)

    assert MODULE.validate_entry(entry, 1.0, 0.45, unavailable).status == MODULE.AuditStatus.FAIL


SOFTWARE_DOI = "10.5281/zenodo.20033111"
SOFTWARE_TITLE = "markov-chain-monte-carlo: A composable MCMC framework for Rust"
CFF = f"""cff-version: 1.2.0
type: software
title: "{SOFTWARE_TITLE}"
doi: {SOFTWARE_DOI}
authors:
  - family-names: Getchell
    given-names: Adam
date-released: 2026-09-28
"""
SOFTWARE_LINKS = [
    f"[![DOI](https://zenodo.org/badge/DOI/{SOFTWARE_DOI}.svg)](https://doi.org/{SOFTWARE_DOI})",
    f"DOI: [{SOFTWARE_DOI}](https://doi.org/{SOFTWARE_DOI})",
    f"For software citation metadata, see [CITATION.cff](CITATION.cff). https://doi.org/{SOFTWARE_DOI}",
    f"- DOI: <https://doi.org/{SOFTWARE_DOI}>\n- Citation metadata: [CITATION.cff](CITATION.cff)",
    f"- DOI: <https://doi.org/{SOFTWARE_DOI}>\n- Citation metadata: [CITATION.cff][citation-metadata]",
    f"Tagged releases are archived on Zenodo under the all-versions concept DOI\n[{SOFTWARE_DOI}](https://doi.org/{SOFTWARE_DOI}).",
    f"For citations of this software, see [CITATION.cff](CITATION.cff) and the DOI: https://doi.org/{SOFTWARE_DOI}",
]

README_BADGES = SOFTWARE_LINKS[0] + "\n[![PyPI version][pypi-badge]][pypi]\n[![License][license-badge]][license]\n[![CI][ci-badge]][ci-workflow]"
README_BADGE_DEFINITIONS = (
    "\n\n[pypi-badge]: https://example.org/pypi.svg\n[pypi]: https://example.org/pypi\n"
    "[license-badge]: https://example.org/license.svg\n[license]: https://example.org/license\n"
    "[ci-badge]: https://example.org/ci.svg\n[ci-workflow]: https://example.org/ci"
)
README_DEFINITIONS = (
    "[dependency-sources]: https://example.org/docs/dependency-sources\n"
    f"[doi]: https://doi.org/{SOFTWARE_DOI}\n"
    "[draft-api]: https://example.org/docs/release-evidence-api#draft-preparation"
)


@pytest.mark.parametrize(("layout", "line"), [(README_BADGES + README_BADGE_DEFINITIONS, 1), (README_DEFINITIONS, 2)])
def test_readme_badge_and_definition_blocks_use_canonical_identity(tmp_path: Path, layout: str, line: int) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entries = MODULE.extract_entries(layout)
    assert [(entry.doi.value, entry.line) for entry in entries] == [(SOFTWARE_DOI, line)]
    original = MODULE.validate_entries(entries, 1, 0.45, lambda *_: software_metadata())
    assert original[0].status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    checked = MODULE.validate_entries(entries, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert checked[0].status == MODULE.AuditStatus.OK
    assert checked[0].local_status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    assert checked[0].canonical_software is not None


def test_badge_layout_without_definitions_retains_literal_text(tmp_path: Path) -> None:
    """The original incomplete fixture renders literal markup under CommonMark."""
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(README_BADGES)[0]
    row = MODULE.validate_entries([entry], 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))[0]
    assert entry.entry == " ".join(README_BADGES.splitlines())
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.canonical_software is None


@pytest.mark.parametrize("definition_first", [False, True])
def test_definition_blocks_do_not_absorb_adjacent_real_citations(tmp_path: Path, definition_first: bool) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    citation = "Shewchuk. Robust predicates. (1997). DOI: https://doi.org/10.1234/paper"
    blocks = [README_DEFINITIONS, citation] if definition_first else [citation, README_DEFINITIONS]
    entries = MODULE.extract_entries("\n".join(blocks))
    rows = MODULE.validate_entries(
        entries,
        1,
        0.45,
        lambda doi, _: software_metadata() if doi.value == SOFTWARE_DOI else metadata("Robust predicates"),
        citation=MODULE.SoftwareCitation.load(cff),
    )
    assert len(rows) == 2
    assert all(row.status == MODULE.AuditStatus.OK for row in rows)
    paper = next(row for row in rows if row.doi == "10.1234/paper")
    assert paper.canonical_software is None
    assert paper.local_years == ("1997",)


@pytest.mark.parametrize("claim", ["Wrong, A. " + SOFTWARE_TITLE + ". 2026.", "Getchell. Unrelated science. 2026.", "Getchell. " + SOFTWARE_TITLE + ". 2001."])
@pytest.mark.parametrize("reference", [False, True])
def test_readme_markup_preserves_conflicting_visible_claims(tmp_path: Path, claim: str, reference: bool) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f"[{claim}][doi]\n\n{README_DEFINITIONS}" if reference else claim + "\n" + README_BADGES
    rows = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert rows[0].line == (1 if reference else 2)
    assert rows[0].status == MODULE.AuditStatus.MISMATCH
    assert rows[0].canonical_software is None
    if reference:
        assert len(rows) == 2
        assert rows[1].status == MODULE.AuditStatus.OK
        assert rows[1].canonical_software is not None


@pytest.mark.parametrize("name", [SOFTWARE_TITLE.partition(":")[0], "unrelated-project"])
@pytest.mark.parametrize("inline_pointer", [False, True])
@pytest.mark.parametrize("linked_name", [False, True])
def test_named_citation_instructions_require_the_same_canonical_software(tmp_path: Path, name: str, inline_pointer: bool, linked_name: bool) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    displayed_name = f"[{name}](https://example.org/software)" if linked_name else name
    pointer = f"[Zenodo concept DOI](https://doi.org/{SOFTWARE_DOI})" if inline_pointer else "[Zenodo concept DOI][doi]"
    text = (
        f"If you use {displayed_name} in your work, cite the software using\n"
        "[CITATION.cff](https://example.org/CITATION.cff).\n"
        "Include the version used so others can identify the same release. The\n"
        f"{pointer} covers all versions; use the version-specific DOI from\n"
        "the corresponding Zenodo record when citing an exact release.\n\n" + README_DEFINITIONS
    )
    rows = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert [row.line for row in rows] == [4, 8]
    assert (rows[0].status == MODULE.AuditStatus.OK) is (name == SOFTWARE_TITLE.partition(":")[0])
    assert (rows[0].canonical_software is not None) is (name == SOFTWARE_TITLE.partition(":")[0])
    assert rows[1].status == MODULE.AuditStatus.OK


def test_named_pointer_vocabulary_does_not_weaken_ordinary_title_claims(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(f"Exact record. https://doi.org/{SOFTWARE_DOI}")[0]
    row = MODULE.validate_entry(entry, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.mismatched_fields == ("title",)
    assert row.canonical_software is None


@pytest.mark.parametrize(
    "link", ["[DOI][Software DOI]", "[Software DOI][]", "[Software DOI]", "[![DOI][badge]][Software DOI]", "[![DOI](badge.svg)][Software DOI]"]
)
def test_reference_forms_retain_use_and_definition_occurrences(tmp_path: Path, link: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = link + f"\n\n[software   doi]: <https://doi.org/{SOFTWARE_DOI}>\n[badge]: https://example.org/badge.svg"
    entries = MODULE.extract_entries(text)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(1, SOFTWARE_DOI), (3, SOFTWARE_DOI)]
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert all(row.status == MODULE.AuditStatus.OK for row in rows)


@pytest.mark.parametrize("link", [r"\[DOI]", "[DOI](https://example.org/another-target)", "[DOI][undefined]"])
def test_unrelated_link_syntax_does_not_create_a_reference_occurrence(link: str) -> None:
    entries = MODULE.extract_entries(link + f"\n\n[doi]: https://doi.org/{SOFTWARE_DOI}")
    assert [entry.line for entry in entries] == [3]


@pytest.mark.parametrize("separator", [" ", "\n  ", "\n"])
def test_reference_definition_title_retains_local_claims(tmp_path: Path, separator: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(f'[doi]: https://doi.org/{SOFTWARE_DOI}{separator}"Wrong. Unrelated science. 2001."')[0]
    row = MODULE.validate_entry(entry, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.canonical_software is None
    assert row.local_years == ("2001",)


def test_multiline_definition_title_does_not_contaminate_next_citation(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f'[doi]: https://doi.org/{SOFTWARE_DOI}\n  "Wrong.\n  Unrelated science. 2001."\nShewchuk. Robust predicates. 1997. https://doi.org/10.1234/paper'
    rows = MODULE.validate_entries(
        MODULE.extract_entries(text),
        1,
        0.45,
        lambda doi, _: software_metadata() if doi.value == SOFTWARE_DOI else metadata("Robust predicates"),
        citation=MODULE.SoftwareCitation.load(cff),
    )
    assert [(row.line, row.status) for row in rows] == [(1, MODULE.AuditStatus.MISMATCH), (4, MODULE.AuditStatus.OK)]
    assert rows[1].local_years == ("1997",)


@pytest.mark.parametrize("angle_destination", [False, True])
@pytest.mark.parametrize(
    ("claim", "status"),
    [
        (f"Getchell. {SOFTWARE_TITLE}. 2026.", MODULE.AuditStatus.OK),
        (f"Wrong, A. {SOFTWARE_TITLE}. 2026.", MODULE.AuditStatus.MISMATCH),
        ("Getchell. Unrelated science. 2026.", MODULE.AuditStatus.MISMATCH),
        (f"Getchell. {SOFTWARE_TITLE}. 2001.", MODULE.AuditStatus.MISMATCH),
    ],
)
def test_reference_destination_on_next_line_preserves_use_claims(tmp_path: Path, angle_destination: bool, claim: str, status: Any) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    destination = f"https://doi.org/{SOFTWARE_DOI}"
    if angle_destination:
        destination = f"<{destination}>"
    text = f"[{claim}][doi]\n\n[doi]:\n  {destination}\n[guide]: https://example.org/guide"
    entries = MODULE.extract_entries(text)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(1, SOFTWARE_DOI), (4, SOFTWARE_DOI)]
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert [row.status for row in rows] == [status, MODULE.AuditStatus.OK]
    assert rows[0].canonical_software is None
    assert rows[1].canonical_software is not None


def test_continued_definition_retains_title_and_adjacent_citation_boundaries(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f'[doi]:\n  https://doi.org/{SOFTWARE_DOI}\n  "Wrong.\n  Unrelated science. 2001."\nShewchuk. Robust predicates. 1997. https://doi.org/10.1234/paper'
    rows = MODULE.validate_entries(
        MODULE.extract_entries(text),
        1,
        0.45,
        lambda doi, _: software_metadata() if doi.value == SOFTWARE_DOI else metadata("Robust predicates"),
        citation=MODULE.SoftwareCitation.load(cff),
    )
    assert [(row.line, row.status) for row in rows] == [(2, MODULE.AuditStatus.MISMATCH), (5, MODULE.AuditStatus.OK)]
    assert rows[0].local_years == ("2001",)
    assert rows[1].local_years == ("1997",)


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("[^paper]: Shewchuk. Robust predicates. (1997). DOI: https://doi.org/10.1234/paper", 1),
        ("[^paper]: Shewchuk.\n    Robust predicates. (1997). DOI: https://doi.org/10.1234/paper", 2),
        ("[paper]: Shewchuk. Robust predicates. (1997). DOI: https://doi.org/10.1234/paper", 1),
        ('[archive]: https://example.org "Shewchuk. Robust predicates. (1997). https://doi.org/10.1234/paper"', 1),
    ],
)
def test_reference_detection_never_drops_bibliographic_doi_occurrences(text: str, line: int) -> None:
    entries = MODULE.extract_entries(text)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(line, "10.1234/paper")]
    row = MODULE.validate_entry(entries[0], 1, 0.45, lambda *_: metadata("Robust predicates"))
    assert row.status == MODULE.AuditStatus.OK
    assert row.canonical_software is None
    assert row.local_years == ("1997",)


def test_definition_destination_and_title_keep_distinct_doi_occurrences() -> None:
    text = f'[archive]: https://doi.org/{SOFTWARE_DOI} "DOI: [10.1234/paper](https://doi.org/10.1234/paper)"'
    assert [(entry.line, entry.doi.value) for entry in MODULE.extract_entries(text)] == [(1, SOFTWARE_DOI), (1, "10.1234/paper")]


@pytest.mark.parametrize("tail", ['"DOI" Wrong. Unrelated science. 2001.', '"DOI Wrong. Unrelated science. 2001.', "Wrong. Unrelated science. 2001."])
def test_invalid_definition_tail_remains_an_ordinary_citation(tmp_path: Path, tail: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f"[doi]\n\n[1]: Wrong. Unrelated science. 2001. https://doi.org/{SOFTWARE_DOI}\n\n[doi]: https://doi.org/{SOFTWARE_DOI} {tail}"
    entries = MODULE.extract_entries(text)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(3, SOFTWARE_DOI), (5, SOFTWARE_DOI)]
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert all(row.status == MODULE.AuditStatus.MISMATCH and row.canonical_software is None for row in rows)
    assert all(row.local_years == ("2001",) for row in rows)


@pytest.mark.parametrize("split_destination", [False, True])
def test_multiline_reference_label_retains_conflicting_use(tmp_path: Path, split_destination: bool) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    separator = "\n  " if split_destination else " "
    text = f"[Wrong. Unrelated science. 2001.][SOFTWARE concept doi]\n\n[software\nconcept\ndoi]:{separator}<https://doi.org/{SOFTWARE_DOI}>"
    entries = MODULE.extract_entries(text)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(1, SOFTWARE_DOI), (6 if split_destination else 5, SOFTWARE_DOI)]
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert [row.status for row in rows] == [MODULE.AuditStatus.MISMATCH, MODULE.AuditStatus.OK]
    assert rows[0].canonical_software is None
    assert rows[0].local_years == ("2001",)


@pytest.mark.parametrize("marker", ["-", "1.", "#", "[other]:"])
@pytest.mark.parametrize("delimiters", ['""', "''", "()"])
def test_block_markers_inside_open_definition_title_retain_claims(tmp_path: Path, marker: str, delimiters: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = (
        f"[doi]: https://doi.org/{SOFTWARE_DOI} {delimiters[0]}DOI\n{marker} Wrong. Unrelated science. 2001.{delimiters[1]}\n"
        "Shewchuk. Robust predicates. 1997. https://doi.org/10.1234/paper"
    )
    rows = MODULE.validate_entries(
        MODULE.extract_entries(text),
        1,
        0.45,
        lambda doi, _: software_metadata() if doi.value == SOFTWARE_DOI else metadata("Robust predicates"),
        citation=MODULE.SoftwareCitation.load(cff),
    )
    assert [(row.line, row.status) for row in rows] == [(1, MODULE.AuditStatus.MISMATCH), (3, MODULE.AuditStatus.OK)]
    assert [row.local_years for row in rows] == [("2001",), ("1997",)]
    assert rows[0].canonical_software is None


def test_multiline_title_keeps_doi_on_its_physical_source_line() -> None:
    text = '[archive]: https://example.org "Shewchuk. Robust predicates.\n1997. https://doi.org/10.1234/paper"'
    entries = MODULE.extract_entries(text)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(2, "10.1234/paper")]
    assert MODULE.validate_entry(entries[0], 1, 0.45, lambda *_: metadata("Robust predicates")).status == MODULE.AuditStatus.OK


def test_reference_uses_keep_first_definition_binding() -> None:
    text = "[Shewchuk. Robust predicates. 1997.][paper]\n\n[paper]: https://doi.org/10.1234/paper\n[paper]: https://doi.org/10.1234/other"
    assert [(entry.line, entry.doi.value) for entry in MODULE.extract_entries(text)] == [(1, "10.1234/paper"), (3, "10.1234/paper"), (4, "10.1234/other")]


@pytest.mark.parametrize(
    ("use", "label"),
    [
        ("[Wrong. Unrelated science. 2001.][software\nconcept doi]", "software concept doi"),
        ("[Wrong.\nUnrelated science. 2001.][software concept doi]", "software concept doi"),
        ("[Wrong.\nUnrelated science. 2001.][]", "Wrong. Unrelated science. 2001."),
        ("[Wrong.\nUnrelated science. 2001.]", "Wrong. Unrelated science. 2001."),
    ],
)
def test_multiline_reference_uses_retain_visible_conflicts_and_start_lines(tmp_path: Path, use: str, label: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f"# References\n\n{use}\n\n[{label}]: https://doi.org/{SOFTWARE_DOI}"
    entries = MODULE.extract_entries(text)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(3, SOFTWARE_DOI), (6, SOFTWARE_DOI)]
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert [row.status for row in rows] == [MODULE.AuditStatus.MISMATCH, MODULE.AuditStatus.OK]
    assert rows[0].local_years == ("2001",)
    assert rows[0].canonical_software is None


@pytest.mark.parametrize(
    ("use", "label", "field"),
    [
        ("[Shewchuk. Robust predicates. (1997).][paper-2018]", "paper-2018", "year"),
        ("[Wrong.][Shewchuk] Robust predicates. (2018).", "Shewchuk", "authors"),
        ("[Shewchuk. Unrelated science. (2018).][Robust predicates]", "Robust predicates", "title"),
    ],
)
def test_reference_identifiers_cannot_supply_missing_bibliographic_claims(use: str, label: str, field: str) -> None:
    text = f'{use}\n\n[{label}]: https://doi.org/10.1234/paper "Shewchuk. Robust predicates. (2018)."'
    entries = MODULE.extract_entries(text)
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: metadata("Robust predicates", year=2018))
    assert entries[0].entry == use  # Keep the original markup independently of claims.
    assert [row.status for row in rows] == [MODULE.AuditStatus.MISMATCH, MODULE.AuditStatus.OK]
    assert rows[0].mismatched_fields == (field,)
    assert rows[0].local_years == (("1997",) if field == "year" else ("2018",))


@pytest.mark.parametrize("visible", ["Wrong. Unrelated science. (2001).", "Shewchuk. Unrelated science. (2001)."])
def test_inline_destinations_cannot_supply_missing_citation_claims(visible: str) -> None:
    use = f"[{visible}](https://example.org/Shewchuk.Robust-predicates) [DOI][paper]"
    text = f'{use}\n\n[paper]: https://doi.org/10.1234/paper "Shewchuk. Robust predicates. 2001."'
    entries = MODULE.extract_entries(text)
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: metadata("Robust predicates", year=2001))
    assert entries[0].entry == use
    assert entries[0].bibliographic_claims == f"{visible} DOI"
    assert [row.status for row in rows] == [MODULE.AuditStatus.MISMATCH, MODULE.AuditStatus.OK]
    assert rows[0].mismatched_fields == ("title",)
    # Without an identified title, the existing contract leaves author attribution unknown.
    assert rows[0].author_score is None


def test_inline_author_link_cannot_supply_a_hidden_matching_author() -> None:
    text = "[Wrong.](https://example.org/Shewchuk.) Robust predicates. (2001). [DOI][paper]\n\n[paper]: https://doi.org/10.1234/paper"
    entry = MODULE.extract_entries(text)[0]
    row = MODULE.validate_entries([entry], 1, 0.45, lambda *_: metadata("Robust predicates", year=2001))[0]
    assert entry.bibliographic_claims == "Wrong. Robust predicates. (2001). DOI"
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.mismatched_fields == ("authors",)
    assert row.author_score == 0.0


@pytest.mark.parametrize("resolver", ["HTTPS://doi.org/", "https://DOI.ORG/", "HtTpS://DoI.OrG/"])
@pytest.mark.parametrize("style", ["reference", "inline", "raw"])
def test_resolver_case_preserves_doi_path_and_conflicting_use(resolver: str, style: str) -> None:
    doi = "10.1234/PaPer(Part)"
    claim = "Shewchuk. Robust predicates. 1997."
    use = f"[{claim}][paper]" if style == "reference" else f"[{claim}]({resolver}{doi})" if style == "inline" else f"{claim} {resolver}{doi}"
    text = f'{use}\n\n[paper]: {resolver}{doi} "Shewchuk. Robust predicates. 2018."'
    entries = MODULE.extract_entries(text)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(1, doi), (3, doi)]
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: metadata("Robust predicates", year=2018))
    assert [row.status for row in rows] == [MODULE.AuditStatus.MISMATCH, MODULE.AuditStatus.OK]
    assert rows[0].local_years == ("1997",)
    assert rows[0].mismatched_fields == ("year",)


@pytest.mark.parametrize("structured", ["[DOI](https://doi.org/10.1234/First(Part))", "DOI: <https://doi.org/10.1234/First(Part)>"])
@pytest.mark.parametrize("raw_first", [False, True])
@pytest.mark.parametrize("autolink", [False, True])
def test_structured_and_raw_dois_on_same_line_are_both_audited(structured: str, raw_first: bool, autolink: bool) -> None:
    raw_url = "HTTPS://DOI.ORG/10.1234/Second(Part)"
    raw = f"<{raw_url}>" if autolink else raw_url
    links = f"{raw} {structured}" if raw_first else f"{structured} {raw}"
    entries = MODULE.extract_entries(f"Shewchuk. Robust predicates. 1997. {links}")
    assert {(entry.line, entry.doi.value) for entry in entries} == {(1, "10.1234/First(Part)"), (1, "10.1234/Second(Part)")}
    assert len(entries) == 2
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda doi, _: metadata("Robust predicates", year=1997 if doi.value == "10.1234/First(Part)" else 2018))
    assert {row.doi: row.status for row in rows} == {"10.1234/First(Part)": MODULE.AuditStatus.OK, "10.1234/Second(Part)": MODULE.AuditStatus.MISMATCH}


@pytest.mark.parametrize("destination", ["https://doi.org/10.1234/PaPer(Part)", "https://example.org/archive"])
@pytest.mark.parametrize("label", ["https://doi.org/10.1234/PaPer(Part)", "HTTPS://DOI.ORG/10.1234/PaPer(Part)"])
def test_url_as_inline_label_is_a_single_doi_occurrence(destination: str, label: str) -> None:
    entries = MODULE.extract_entries(f"Shewchuk. Robust predicates. 1997. [{label}]({destination})")
    assert [(entry.line, entry.doi.value) for entry in entries] == [(1, "10.1234/PaPer(Part)")]
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: metadata("Robust predicates"))
    assert [row.status for row in rows] == [MODULE.AuditStatus.OK]


@pytest.mark.parametrize(
    "destination", [r"https://doi.org/10.1234/PaPer\(Part\)", "<https://doi.org/10.1234/PaPer(Part)>", r"<https://doi.org/10.1234/PaPer\(Part\)>"]
)
def test_inline_destination_escapes_preserve_doi_identity(destination: str) -> None:
    entries = MODULE.extract_entries(f"Shewchuk. Robust predicates. 1997. [DOI]({destination})")
    assert [entry.doi.value for entry in entries] == ["10.1234/PaPer(Part)"]
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: metadata("Robust predicates"))
    assert [row.status for row in rows] == [MODULE.AuditStatus.OK]


@pytest.mark.parametrize(
    ("markdown", "line"),
    [
        ("[Shewchuk. Robust\npredicates. 1997.](https://doi.org/10.1234/paper)", 2),
        ("[Shewchuk. Robust predicates. 1997.](\nhttps://doi.org/10.1234/paper)", 2),
        ("[Shewchuk. Robust\npredicates. 1997.](\n<https://doi.org/10.1234/paper>)", 3),
    ],
)
def test_wrapped_inline_links_keep_the_destination_source_line(markdown: str, line: int) -> None:
    entries = MODULE.extract_entries(markdown)
    assert [(entry.line, entry.doi.value) for entry in entries] == [(line, "10.1234/paper")]
    assert entries[0].bibliographic_claims == "Shewchuk. Robust predicates. 1997."
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: metadata("Robust predicates", year=2018))
    assert [row.status for row in rows] == [MODULE.AuditStatus.MISMATCH]
    assert rows[0].mismatched_fields == ("year",)


@pytest.mark.parametrize("destination", ["https://example.org/archive", "https://doi.org/10.1234/target"])
def test_explicit_doi_labels_remain_candidates_when_inline_links_are_masked(destination: str) -> None:
    entries = MODULE.extract_entries(f"Shewchuk. Robust predicates. 1997. DOI: [10.1234/label]({destination})")
    expected = {"10.1234/label", "10.1234/target"} if "doi.org" in destination else {"10.1234/label"}
    assert {entry.doi.value for entry in entries} == expected
    assert all(entry.line == 1 for entry in entries)


@pytest.mark.parametrize("wrapped_image", [False, True])
@pytest.mark.parametrize("visible_doi", [False, True])
def test_nested_image_destinations_do_not_leak_into_outer_link_label_scan(wrapped_image: bool, visible_doi: bool) -> None:
    destination = "https://doi.org/10.1234/PaPer(Part)"
    if wrapped_image:
        destination = "\n" + destination
    label = f"![DOI]({destination})"
    if visible_doi:
        label += "\nhttps://doi.org/10.1234/Second(Part)"
    entries = MODULE.extract_entries(f"[{label}](https://example.org/archive)")
    expected = [(2 if wrapped_image else 1, "10.1234/PaPer(Part)")]
    if visible_doi:
        expected.append((3 if wrapped_image else 2, "10.1234/Second(Part)"))
    assert [(entry.line, entry.doi.value) for entry in entries] == expected


def test_definition_identifier_is_not_a_publication_year_claim() -> None:
    text = '[paper-2018]: https://doi.org/10.1234/paper "Shewchuk. Robust predicates. (1997)."'
    row = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: metadata("Robust predicates", year=2018))[0]
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.local_years == ("1997",)
    assert row.mismatched_fields == ("year",)


@pytest.mark.parametrize(
    "use",
    [
        "[unresolved][Shewchuk. Robust predicates. (1997).][paper-2018]",
        "[Shewchuk. [Robust predicates]. (1997).][paper-2018]",
        r"\\[Shewchuk. Robust predicates. (1997).][paper-2018]",
        "[Shewchuk. Robust predicates. (1997).](not a link)",
    ],
)
def test_reference_precedence_cannot_hide_visible_year_conflicts(use: str) -> None:
    label = "Shewchuk. Robust predicates. (1997)." if use.endswith("(not a link)") else "paper-2018"
    text = f'{use}\n\n[{label}]: https://doi.org/10.1234/paper "Shewchuk. Robust predicates. (2018)."'
    rows = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: metadata("Robust predicates", year=2018))
    assert [(row.line, row.status) for row in rows] == [(1, MODULE.AuditStatus.MISMATCH), (3, MODULE.AuditStatus.OK)]
    assert rows[0].local_years == ("1997",)


def test_multiline_image_mask_preserves_reference_source_lines() -> None:
    text = (
        "![logo\nimage][badge]\n\n[Shewchuk. Robust predicates. 1997.][paper]\n\n[badge]: https://example.org/badge.svg\n[paper]: https://doi.org/10.1234/paper"
    )
    assert [(entry.line, entry.doi.value) for entry in MODULE.extract_entries(text)] == [(4, "10.1234/paper"), (7, "10.1234/paper")]


def test_unresolved_reference_text_cannot_become_a_claim_free_pointer(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f"[DOI][Wrong. Unrelated science. 2001.] https://doi.org/{SOFTWARE_DOI}"
    row = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))[0]
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.canonical_software is None
    assert row.local_years == ("2001",)


def test_literal_inline_syntax_in_code_is_not_a_claim_free_pointer(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f"`[DOI](Wrong.2001)` [DOI][doi]\n\n[doi]: https://doi.org/{SOFTWARE_DOI}"
    row = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))[0]
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.local_years == ("2001",)
    assert row.canonical_software is None


@pytest.mark.parametrize("image", ["![Wrong. Unrelated science. 2001.][missing]", "![Wrong. Unrelated science. 2001.][]", "![Wrong. Unrelated science. 2001.]"])
def test_unresolved_image_text_retains_visible_conflicts(tmp_path: Path, image: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f"{image} [DOI][doi]\n\n[doi]: https://doi.org/{SOFTWARE_DOI}"
    row = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))[0]
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.local_years == ("2001",)
    assert row.canonical_software is None


@pytest.mark.parametrize("code", ["`[paper]`", "``[paper] ` literal``", "`[paper]\n[paper]`", r"`[paper]\`", r"\``[paper]`"])
def test_code_spans_do_not_resolve_reference_uses(code: str) -> None:
    text = f"{code}\n\n[Shewchuk. Robust predicates. 1997.][paper]\n\n[paper]: https://doi.org/10.1234/paper"
    offset = code.count("\n")
    assert [(entry.line, entry.doi.value) for entry in MODULE.extract_entries(text)] == [(3 + offset, "10.1234/paper"), (5 + offset, "10.1234/paper")]


@pytest.mark.parametrize("use", ["[Wrong. `] [other]` Unrelated science. 2001.][paper]", "[Wrong. `![image][other]` Unrelated science. 2001.][paper]"])
def test_code_span_brackets_do_not_hide_outer_reference(use: str) -> None:
    text = f"{use}\n\n[paper]: https://doi.org/10.1234/paper\n[other]: https://example.org"
    rows = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: metadata("Robust predicates", year=2018))
    assert [(row.line, row.status) for row in rows] == [(1, MODULE.AuditStatus.MISMATCH), (3, MODULE.AuditStatus.INSUFFICIENT_CONTEXT)]
    assert rows[0].local_years == ("2001",)


def test_backticks_in_reference_identifier_remain_literal() -> None:
    text = "[Shewchuk. Robust predicates. 1997.][`paper`]\n\n[`paper`]: https://doi.org/10.1234/paper"
    assert [(entry.line, entry.doi.value) for entry in MODULE.extract_entries(text)] == [(1, "10.1234/paper"), (3, "10.1234/paper")]


def test_backticks_in_reference_labels_cannot_hide_later_doi_uses() -> None:
    """CommonMark labels are literal strings, independently of code-span syntax."""
    text = "[x][`foo] [paper] `\n\n[paper]: https://doi.org/10.1234/paper\n[`foo]: https://example.org"
    assert [(entry.line, entry.doi.value) for entry in MODULE.extract_entries(text)] == [(1, "10.1234/paper"), (3, "10.1234/paper")]


@pytest.mark.parametrize("marker", ["-", "*", "+", "1.", "1)"])
def test_code_spans_do_not_cross_list_items(marker: str) -> None:
    text = f"{marker} Unclosed `code\n{marker} [Wrong. Unrelated science. 2001.][paper]\n{marker} Closing ` marker\n\n[paper]: https://doi.org/10.1234/paper"
    rows = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: metadata("Robust predicates", year=2018))
    assert [(row.line, row.status) for row in rows] == [(2, MODULE.AuditStatus.MISMATCH), (5, MODULE.AuditStatus.INSUFFICIENT_CONTEXT)]
    assert rows[0].local_years == ("2001",)


@pytest.mark.parametrize("prefix", ["[x](https://example.org/`x)", '[x](https://example.org "`title")', "![alt](https://example.org/`x)"])
def test_backticks_in_inline_link_metadata_do_not_hide_later_references(prefix: str) -> None:
    text = f"{prefix} [paper] `\n\n[paper]: https://doi.org/10.1234/paper"
    assert [(entry.line, entry.doi.value) for entry in MODULE.extract_entries(text)] == [(1, "10.1234/paper"), (3, "10.1234/paper")]


@pytest.mark.parametrize("title", ["[Wrong. Unrelated science. 2001.]: https://doi.org/{doi}", "![Wrong. Unrelated science. 2001.](https://example.org)"])
def test_definition_title_claims_are_not_reparsed_as_markdown(tmp_path: Path, title: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f'[doi]: https://doi.org/{SOFTWARE_DOI} "{title.format(doi=SOFTWARE_DOI)}"'
    row = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))[0]
    assert row.status == MODULE.AuditStatus.MISMATCH
    assert row.canonical_software is None
    assert row.local_years == ("2001",)


@pytest.mark.parametrize(
    "inner", ["[DOI][paper]", "[paper]", "[paper][]", "[unresolved [DOI][paper]][missing]", "[[paper]][missing]", "[unresolved [paper][]][missing]"]
)
def test_inner_doi_reference_takes_precedence_over_outer_inline_link(tmp_path: Path, inner: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f"[Wrong. Unrelated science. 2001.\n{inner}](https://example.org)\n\n[paper]: https://doi.org/{SOFTWARE_DOI}"
    rows = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert [(row.line, row.status) for row in rows] == [(2, MODULE.AuditStatus.MISMATCH), (4, MODULE.AuditStatus.OK)]
    assert rows[0].local_years == ("2001",)
    assert rows[0].canonical_software is None


@pytest.mark.parametrize("name", [SOFTWARE_TITLE, SOFTWARE_TITLE.partition(":")[0]])
def test_definition_title_can_supply_matching_software_citation_instructions(tmp_path: Path, name: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = f'[doi]: https://doi.org/{SOFTWARE_DOI} "If you use {name} in your work, cite the software using CITATION.cff."'
    row = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))[0]
    assert row.status == MODULE.AuditStatus.OK
    assert row.canonical_software is not None
    assert row.local_status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT


@pytest.mark.parametrize(
    "image",
    [
        "![{claims}][badge]",
        "![{claims}](https://example.org/badge.svg)",
        "![{claims} [details]][badge]",
        "![details [{claims}][source]][badge]",
        "![{claims} [details]](https://example.org/badge.svg)",
        "![nested [level [{claims}]]][badge]",
    ],
)
def test_image_text_cannot_supply_missing_identity_claims(tmp_path: Path, image: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    image = image.format(claims=f"Getchell. {SOFTWARE_TITLE}. 2026.")
    text = f"Wrong. Unrelated science. 2001.\n{image}\n[DOI][doi]\n\n[badge]: https://example.org/badge.svg\n[doi]: https://doi.org/{SOFTWARE_DOI}"
    entries = MODULE.extract_entries(text)
    assert image in entries[0].entry
    rows = MODULE.validate_entries(entries, 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert [(row.line, row.status) for row in rows] == [(3, MODULE.AuditStatus.MISMATCH), (6, MODULE.AuditStatus.OK)]
    assert rows[0].local_years == ("2001",)
    assert "title" in rows[0].mismatched_fields
    assert "year" in rows[0].mismatched_fields


def test_repeated_software_pointer_is_checked_per_occurrence(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    text = "\n\n".join([SOFTWARE_LINKS[0], SOFTWARE_LINKS[-1], f"Wrong Author. Another title (2001). https://doi.org/{SOFTWARE_DOI}"])
    rows = MODULE.validate_entries(MODULE.extract_entries(text), 1, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert [row.status for row in rows] == [MODULE.AuditStatus.OK, MODULE.AuditStatus.OK, MODULE.AuditStatus.MISMATCH]
    assert len({row.line for row in rows}) == 3
    assert rows[0].canonical_software == rows[1].canonical_software
    assert rows[2].canonical_software is None


def software_metadata() -> dict[str, object]:
    """Return the resolved software identity from the motivating issue."""
    return {**metadata(SOFTWARE_TITLE, family="Getchell", year=2026), "DOI": SOFTWARE_DOI}


@pytest.mark.parametrize("link", SOFTWARE_LINKS)
def test_software_link_requires_context_then_matches_explicit_cff(tmp_path: Path, link: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(link)[0]
    original = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: software_metadata())
    assert original.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.OK
    assert result.local_status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    assert result.to_json_object()["canonical_software"]["doi"] == SOFTWARE_DOI
    assert original.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT


@pytest.mark.parametrize("field", ["published-print", "published", "published-online"])
@pytest.mark.parametrize("canonical", [False, True])
def test_software_pointers_retain_conflicting_publication_dates(tmp_path: Path, field: str, canonical: bool) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    raw = {**software_metadata(), "issued": {"date-parts": [[2025]]}, field: {"date-parts": [[2026]]}}
    citation = MODULE.SoftwareCitation.load(cff) if canonical else None
    result = MODULE.validate_entry(MODULE.extract_entries(SOFTWARE_LINKS[0])[0], 1.0, 0.45, lambda *_: raw, citation=citation)
    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.mismatched_fields == ("year",)
    assert "publication date fields disagree" in result.message
    assert dict(result.date_provenance) == {field: "2026", "issued": "2025"}


@pytest.mark.parametrize("claim", ["Wrong, A. " + SOFTWARE_TITLE + ". 2026.", "Getchell. Unrelated science. 2026.", "Getchell. " + SOFTWARE_TITLE + ". 2001."])
@pytest.mark.parametrize("link", SOFTWARE_LINKS[:2])
def test_canonical_software_never_overrides_local_contradictions(tmp_path: Path, claim: str, link: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(f"{claim}\n{link}")[0]
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.MISMATCH
    assert result.canonical_software is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("DOI", "10.1234/wrong"), ("DOI", "invalid"), ("title", "Another work"), ("author", [{"family": "Wrong"}]), ("issued", {"date-parts": [[2001]]})],
)
def test_canonical_software_rejects_wrong_resolved_identity(tmp_path: Path, field: str, value: object) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    raw = {**software_metadata(), field: value}
    result = MODULE.validate_entry(MODULE.extract_entries(SOFTWARE_LINKS[0])[0], 1.0, 0.0, lambda *_: raw, citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.MISMATCH


def test_wrong_linked_doi_cannot_match_canonical_identity(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    entry = MODULE.extract_entries(SOFTWARE_LINKS[0].replace(SOFTWARE_DOI, "10.1234/wrong"))[0]
    result = MODULE.validate_entry(entry, 1.0, 0.45, lambda *_: software_metadata(), citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.MISMATCH


@pytest.mark.parametrize("field", ["DOI", "author", "issued"])
def test_incomplete_resolved_software_is_not_a_match(tmp_path: Path, field: str) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    raw = software_metadata()
    del raw[field]
    result = MODULE.validate_entry(MODULE.extract_entries(SOFTWARE_LINKS[0])[0], 1.0, 0.45, lambda *_: raw, citation=MODULE.SoftwareCitation.load(cff))
    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT


def test_one_incomplete_resolver_author_prevents_canonical_software_success(tmp_path: Path) -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF)
    raw = {**software_metadata(), "author": [{"family": "Getchell"}, {"given": "A."}]}

    result = MODULE.validate_entry(MODULE.extract_entries(SOFTWARE_LINKS[0])[0], 1.0, 0.45, lambda *_: raw, citation=MODULE.SoftwareCitation.load(cff))

    assert result.status == MODULE.AuditStatus.INSUFFICIENT_CONTEXT
    assert result.resolved_authors == ("Getchell",)


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "title: [broken",
        CFF.replace("type: software", "type: dataset"),
        CFF.replace("date-released: 2026-09-28", ""),
        CFF.replace("family-names: Getchell", "family-names: 123"),
        CFF.replace(f"doi: {SOFTWARE_DOI}", ""),
        CFF.replace("date-released: 2026-09-28", "date-released: unknown"),
    ],
)
def test_invalid_canonical_input_is_a_cli_error(tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str) -> None:
    markdown, cff = tmp_path / "README.md", tmp_path / "CITATION.cff"
    markdown.write_text(SOFTWARE_LINKS[0])
    cff.write_text(content)
    assert MODULE.run([str(markdown), "--citation-cff", str(cff), "--json"]) == 2
    assert not capsys.readouterr().out


def test_canonical_cli_keeps_scholarly_checks_and_input_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    markdown, cff = tmp_path / "README.md", tmp_path / "CITATION.cff"
    markdown.write_text(SOFTWARE_LINKS[0] + "\n\nShewchuk. Robust predicates. 1997. DOI: [10.1234/paper](https://doi.org/10.1234/paper)\n")
    cff.write_text(CFF + 'preferred-citation:\n  title: "Unrelated preferred paper"\n')
    original = MODULE.validate_entries

    def fetcher(doi: Any, _timeout: float) -> dict[str, object]:
        return software_metadata() if str(doi.value) == SOFTWARE_DOI else metadata("Robust predicates")

    monkeypatch.setattr(MODULE, "validate_entries", lambda entries, timeout, score, **kwargs: original(entries, timeout, score, fetcher, **kwargs))
    assert MODULE.run([str(markdown), "--citation-cff", str(cff), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["status"] for row in rows] == ["OK", "OK"]
    assert rows[0]["local_status"] == "INSUFFICIENT_CONTEXT"
    assert base64.b64decode(rows[0]["canonical_software"]["content_base64"], validate=True) == cff.read_bytes()
    assert "canonical_software" not in rows[1]
    assert rows[0]["source"]["path"] == str(markdown)


def test_empty_input_fails_without_allow_empty() -> None:
    """Empty audits fail loudly unless the caller opts out."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        path = Path(handle.name)
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            code = MODULE.run([str(path)])
    finally:
        path.unlink()

    assert code == 2
    assert "no DOI references found" in stderr.getvalue()


def test_invalid_threshold_is_rejected_by_argparse() -> None:
    """CLI parsing rejects non-finite title thresholds."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        path = Path(handle.name)
        handle.write("- Shewchuk. https://doi.org/10.1007/PL00009321\n")
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            try:
                MODULE.run(["--min-title-score", "nan", str(path)])
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            else:
                code = 0
    finally:
        path.unlink()

    assert code == 2
    assert "threshold must be" in stderr.getvalue()


TESTS = [
    test_extracts_doi_label_with_parentheses_and_angle_tokens,
    test_extracts_markdown_link_destination_with_balanced_parentheses,
    test_extracts_raw_url_with_trailing_period,
    test_validation_flags_author_mismatch,
    test_validation_accepts_matching_title_author_and_year,
    test_validation_reports_malformed_fetcher_response,
    test_empty_input_fails_without_allow_empty,
    test_invalid_threshold_is_rejected_by_argparse,
]


def main() -> int:
    """Run the fixture tests without requiring pytest."""
    for test in TESTS:
        test()
    print(f"Ran {len(TESTS)} tests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
